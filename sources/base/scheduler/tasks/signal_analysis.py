"""Celery tasks for signal analysis (transition detection only)."""

from celery.schedules import crontab
import traceback
import json
import importlib
from datetime import datetime, timedelta, time
from typing import Dict, Any, List, Optional
from uuid import uuid4
import numpy as np

import pytz
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from sources.base.scheduler.celery_app import app
from sources.base.storage.database import get_sync_db, sync_engine
from sources._generated_registry import TRANSITION_DETECTORS

# Create session factory using the centralized engine
Session = sessionmaker(bind=sync_engine)

# Transition detectors are now imported from generated registry
# The registry maps signal names to their detector classes


@app.task(name="start_transition_detection", bind=True,
          autoretry_for=(Exception,), retry_kwargs={'max_retries': 3})
def start_transition_detection(
    self,
    user_id: str,
    date: str,
    run_type: str = "manual",
    custom_start_time: Optional[str] = None,
    custom_end_time: Optional[str] = None,
    timezone: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run transition detection for ambient signals for a specific date or custom time range.

    Args:
        user_id: User UUID
        date: Either ISO date (2024-12-15) or keyword ('yesterday', 'today')
        run_type: 'manual' or 'scheduled' for tracking
        custom_start_time: Optional ISO datetime string for custom start (overrides date)
        custom_end_time: Optional ISO datetime string for custom end (overrides date)
        timezone: User's timezone (e.g., 'America/Chicago'). If not provided, fetched from user record

    Returns:
        Dict with results including transition counts and processing time
    """
    db = Session()
    start_process_time = datetime.utcnow()

    try:
        # Get user's timezone if not provided
        if timezone is None:
            result = db.execute(
                text("SELECT timezone FROM users WHERE id = :user_id"),
                {"user_id": user_id}
            )
            user_record = result.fetchone()
            if user_record:
                timezone = user_record[0]
            else:
                timezone = 'America/Chicago'  # Default fallback

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
        signals_result = db.execute(
            text("""
                SELECT id, source_name, signal_name, computation, 
                       fidelity_score, description, macro_weight, min_transition_gap
                FROM signal_configs
                WHERE status = 'active'
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

            # Check if this signal has a transition detector
            if source_signal_key in TRANSITION_DETECTORS:
                # Import the detector dynamically
                detector_path = TRANSITION_DETECTORS[source_signal_key]
                module_path, class_name = detector_path.rsplit('.', 1)
                module = importlib.import_module(module_path)
                detector_class = getattr(module, class_name)
                
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

                    # Store signal-level transitions in signal_transitions table
                    for transition in transitions:
                        _store_signal_transition(
                            db, signal['source_name'],
                            signal['signal_name'], transition
                        )
            else:
                print(f"No transition detector found for {source_signal_key}")

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
                timestamp, confidence, source_event_id, source_metadata,
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
                timestamp, confidence, source_event_id, source_metadata,
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
            (id, source_name, signal_name, transition_time,
             from_state, to_state, confidence, detection_method, transition_metadata, created_at)
            VALUES
            (:id, :source_name, :signal_name, :transition_time,
             :from_state, :to_state, :confidence, :detection_method, :transition_metadata, :created_at)
        """),
        {
            "id": transition_dict["id"],
            "source_name": source_name,
            "signal_name": signal_name,
            "transition_time": transition_dict["transition_time"],
            "from_state": transition_dict.get("from_state"),
            "to_state": transition_dict["to_state"],
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
    user_id: str,
    signal_name: str,
    date: str,
    start_time: str,
    end_time: str,
    timezone: str = "America/Chicago"
) -> Dict[str, Any]:
    """
    Run transition detection for a single specific ambient signal.

    Args:
        user_id: User UUID
        signal_name: The specific signal to process (e.g., 'ios_speed')
        date: ISO date string (2025-07-23)
        start_time: ISO datetime string for start
        end_time: ISO datetime string for end
        timezone: User's timezone

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
        print(f"[TransitionDetection] User ID: {user_id}")
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
                "error": f"Signal {signal_name} not found or not active for user {user_id}"
            }

        signal = dict(signal_record._mapping)
        # Parse computation JSON if it's a string
        if isinstance(signal.get('computation'), str):
            signal['computation'] = json.loads(signal['computation'])
        print(f"[TransitionDetection] Found signal: {signal}")

        # Check if transition detector exists
        if signal_name not in TRANSITION_DETECTORS:
            return {
                "success": False,
                "error": f"No transition detector available for signal {signal_name}. Available: {list(TRANSITION_DETECTORS.keys())}"
            }

        # Get signal data
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

        # Use transition detector - import dynamically
        detector_path = TRANSITION_DETECTORS[signal_name]
        module_path, class_name = detector_path.rsplit('.', 1)
        module = importlib.import_module(module_path)
        detector_class = getattr(module, class_name)
        
        # Pass the full signal config to the detector
        detector = detector_class(config=signal)

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


# Note: This function is deprecated - the system no longer uses user_id
# @app.task(name="run_daily_transition_detection")
# def run_daily_transition_detection():
#     """Run transition detection for all active users for yesterday."""
#     db = Session()
#
#     try:
#         # Get all users with active signals
#         result = db.execute(
#             text("""
#                 SELECT DISTINCT user_id
#                 FROM signals
#                 WHERE status = 'active'
#             """)
#         )
#
#         user_ids = [row[0] for row in result]
#
#         # Queue transition detection for each user
#         for user_id in user_ids:
#             start_transition_detection.delay(
#                 user_id=str(user_id),
#                 date='yesterday',
#                 run_type='scheduled'
#             )
#
#         return {
#             "success": True,
#             "users_queued": len(user_ids)
#         }
#
#     finally:
#         db.close()

