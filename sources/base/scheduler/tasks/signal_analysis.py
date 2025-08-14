"""Celery tasks for signal analysis (transition detection only)."""

from celery.schedules import crontab
import traceback
import json
import importlib
from datetime import datetime, timedelta, time, timezone
from typing import Dict, Any, List, Optional
from uuid import uuid4
import numpy as np

import pytz
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from sources.base.scheduler.celery_app import app
from sources.base.storage.database import get_sync_db, sync_engine

# Create session factory using the centralized engine
Session = sessionmaker(bind=sync_engine)


@app.task(name="start_transition_detection", bind=True,
          autoretry_for=(Exception,), retry_kwargs={'max_retries': 3})
def start_transition_detection(
    self,
    date: str,
    run_type: str = "manual",
    custom_start_time: Optional[str] = None,
    custom_end_time: Optional[str] = None,
    timezone: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run transition detection for ambient signals for a specific date or custom time range.

    Args:
        date: Either ISO date (2024-12-15) or keyword ('yesterday', 'today')
        run_type: 'manual' or 'scheduled' for tracking
        custom_start_time: Optional ISO datetime string for custom start (overrides date)
        custom_end_time: Optional ISO datetime string for custom end (overrides date)
        timezone: Timezone (e.g., 'America/Chicago'). Uses default if not provided

    Returns:
        Dict with results including transition counts and processing time
    """
    db = Session()
    start_process_time = datetime.utcnow()

    try:
        # Use provided timezone or get from single user record
        if timezone is None:
            # Get timezone from the single user (using users table as settings)
            result = db.execute(
                text("SELECT timezone FROM users LIMIT 1"),
                {}
            )
            user_record = result.fetchone()
            if user_record and user_record[0]:
                timezone = user_record[0]
            else:
                # Fallback to environment or default
                import os
                timezone = os.environ.get('DEFAULT_TIMEZONE', 'America/Chicago')

        # Create timezone object
        try:
            tz = pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            tz = pytz.timezone('America/Chicago')  # Fallback

        # Parse time window
        if custom_start_time and custom_end_time:
            # Use custom time range for testing
            start_time = datetime.fromisoformat(
                custom_start_time.replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(
                custom_end_time.replace('Z', '+00:00'))
            # Remove timezone info for consistency with PostgreSQL
            if start_time.tzinfo:
                start_time = start_time.replace(tzinfo=None)
            if end_time.tzinfo:
                end_time = end_time.replace(tzinfo=None)
            target_date = start_time.date()
        else:
            # Parse date based on user's local timezone
            if date == 'yesterday':
                # Get current time in user's timezone
                now_local = datetime.now(tz)
                target_date = (now_local - timedelta(days=1)).date()
            elif date == 'today':
                # Get current time in user's timezone
                now_local = datetime.now(tz)
                target_date = now_local.date()
            else:
                # Date is provided as ISO format (e.g., "2024-12-15")
                target_date = datetime.fromisoformat(date).date()

            # Create local midnight to midnight for the target date
            local_start = tz.localize(datetime.combine(target_date, time.min))
            local_end = tz.localize(datetime.combine(target_date, time.max))

            # Convert to UTC for database queries
            start_time = local_start.astimezone(pytz.UTC).replace(tzinfo=None)
            end_time = local_end.astimezone(pytz.UTC).replace(tzinfo=None)

        # Get all active signals with their config
        # Join signal_configs with streams to find enabled signals
        signals_result = db.execute(
            text("""
                SELECT DISTINCT ON (sc.id)
                       sc.id, sc.source_name, sc.signal_name,
                       sc.computation::text as computation,
                       sc.fidelity_score, sc.description, sc.macro_weight, sc.min_transition_gap
                FROM signal_configs sc
                INNER JOIN stream_configs stc ON stc.source_name = sc.source_name
                    AND stc.stream_name = sc.stream_name
                INNER JOIN streams s ON s.stream_config_id = stc.id
                INNER JOIN sources src ON src.id = s.source_id
                WHERE s.enabled = true
                    AND src.status = 'active'
                    AND (
                        s.enabled_signals IS NULL
                        OR s.enabled_signals::text = '[]'
                        OR sc.signal_name = ANY(
                            SELECT json_array_elements_text(s.enabled_signals)
                        )
                    )
                ORDER BY sc.id
            """),
            {}
        )

        active_signals = []
        for row in signals_result:
            signal_dict = dict(row._mapping)
            # Parse computation JSON if it's a string
            if isinstance(signal_dict.get('computation'), str):
                signal_dict['computation'] = json.loads(signal_dict['computation'])
            active_signals.append(signal_dict)

        print(f"Found {len(active_signals)} active signals")
        for sig in active_signals:
            print(
                f"  - {sig['source_name']} / {sig['signal_name']} (id: {sig['id']})")

        # Clear existing transitions for this time window
        print(
            f"Clearing existing transitions for time window {start_time} to {end_time}")
        db.execute(
            text("""
                DELETE FROM signal_transitions
                WHERE transition_time >= :start_time
                AND transition_time <= :end_time
            """),
            {
                "start_time": start_time,
                "end_time": end_time
            }
        )
        db.commit()

        # Run transition detection for each signal
        transitions_by_source = {}
        total_signals_processed = 0
        total_transitions_detected = 0

        for signal in active_signals:
            # Use signal_name directly as it already contains source prefix
            source_signal_key = signal['signal_name']

            # Get ambient signals
            signal_data = _get_ambient_signals(
                db, signal['id'], start_time, end_time
            )

            if not signal_data:
                continue

            total_signals_processed += len(signal_data)

            # Try to import a transition detector for this signal
            # Check if detector info is in the computation field
            try:
                computation = signal.get('computation', {})
                detector_module = computation.get('detector_module')
                detector_class_name = computation.get('detector_class')

                if not detector_module or not detector_class_name:
                    # Fall back to checking for known patterns if not in database
                    # This is for backward compatibility during migration
                    if source_signal_key == 'google_calendar_events':
                        detector_module = 'sources.google.calendar.events.detector'
                        detector_class_name = 'CalendarEventsTransitionDetector'
                    elif source_signal_key == 'ios_speed':
                        detector_module = 'sources.ios.location.speed.detector'
                        detector_class_name = 'SpeedTransitionDetector'
                    elif source_signal_key == 'ios_coordinates':
                        detector_module = 'sources.ios.location.coordinates.detector'
                        detector_class_name = 'CoordinatesTransitionDetector'
                    elif source_signal_key == 'ios_altitude':
                        detector_module = 'sources.ios.location.altitude.detector'
                        detector_class_name = 'AltitudeTransitionDetector'
                    else:
                        print(f"No detector configuration found for {source_signal_key}")
                        continue

                # Import the detector module and class
                module = importlib.import_module(detector_module)
                detector_class = getattr(module, detector_class_name)

                print(
                    f"Processing signal {source_signal_key} with transition detector {detector_class.__name__}")

                # Initialize transition detector with signal config
                # Pass the full signal config to the detector
                detector = detector_class(config=signal)

                # Pass min_transition_gap to detector if available
                if signal.get('min_transition_gap'):
                    detector.min_transition_gap = signal['min_transition_gap']

                # Detect transitions
                transitions = detector.detect_transitions(
                    signal_data, start_time, end_time
                )

                if transitions:
                    transitions_by_source[source_signal_key] = transitions
                    total_transitions_detected += len(transitions)
                    print(f"  - Detected {len(transitions)} transitions for {source_signal_key}")

                    # Store signal-level transitions in signal_transitions table
                    for i, transition in enumerate(transitions):
                        _store_signal_transition(
                            db, signal['source_name'],
                            signal['signal_name'], transition
                        )
                    print(f"  - Stored {len(transitions)} transitions for {source_signal_key}")

            except (ImportError, AttributeError) as e:
                print(f"Could not load detector for {source_signal_key}: {e}")

        # Commit all transitions
        db.commit()

        # Calculate processing time
        processing_time_ms = int(
            (datetime.utcnow() - start_process_time).total_seconds() * 1000
        )

        return {
            "success": True,
            "date": str(target_date),
            "transitions_detected": total_transitions_detected,
            "signals_processed": total_signals_processed,
            "processing_time_ms": processing_time_ms,
            "run_type": run_type,
            "transitions_by_source": {k: len(v) for k, v in transitions_by_source.items()}
        }

    except Exception as e:
        # Rollback any pending transaction
        db.rollback()
        error_message = f"{type(e).__name__}: {str(e)}"
        traceback.print_exc()
        raise

    finally:
        db.close()


def _get_ambient_signals(
    db,
    signal_id: str,
    start_time: datetime,
    end_time: datetime
) -> List[Dict[str, Any]]:
    """Get ambient signals for a time window."""
    print(
        f"Fetching ambient signals: signal_id={signal_id}, start={start_time}, end={end_time}")

    # First, get the signal name to determine if it's a coordinate signal
    signal_info = db.execute(
        text("SELECT signal_name FROM signal_configs WHERE id = :signal_id"),
        {"signal_id": signal_id}
    ).fetchone()

    signal_name = signal_info[0] if signal_info else None
    is_coordinate_signal = signal_name == 'ios_coordinates' if signal_name else False

    # Build query based on signal type
    if is_coordinate_signal:
        # Include coordinate extraction only for GPS signals
        query = text("""
            SELECT
                id, signal_id, signal_name, signal_value,
                timestamp, confidence, idempotency_key, source_metadata,
                created_at,
                ST_X(coordinates) as lng, ST_Y(coordinates) as lat
            FROM signals
            WHERE signal_id = :signal_id
            AND timestamp >= :start_time
            AND timestamp <= :end_time
            ORDER BY timestamp
        """)
    else:
        # Exclude coordinate data for non-GPS signals
        query = text("""
            SELECT
                id, signal_id, signal_name, signal_value,
                timestamp, confidence, idempotency_key, source_metadata,
                created_at
            FROM signals
            WHERE signal_id = :signal_id
            AND timestamp >= :start_time
            AND timestamp <= :end_time
            ORDER BY timestamp
        """)

    result = db.execute(
        query,
        {
            "signal_id": signal_id,
            "start_time": start_time,
            "end_time": end_time
        }
    )

    signals = []
    for row in result:
        signal_dict = dict(row._mapping)
        # Only process coordinates for GPS signals
        if is_coordinate_signal and signal_dict.get('lat') is not None and signal_dict.get('lng') is not None:
            signal_dict['coordinates'] = {
                'lat': signal_dict.pop('lat'),
                'lng': signal_dict.pop('lng')
            }
        signals.append(signal_dict)
    print(
        f"Found {len(signals)} ambient signals for signal_id {signal_id} (signal_name: {signal_name})")
    return signals


def _store_signal_transition(
    db,
    source_name: str,
    signal_name: str,
    transition
):
    """Store a signal-level transition."""
    import json

    transition_dict = transition.to_dict()

    # Serialize metadata to JSON string
    metadata = transition_dict.get("metadata", {})
    metadata_json = json.dumps(metadata) if metadata else "{}"

    db.execute(
        text("""
            INSERT INTO signal_transitions
            (id, source_name, signal_name, transition_time, transition_type,
             change_magnitude, change_direction, before_mean, before_std,
             after_mean, after_std, confidence, detection_method,
             transition_metadata, created_at)
            VALUES
            (:id, :source_name, :signal_name, :transition_time, :transition_type,
             :change_magnitude, :change_direction, :before_mean, :before_std,
             :after_mean, :after_std, :confidence, :detection_method,
             :transition_metadata, :created_at)
            ON CONFLICT (source_name, signal_name, transition_time, transition_type, change_direction)
            DO UPDATE SET
                change_magnitude = EXCLUDED.change_magnitude,
                before_mean = EXCLUDED.before_mean,
                before_std = EXCLUDED.before_std,
                after_mean = EXCLUDED.after_mean,
                after_std = EXCLUDED.after_std,
                confidence = EXCLUDED.confidence,
                detection_method = EXCLUDED.detection_method,
                transition_metadata = EXCLUDED.transition_metadata,
                created_at = signal_transitions.created_at  -- Keep original creation time
        """),
        {
            "id": transition_dict["id"],
            "source_name": source_name,
            "signal_name": signal_name,
            "transition_time": transition_dict["transition_time"],
            "transition_type": transition_dict.get("transition_type"),
            "change_magnitude": transition_dict.get("change_magnitude"),
            "change_direction": transition_dict.get("change_direction"),
            "before_mean": transition_dict.get("before_mean"),
            "before_std": transition_dict.get("before_std"),
            "after_mean": transition_dict.get("after_mean"),
            "after_std": transition_dict.get("after_std"),
            "confidence": transition_dict["confidence"],
            "detection_method": transition_dict["detection_method"],
            "transition_metadata": metadata_json,
            "created_at": datetime.utcnow()
        }
    )


@app.task(name="run_single_signal_transition_detection", bind=True,
          autoretry_for=(Exception,), retry_kwargs={'max_retries': 3})
def run_single_signal_transition_detection(
    self,
    signal_name: str,
    date: str,
    start_time: str,
    end_time: str,
    timezone: str = "America/Chicago"
) -> Dict[str, Any]:
    """
    Run transition detection for a single specific ambient signal.

    Args:
        signal_name: The specific signal to process (e.g., 'ios_speed')
        date: ISO date string (2025-07-23)
        start_time: ISO datetime string for start
        end_time: ISO datetime string for end
        timezone: Timezone for the detection

    Returns:
        Dict with results including transition count and processing time
    """
    db = Session()
    start_process_time = datetime.utcnow()

    try:
        # Parse time window
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))

        print(f"\n{'='*60}")
        print(f"[TransitionDetection] Running single signal detection")
        print(f"[TransitionDetection] Signal name: {signal_name}")
        print(f"[TransitionDetection] Time range: {start_dt} to {end_dt}")
        print(f"{'='*60}")

        # Debug: Check what signals exist
        debug_result = db.execute(
            text("SELECT signal_name, status FROM signal_configs"),
            {}
        )
        debug_signals = [f"{row[0]} ({row[1]})" for row in debug_result]
        print(f"[DEBUG] All signals: {debug_signals}")

        # Find the specific signal
        signal_result = db.execute(
            text("""
                SELECT id, source_name, signal_name, computation, fidelity_score, description, macro_weight, min_transition_gap
                FROM signal_configs
                WHERE signal_name = :signal_name
                AND status = 'active'
            """),
            {"signal_name": signal_name}
        )

        signal_record = signal_result.fetchone()
        if not signal_record:
            return {
                "success": False,
                "error": f"Signal {signal_name} not found or not active"
            }

        signal = dict(signal_record._mapping)
        # Parse computation JSON if it's a string
        if isinstance(signal.get('computation'), str):
            signal['computation'] = json.loads(signal['computation'])
        print(f"[TransitionDetection] Found signal: {signal}")

        # Get signal data first
        signal_data = _get_ambient_signals(
            db, signal['id'],
            start_dt.replace(tzinfo=None) if start_dt.tzinfo else start_dt,
            end_dt.replace(tzinfo=None) if end_dt.tzinfo else end_dt
        )

        if not signal_data:
            print(f"\n[TransitionDetection] ❌ No signal data found!")
            return {
                "success": False,
                "error": f"No signal data found for {signal_name} in the specified time range"
            }

        print(
            f"\n[TransitionDetection] ✅ Found {len(signal_data)} data points for {signal_name}")

        # Load transition detector dynamically from computation config
        computation = signal.get('computation', {})
        detector_module = computation.get('detector_module')
        detector_class_name = computation.get('detector_class')

        if not detector_module or not detector_class_name:
            # Fall back to known patterns for backward compatibility
            if signal_name == 'google_calendar_events':
                detector_module = 'sources.google.calendar.events.detector'
                detector_class_name = 'CalendarEventsTransitionDetector'
            elif signal_name == 'ios_speed':
                detector_module = 'sources.ios.location.speed.detector'
                detector_class_name = 'SpeedTransitionDetector'
            elif signal_name == 'ios_coordinates':
                detector_module = 'sources.ios.location.coordinates.detector'
                detector_class_name = 'CoordinatesTransitionDetector'
            elif signal_name == 'ios_altitude':
                detector_module = 'sources.ios.location.altitude.detector'
                detector_class_name = 'AltitudeTransitionDetector'
            else:
                return {
                    "success": False,
                    "error": f"No transition detector configured for signal {signal_name}"
                }

        # Import and instantiate the detector
        try:
            module = importlib.import_module(detector_module)
            detector_class = getattr(module, detector_class_name)
            # Pass the full signal config to the detector
            detector = detector_class(config=signal)
        except (ImportError, AttributeError) as e:
            return {
                "success": False,
                "error": f"Failed to load detector for {signal_name}: {e}"
            }

        # Clear existing transitions for this signal in the time range
        db.execute(
            text("""
                DELETE FROM signal_transitions
                WHERE signal_name = :signal_name
                AND transition_time >= :start_time
                AND transition_time <= :end_time
            """),
            {
                "signal_name": signal_name,
                "start_time": start_dt,
                "end_time": end_dt
            }
        )

        # Detect transitions
        print(
            f"\n[TransitionDetection] Running transition detection with {detector.__class__.__name__}")
        transitions = detector.detect_transitions(
            signal_data, start_dt, end_dt)

        print(
            f"[TransitionDetection] Detected {len(transitions)} transitions")

        if not transitions:
            return {
                "success": True,
                "signal_name": signal_name,
                "transitions_detected": 0,
                "signals_processed": len(signal_data),
                "processing_time_ms": int((datetime.utcnow() - start_process_time).total_seconds() * 1000),
                "message": "No transitions detected"
            }

        # Store transitions
        for i, transition in enumerate(transitions):
            print(
                f"[TransitionDetection] Storing transition {i+1}: {transition.from_state} -> {transition.to_state} at {transition.transition_time}")
            _store_signal_transition(
                db, signal['source_name'],
                signal['signal_name'], transition
            )

        db.commit()

        return {
            "success": True,
            "signal_name": signal_name,
            "transitions_detected": len(transitions),
            "signals_processed": len(signal_data),
            "processing_time_ms": int((datetime.utcnow() - start_process_time).total_seconds() * 1000),
            "message": f"Successfully processed {len(transitions)} transitions for {signal_name}"
        }

    except Exception as e:
        # Rollback any pending transaction
        db.rollback()
        error_message = f"{type(e).__name__}: {str(e)}"
        print(f"Error in single signal transition detection: {error_message}")
        raise

    finally:
        db.close()


# Schedule daily transition detection
@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """Set up periodic transition detection tasks."""
    # Run daily at 3am for all active users
    sender.add_periodic_task(
        crontab(hour=3, minute=0),
        # run_daily_transition_detection.s(),  # Commented out - no longer uses user_id
        name='daily-transition-detection'
    )

@app.task(name="generate_events_hdbscan", bind=True,
          autoretry_for=(Exception,), retry_kwargs={'max_retries': 3})
def generate_events_hdbscan(
    self,
    date: str,
    timezone: Optional[str] = None,
    min_cluster_size: Optional[int] = None,
    epsilon: Optional[float] = None,
    target_min_events: int = 8,
    target_max_events: int = 24
) -> Dict[str, Any]:
    """
    Generate continuous day segments using HDBSCAN to consolidate noisy transitions.
    
    This task:
    1. Consolidates noisy transitions into clean boundaries using HDBSCAN
    2. Creates 8-24 boundaries representing state changes
    3. Generates continuous segments that fill the entire day

    Args:
        date: ISO date string (2025-01-15)
        timezone: Timezone string (e.g., 'America/Chicago'). Uses user default if not provided
        min_cluster_size: Minimum cluster size for HDBSCAN (auto-calculated if None)
        epsilon: Epsilon parameter for HDBSCAN in seconds (auto-calculated if None)
        target_min_events: Minimum target number of events (default 8)
        target_max_events: Maximum target number of events (default 24)

    Returns:
        Dict with clustering results and mathematical metrics
    """
    db = Session()
    start_process_time = datetime.utcnow()

    try:
        # Import sklearn's DBSCAN as a fallback (it's already available)
        from sklearn.cluster import DBSCAN
        from scipy.stats import entropy as scipy_entropy

        # Get timezone if not provided
        if timezone is None:
            # Get timezone from the single user record
            result = db.execute(
                text("SELECT timezone FROM users LIMIT 1"),
                {}
            )
            user_record = result.fetchone()
            if user_record and user_record[0]:
                timezone = user_record[0]
            else:
                # Fallback to environment or default
                import os
                timezone = os.environ.get('DEFAULT_TIMEZONE', 'America/Chicago')
        
        print(f"Using timezone: {timezone} for date: {date}")
        
        # Parse date and create timezone-aware boundaries
        target_date = datetime.fromisoformat(date).date()
        
        # Create timezone object
        try:
            tz = pytz.timezone(timezone)
        except pytz.exceptions.UnknownTimeZoneError:
            print(f"Unknown timezone {timezone}, falling back to America/Chicago")
            tz = pytz.timezone('America/Chicago')
        
        # Create midnight-to-midnight in user's timezone
        local_start = tz.localize(datetime.combine(target_date, time.min))
        local_end = tz.localize(datetime.combine(target_date, time.max))
        
        # Convert to UTC for database queries (as naive datetimes)
        utc_start = local_start.astimezone(pytz.UTC).replace(tzinfo=None)
        utc_end = local_end.astimezone(pytz.UTC).replace(tzinfo=None)
        
        print(f"Date boundaries for {date} in {timezone}:")
        print(f"  Local: {local_start} to {local_end}")
        print(f"  UTC: {utc_start} to {utc_end}")

        # Get all transitions for the timezone-aware day
        result = db.execute(
            text("""
                SELECT
                    id, source_name, signal_name, transition_time,
                    transition_type, change_magnitude, change_direction,
                    before_mean, after_mean, confidence, detection_method,
                    transition_metadata
                FROM signal_transitions
                WHERE transition_time >= :utc_start
                  AND transition_time <= :utc_end
                ORDER BY transition_time
            """),
            {"utc_start": utc_start, "utc_end": utc_end}
        )

        transitions = [dict(row._mapping) for row in result]
        n_transitions = len(transitions)

        if n_transitions < 2:
            return {
                "success": False,
                "error": f"Not enough transitions ({n_transitions}) for clustering. Need at least 2."
            }
        
        # Phase 1: Extract features for HDBSCAN consolidation
        print(f"Preparing {n_transitions} transitions for HDBSCAN consolidation...")
        
        # Build feature matrix for transition clustering
        features = []
        for i, t in enumerate(transitions):
            trans_time = t['transition_time']
            # Ensure timezone-naive for all calculations
            if trans_time.tzinfo is not None:
                trans_time = trans_time.replace(tzinfo=None)
            
            # Feature 1: Temporal position (most important for consolidation)
            time_of_day = trans_time.hour + trans_time.minute / 60.0  # 0-24 scale
            
            # Feature 2: Signal type embedding (simple hash for now)
            signal_hash = hash(t['signal_name']) % 100 / 100.0  # 0-1 scale
            
            # Feature 3: Change magnitude
            magnitude = t.get('change_magnitude', 0.5) if t.get('change_magnitude') else 0.5
            
            # Feature 4: Confidence
            confidence = t.get('confidence', 0.5)
            
            # Feature 5: Local density (transitions within 2 minutes)
            window_start = trans_time - timedelta(minutes=2)
            window_end = trans_time + timedelta(minutes=2)
            nearby_count = 0
            for other in transitions:
                other_time = other['transition_time']
                # Ensure consistent timezone handling
                if other_time.tzinfo is not None:
                    other_time = other_time.replace(tzinfo=None)
                if window_start <= other_time <= window_end:
                    nearby_count += 1
            density = nearby_count / 10.0  # Normalize to ~0-1
            
            # Feature 6: Source diversity in local window
            nearby_sources = set()
            for other in transitions:
                other_time = other['transition_time']
                # Ensure consistent timezone handling
                if other_time.tzinfo is not None:
                    other_time = other_time.replace(tzinfo=None)
                if window_start <= other_time <= window_end:
                    nearby_sources.add(other['source_name'])
            diversity = len(nearby_sources) / 4.0  # Normalize by max sources
            
            features.append([
                time_of_day,    # When
                signal_hash,    # What signal
                magnitude,      # How much change
                confidence,     # How confident
                density,        # How many nearby
                diversity       # How diverse
            ])
        
        features = np.array(features)
        print(f"Feature matrix shape: {features.shape}")

        # Phase 2: HDBSCAN clustering to consolidate transitions
        print(f"Running HDBSCAN to consolidate transitions into boundaries...")
        
        # Use DBSCAN for consolidation (HDBSCAN not available, but DBSCAN works well)
        # Key parameters:
        # - eps: controls how close transitions need to be to consolidate
        # - min_samples: minimum transitions to form a consolidated boundary
        from sklearn.cluster import DBSCAN
        
        clusterer = DBSCAN(
            eps=0.3,  # Relatively tight clustering for consolidation
            min_samples=2,  # At least 2 transitions to consolidate
            metric='euclidean'
        )
        
        cluster_labels = clusterer.fit_predict(features)
        n_clusters = len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
        n_noise = list(cluster_labels).count(-1)
        
        print(f"Found {n_clusters} clusters and {n_noise} noise points")
        
        # Phase 3: Create consolidated boundaries from clusters
        boundaries = []
        
        for cluster_id in set(cluster_labels):
            cluster_transitions = [transitions[i] for i, label in enumerate(cluster_labels) 
                                  if label == cluster_id]
            
            if cluster_id == -1:
                # Noise points remain individual boundaries
                for t in cluster_transitions:
                    trans_time = t['transition_time']
                    # Ensure timezone-naive for consistency
                    if trans_time.tzinfo is not None:
                        trans_time = trans_time.replace(tzinfo=None)
                    boundaries.append({
                        'timestamp': trans_time,
                        'confidence': t.get('confidence', 0.5),
                        'transition_count': 1,
                        'source_transitions': [t['id']],
                        'is_consolidated': False
                    })
            else:
                # Consolidate cluster to single boundary
                # Use confidence-weighted average for timestamp
                weights = [t.get('confidence', 0.5) for t in cluster_transitions]
                # Handle both timezone-aware and naive datetimes
                timestamps = []
                for t in cluster_transitions:
                    trans_time = t['transition_time']
                    if trans_time.tzinfo is not None:
                        trans_time = trans_time.replace(tzinfo=None)
                    timestamps.append((trans_time - datetime(1970, 1, 1)).total_seconds())
                weighted_timestamp_seconds = np.average(timestamps, weights=weights)
                weighted_timestamp = datetime(1970, 1, 1) + timedelta(seconds=weighted_timestamp_seconds)
                
                boundaries.append({
                    'timestamp': weighted_timestamp,
                    'confidence': np.mean(weights),
                    'transition_count': len(cluster_transitions),
                    'source_transitions': [t['id'] for t in cluster_transitions],
                    'is_consolidated': True
                })
        
        # Sort boundaries by time
        boundaries.sort(key=lambda b: b['timestamp'])
        print(f"Created {len(boundaries)} boundaries from {n_transitions} transitions")
        
        # Phase 4: Reduce boundaries to target range (8-24)
        # Calculate target based on data coverage
        if boundaries:
            first_boundary = boundaries[0]['timestamp']
            last_boundary = boundaries[-1]['timestamp']
            data_span_hours = (last_boundary - first_boundary).total_seconds() / 3600
            
            # Scale target based on data coverage
            # For full day (24 hours): 8-24 events
            # For partial days: scale proportionally
            # Minimum 2 events for any data period > 1 hour
            data_coverage_ratio = data_span_hours / 24.0
            
            if data_span_hours < 1:
                # Less than 1 hour of data - just create 1-2 events
                scaled_min = 1
                scaled_max = 2
            elif data_span_hours < 6:
                # Less than 6 hours - create 2-6 events (roughly 1 per hour)
                scaled_min = max(2, int(data_span_hours * 0.5))
                scaled_max = min(6, max(scaled_min + 1, int(data_span_hours * 1.2)))
            else:
                # 6+ hours - scale from full day targets
                scaled_min = max(4, int(target_min_events * data_coverage_ratio))
                scaled_max = max(scaled_min + 2, int(target_max_events * data_coverage_ratio))
            
            print(f"Data spans {data_span_hours:.1f} hours, target: {scaled_min}-{scaled_max} segments")
        else:
            scaled_min = target_min_events
            scaled_max = target_max_events
        
        # Reduce boundaries if needed
        while len(boundaries) > scaled_max:
            # Find least important adjacent pair
            min_importance = float('inf')
            merge_idx = -1
            
            for i in range(len(boundaries) - 1):
                # Importance = confidence product * log(time gap)
                time_gap = (boundaries[i+1]['timestamp'] - boundaries[i]['timestamp']).total_seconds()
                importance = boundaries[i]['confidence'] * boundaries[i+1]['confidence'] * np.log(time_gap + 60)
                
                if importance < min_importance:
                    min_importance = importance
                    merge_idx = i
            
            # Merge by removing less confident boundary
            if boundaries[merge_idx]['confidence'] < boundaries[merge_idx + 1]['confidence']:
                boundaries.pop(merge_idx)
            else:
                boundaries.pop(merge_idx + 1)
        
        print(f"Reduced to {len(boundaries)} boundaries after targeting {scaled_min}-{scaled_max} segments")

        # Phase 5: Create continuous segments from boundaries
        # Use the timezone-aware boundaries we calculated earlier
        start_of_day = utc_start  # Already naive datetime in UTC
        end_of_day = utc_end      # Already naive datetime in UTC
        
        # Start with actual data boundaries
        all_boundaries = []
        
        # Only add synthetic boundaries if we have gaps at day edges
        if boundaries:
            first_boundary = boundaries[0]['timestamp']
            last_boundary = boundaries[-1]['timestamp']
            
            # Add start boundary only if data doesn't start near day beginning
            gap_from_start = (first_boundary - start_of_day).total_seconds()
            if gap_from_start > 900:  # > 15 minutes from day start
                all_boundaries.append({
                    'timestamp': start_of_day,
                    'confidence': 0.0,
                    'transition_count': 0,
                    'source_transitions': [],
                    'is_synthetic': True
                })
                print(f"Added synthetic start boundary (gap: {gap_from_start/3600:.1f} hours)")
            
            # Add real boundaries
            all_boundaries.extend(boundaries)
            
            # Add end boundary only if data doesn't reach near day end
            # AND the gap isn't too large (which would indicate no data)
            gap_to_end = (end_of_day - last_boundary).total_seconds()
            if gap_to_end > 900 and gap_to_end < 14400:  # > 15 min but < 4 hours
                all_boundaries.append({
                    'timestamp': end_of_day,
                    'confidence': 0.0,
                    'transition_count': 0,
                    'source_transitions': [],
                    'is_synthetic': True
                })
                print(f"Added synthetic end boundary (gap: {gap_to_end/3600:.1f} hours)")
            elif gap_to_end >= 14400:
                # Gap is too large - data ends early in the day
                # Ensure the last boundary properly ends the segments
                print(f"Data ends early (gap to day end: {gap_to_end/3600:.1f} hours)")
                # The last real boundary is already in all_boundaries
                # No need to add anything else
        else:
            # No boundaries at all - create full day segment
            all_boundaries = [
                {'timestamp': start_of_day, 'confidence': 0.0, 'transition_count': 0, 
                 'source_transitions': [], 'is_synthetic': True},
                {'timestamp': end_of_day, 'confidence': 0.0, 'transition_count': 0,
                 'source_transitions': [], 'is_synthetic': True}
            ]
        
        # Create segments between each pair of boundaries
        segments = []
        for i in range(len(all_boundaries) - 1):
            segment = {
                'segment_index': i,
                'start_time': all_boundaries[i]['timestamp'],
                'end_time': all_boundaries[i+1]['timestamp'],
                'entry_confidence': all_boundaries[i]['confidence'],
                'exit_confidence': all_boundaries[i+1]['confidence'],
                'entry_transition_count': all_boundaries[i]['transition_count'],
                'exit_transition_count': all_boundaries[i+1]['transition_count'],
                'is_edge_segment': i == 0 or i == len(all_boundaries) - 2
            }
            
            # Calculate duration
            duration_seconds = (segment['end_time'] - segment['start_time']).total_seconds()
            segment['duration_minutes'] = duration_seconds / 60
            
            segments.append(segment)
        
        # Don't add segments beyond actual data
        # When data ends early in the day (e.g., 4:38 AM), we should stop there
        # The frontend can handle partial days by showing "no data" for the rest
        
        print(f"Created {len(segments)} segments")
        
        # Clear existing events for this date
        db.execute(
            text("DELETE FROM events WHERE date = :target_date"),
            {"target_date": target_date}
        )
        
        # Phase 6: Calculate segment characteristics and store as events
        events_created = []
        
        for segment in segments:
            # Skip edge segments if they're too short (< 5 minutes)
            if segment['is_edge_segment'] and segment['duration_minutes'] < 5:
                continue
            
            # Find transitions within this segment
            segment_transitions = []
            for t in transitions:
                trans_time = t['transition_time']
                # Ensure consistent timezone handling
                if trans_time.tzinfo is not None:
                    trans_time = trans_time.replace(tzinfo=None)
                if segment['start_time'] <= trans_time < segment['end_time']:
                    segment_transitions.append(t)
            
            # Calculate segment characteristics
            if segment_transitions:
                # Signal contributions
                signal_counts = {}
                for t in segment_transitions:
                    sig_name = t['signal_name']
                    signal_counts[sig_name] = signal_counts.get(sig_name, 0) + 1
                
                # Source diversity
                unique_sources = set(t['source_name'] for t in segment_transitions)
                
                # Confidence statistics
                confidences = [t['confidence'] for t in segment_transitions]
                avg_confidence = np.mean(confidences) if confidences else 0.5
                
                # Activity intensity (transitions per minute)
                activity_intensity = len(segment_transitions) / segment['duration_minutes'] if segment['duration_minutes'] > 0 else 0
                
                # Dominant source
                source_counts = {}
                for t in segment_transitions:
                    src = t['source_name']
                    source_counts[src] = source_counts.get(src, 0) + 1
                dominant_source = max(source_counts.items(), key=lambda x: x[1])[0] if source_counts else None
            else:
                # Segment has no transitions - it's a stable state
                signal_counts = {}
                unique_sources = set()
                avg_confidence = 0.0  # No transitions means no change detected
                activity_intensity = 0.0
                dominant_source = None
            
            # Store segment as event
            event_id = uuid4()
            db.execute(
                text("""
                    INSERT INTO events (
                        id, date, cluster_id, start_time, end_time,
                        core_density, cluster_size, persistence,
                        transition_ids, signal_contributions, event_metadata
                    ) VALUES (
                        :id, :date, :cluster_id, :start_time, :end_time,
                        :core_density, :cluster_size, :persistence,
                        :transition_ids, :signal_contributions, :event_metadata
                    )
                """),
                {
                    "id": event_id,
                    "date": target_date,
                    "cluster_id": segment['segment_index'],
                    "start_time": segment['start_time'],
                    "end_time": segment['end_time'],
                    "core_density": segment['entry_confidence'],  # Use entry boundary confidence
                    "cluster_size": len(segment_transitions),
                    "persistence": segment['duration_minutes'] / (24 * 60),  # Fraction of day
                    "transition_ids": [t['id'] for t in segment_transitions],
                    "signal_contributions": json.dumps(signal_counts),
                    "event_metadata": json.dumps({
                        "segment_type": "continuous",
                        "duration_minutes": segment['duration_minutes'],
                        "is_edge_segment": segment['is_edge_segment'],
                        "entry_confidence": segment['entry_confidence'],
                        "exit_confidence": segment['exit_confidence'],
                        "entry_transition_count": segment['entry_transition_count'],
                        "exit_transition_count": segment['exit_transition_count'],
                        "activity_intensity": activity_intensity,
                        "avg_confidence": avg_confidence,
                        "unique_sources": list(unique_sources),
                        "dominant_source": dominant_source,
                        "has_transitions": len(segment_transitions) > 0,
                        "signal_distribution": signal_counts,
                        "timezone": timezone,
                        "local_date": date
                    })
                }
            )
            
            events_created.append({
                "segment_index": segment['segment_index'],
                "start_time": segment['start_time'].isoformat(),
                "end_time": segment['end_time'].isoformat(),
                "duration_minutes": segment['duration_minutes'],
                "transition_count": len(segment_transitions),
                "activity_intensity": activity_intensity,
                "avg_confidence": avg_confidence
            })
        
        print(f"Stored {len(events_created)} segments as events")
        db.commit()
        
        processing_time_ms = int(
            (datetime.utcnow() - start_process_time).total_seconds() * 1000)
        
        return {
            "success": True,
            "date": str(target_date),
            "timezone": timezone,
            "utc_start": utc_start.isoformat(),
            "utc_end": utc_end.isoformat(),
            "transitions_processed": n_transitions,
            "boundaries_created": len(boundaries),
            "segments_created": len(events_created),
            "processing_time_ms": processing_time_ms,
            "segments": events_created,
            "parameters": {
                "min_cluster_size": min_cluster_size if min_cluster_size else 2,
                "epsilon": epsilon if epsilon else 0.3,
                "target_min_events": scaled_min if 'scaled_min' in locals() else target_min_events,
                "target_max_events": scaled_max if 'scaled_max' in locals() else target_max_events
            },
            "consolidation_stats": {
                "original_transitions": n_transitions,
                "consolidated_boundaries": len(boundaries),
                "reduction_ratio": (n_transitions - len(boundaries)) / n_transitions if n_transitions > 0 else 0
            }
        }
    
    except Exception as e:
        db.rollback()
        error_message = f"{type(e).__name__}: {str(e)}"
        traceback.print_exc()
        return {
            "success": False,
            "error": error_message
        }
    
    finally:
        db.close()