@app.task(name="generate_events_hdbscan", bind=True,
          autoretry_for=(Exception,), retry_kwargs={'max_retries': 3})
def generate_events_hdbscan(
    self,
    date: str,
    min_cluster_size: int = 3,
    epsilon: float = 300.0
) -> Dict[str, Any]:
    """
    Generate day events using HDBSCAN clustering on transitions.

    Args:
        date: ISO date string (2025-01-15)
        min_cluster_size: Minimum cluster size for HDBSCAN
        epsilon: Epsilon parameter for HDBSCAN (in seconds)

    Returns:
        Dict with clustering results
    """
    db = Session()
    start_process_time = datetime.utcnow()

    try:
        # Import HDBSCAN here to avoid dependency issues
        try:
            import hdbscan
        except ImportError:
            return {
                "success": False,
                "error": "HDBSCAN not installed. Run: pip install hdbscan"
            }

        # Parse date
        target_date = datetime.fromisoformat(date).date()

        # Get all transitions for the day
        result = db.execute(
            text("""
                SELECT 
                    id, source_name, signal_name, transition_time,
                    from_state, to_state, confidence, detection_method,
                    transition_metadata
                FROM signal_transitions
                WHERE DATE(transition_time) = :target_date
                ORDER BY transition_time
            """),
            {"target_date": target_date}
        )

        transitions = [dict(row._mapping) for row in result]

        if len(transitions) < min_cluster_size:
            return {
                "success": False,
                "error": f"Not enough transitions ({len(transitions)}) for clustering. Need at least {min_cluster_size}."
            }

        # Prepare features for HDBSCAN
        # Primary feature: time as seconds since midnight
        start_of_day = datetime.combine(target_date, time.min)
        timestamps = np.array([
            (t['transition_time'] - start_of_day).total_seconds()
            for t in transitions
        ]).reshape(-1, 1)

        # Secondary feature: confidence scores (weighted)
        confidences = np.array([
            t['confidence'] * 100  # Scale confidence to similar range as time
            for t in transitions
        ]).reshape(-1, 1)

        # Combine features
        features = np.hstack([timestamps, confidences])

        # Run HDBSCAN
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            min_samples=2,
            metric='manhattan',  # Better for temporal data
            cluster_selection_epsilon=epsilon,
            algorithm='best'
        )

        cluster_labels = clusterer.fit_predict(features)

        # Extract cluster information
        n_clusters = len(set(cluster_labels)) - \
            (1 if -1 in cluster_labels else 0)
        n_noise = list(cluster_labels).count(-1)

        # Clear existing events for this date
        db.execute(
            text("DELETE FROM events WHERE date = :target_date"),
            {"target_date": target_date}
        )

        # Process each cluster
        events_created = []
        for cluster_id in set(cluster_labels):
            if cluster_id == -1:  # Skip noise points
                continue

            # Get transitions in this cluster
            cluster_mask = cluster_labels == cluster_id
            cluster_transitions = [t for i, t in enumerate(
                transitions) if cluster_mask[i]]

            if not cluster_transitions:
                continue

            # Calculate cluster properties
            start_time = min(t['transition_time'] for t in cluster_transitions)
            end_time = max(t['transition_time'] for t in cluster_transitions)
            core_density = float(clusterer.probabilities_[cluster_mask].mean())

            # Get signal contributions
            signal_counts = {}
            for t in cluster_transitions:
                sig_name = t['signal_name']
                signal_counts[sig_name] = signal_counts.get(sig_name, 0) + 1

            # Store event
            event_id = uuid4()
            db.execute(
                text("""
                    INSERT INTO events (
                        id, date, cluster_id, start_time, end_time,
                        core_density, cluster_size, persistence,
                        transition_ids, signal_contributions, metadata
                    ) VALUES (
                        :id, :date, :cluster_id, :start_time, :end_time,
                        :core_density, :cluster_size, :persistence,
                        :transition_ids, :signal_contributions, :metadata
                    )
                """),
                {
                    "id": event_id,
                    "date": target_date,
                    "cluster_id": int(cluster_id),
                    "start_time": start_time,
                    "end_time": end_time,
                    "core_density": core_density,
                    "cluster_size": len(cluster_transitions),
                    "persistence": float(clusterer.cluster_persistence_[cluster_id]) if hasattr(clusterer, 'cluster_persistence_') else None,
                    "transition_ids": [t['id'] for t in cluster_transitions],
                    "signal_contributions": signal_counts,
                    "metadata": {
                        "duration_minutes": (end_time - start_time).total_seconds() / 60,
                        "avg_confidence": np.mean([t['confidence'] for t in cluster_transitions])
                    }
                }
            )

            events_created.append({
                "cluster_id": int(cluster_id),
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "size": len(cluster_transitions)
            })

        db.commit()

        processing_time_ms = int(
            (datetime.utcnow() - start_process_time).total_seconds() * 1000)

        return {
            "success": True,
            "date": str(target_date),
            "transitions_processed": len(transitions),
            "events_created": len(events_created),
            "clusters_found": n_clusters,
            "noise_points": n_noise,
            "processing_time_ms": processing_time_ms,
            "events": events_created,
            "parameters": {
                "min_cluster_size": min_cluster_size,
                "epsilon": epsilon
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
