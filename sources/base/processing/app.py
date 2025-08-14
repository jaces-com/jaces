"""
Processing service FastAPI application
"""
import os
import time
from datetime import datetime, date, timedelta, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4
import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging
import numpy as np
from sqlalchemy import text

from sources.base.storage.database import get_sync_db
from sources.base.processing.signal_analysis import SignalAnalyzer


def merge_correlated_transitions(transitions, window_seconds=30):
    """
    Merge transitions that occur within a time window, keeping the highest weighted.
    
    Args:
        transitions: List of transition dicts
        window_seconds: Time window in seconds to consider transitions correlated
        
    Returns:
        Merged list of transitions
    """
    if len(transitions) <= 1:
        return transitions
    
    # Sort by timestamp
    sorted_transitions = sorted(transitions, key=lambda t: t['transition_time'])
    
    merged = []
    current_group = [sorted_transitions[0]]
    
    for i in range(1, len(sorted_transitions)):
        t = sorted_transitions[i]
        last_time = current_group[-1]['transition_time']
        
        # Check if within correlation window
        time_diff = (t['transition_time'] - last_time).total_seconds()
        
        if time_diff <= window_seconds:
            # Add to current group
            current_group.append(t)
        else:
            # Process current group and start new one
            if current_group:
                # Select representative transition (highest weight × confidence)
                representative = max(
                    current_group,
                    key=lambda x: x.get('macro_weight', 0.5) * x.get('confidence', 0.8)
                )
                
                # Add metadata about merging
                if len(current_group) > 1:
                    representative['correlated_signals'] = [
                        t['signal_name'] for t in current_group
                    ]
                    representative['merged_count'] = len(current_group)
                
                merged.append(representative)
            
            current_group = [t]
    
    # Don't forget the last group
    if current_group:
        representative = max(
            current_group,
            key=lambda x: x.get('macro_weight', 0.5) * x.get('confidence', 0.8)
        )
        
        if len(current_group) > 1:
            representative['correlated_signals'] = [
                t['signal_name'] for t in current_group
            ]
            representative['merged_count'] = len(current_group)
        
        merged.append(representative)
    
    return merged

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="Processing Service", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BoundaryDetectionRequest(BaseModel):
    user_id: str
    start_time: str
    end_time: str
    run_id: Optional[str] = None


class BoundaryDetectionResponse(BaseModel):
    success: bool
    boundaries_count: int
    signals_processed: int
    processing_time_ms: int
    message: str


class TransitionDetectionRequest(BaseModel):
    date: str
    run_type: str = "manual"
    timezone: Optional[str] = None


class TransitionDetectionResponse(BaseModel):
    success: bool
    task_id: Optional[str] = None
    message: str


class EventGenerationRequest(BaseModel):
    date: str
    min_cluster_size: int = 3
    epsilon: float = 300.0


class EventGenerationResponse(BaseModel):
    success: bool
    date: str
    transitions_processed: int
    events_created: int
    clusters_found: int
    noise_points: int
    processing_time_ms: int
    events: List[Dict[str, Any]]
    parameters: Dict[str, Any]


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "processing"}


@app.post("/boundary-detection/run", response_model=BoundaryDetectionResponse)
async def run_signal_analysis(request: BoundaryDetectionRequest):
    """
    Run boundary detection for a specific time range
    """
    start_time = time.time()
    
    try:
        # Parse dates
        user_id = UUID(request.user_id)
        start_dt = datetime.fromisoformat(request.start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(request.end_time.replace('Z', '+00:00'))
        run_id = UUID(request.run_id) if request.run_id else None
        
        # Get database session
        for db in get_sync_db():
            try:
                # Create detector and run
                analyzer = SignalAnalyzer(db)
                transitions = analyzer.detect_transitions(
                    user_id=user_id,
                    start_time=start_dt,
                    end_time=end_dt
                )
                
                # Calculate processing time
                processing_time_ms = int((time.time() - start_time) * 1000)
                
                return BoundaryDetectionResponse(
                    success=True,
                    boundaries_count=len(transitions),
                    signals_processed=0,  # TODO: Track this in detector
                    processing_time_ms=processing_time_ms,
                    message=f"Successfully detected {len(transitions)} transitions"
                )
            finally:
                db.close()
            
    except Exception as e:
        logger.error(f"Error in boundary detection: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/tasks/transition-detection", response_model=TransitionDetectionResponse)
async def trigger_transition_detection(request: TransitionDetectionRequest):
    """
    Trigger transition detection for a specific date
    """
    try:
        # Use direct Redis connection to queue task
        import redis
        import json
        import uuid
        from datetime import datetime
        
        redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
        r = redis.from_url(redis_url)
        
        # Create task message in Celery format
        task_id = str(uuid.uuid4())
        task_message = {
            'id': task_id,
            'task': 'start_transition_detection',
            'args': [
                request.date,
                request.run_type,
                None,  # custom_start_time
                None,  # custom_end_time
                request.timezone
            ],
            'kwargs': {},
            'retries': 0,
            'eta': None,
            'expires': None,
        }
        
        # Queue to Celery's default queue
        r.lpush('celery', json.dumps(task_message))
        
        return TransitionDetectionResponse(
            success=True,
            task_id=task_id,
            message=f"Transition detection queued for {request.date}"
        )
        
    except Exception as e:
        logger.error(f"Error triggering transition detection: {str(e)}")
        return TransitionDetectionResponse(
            success=False,
            task_id=None,
            message=str(e)
        )


@app.post("/api/events/generate", response_model=EventGenerationResponse)
async def generate_events(request: EventGenerationRequest):
    """
    Generate day events using HDBSCAN clustering on transitions
    """
    start_time = time.time()
    
    try:
        # Import HDBSCAN
        try:
            import hdbscan
        except ImportError:
            raise HTTPException(
                status_code=500, 
                detail="HDBSCAN not installed. Run: pip install hdbscan"
            )
        
        # Parse date
        target_date = datetime.fromisoformat(request.date).date()
        
        # Get database session
        for db in get_sync_db():
            try:
                # Get all transitions for the day
                result = db.execute(
                    text("""
                        SELECT 
                            id, source_name, signal_name, transition_time,
                            transition_type, change_magnitude, change_direction,
                            before_mean, after_mean, confidence, detection_method,
                            transition_metadata
                        FROM signal_transitions
                        WHERE DATE(transition_time) = :target_date
                        ORDER BY transition_time
                    """),
                    {"target_date": target_date}
                )
                
                transitions = [dict(row._mapping) for row in result]
                
                if len(transitions) < request.min_cluster_size:
                    return EventGenerationResponse(
                        success=False,
                        date=str(target_date),
                        transitions_processed=len(transitions),
                        events_created=0,
                        clusters_found=0,
                        noise_points=0,
                        processing_time_ms=int((time.time() - start_time) * 1000),
                        events=[],
                        parameters={
                            "min_cluster_size": request.min_cluster_size,
                            "epsilon": request.epsilon
                        }
                    )
                
                # Get macro weights for signals
                signal_weights = {}
                result = db.execute(
                    text("""
                        SELECT signal_name, macro_weight 
                        FROM signal_configs 
                        WHERE macro_weight IS NOT NULL
                    """)
                )
                for row in result:
                    signal_weights[row.signal_name] = row.macro_weight
                
                # Add weights to transitions
                for t in transitions:
                    if t.get('signal_name') in signal_weights:
                        t['macro_weight'] = signal_weights[t['signal_name']]
                    elif t.get('detection_method') == 'synthetic':
                        # Already set in synthetic transitions
                        pass
                    else:
                        t['macro_weight'] = 0.5  # Default weight
                
                # Merge correlated transitions (within 30 seconds)
                transitions = merge_correlated_transitions(transitions)
                
                # Add synthetic transitions at day boundaries
                # Create UTC-aware boundaries, then convert to naive for consistency
                start_of_day = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc).replace(tzinfo=None)
                end_of_day = datetime.combine(target_date, datetime.max.time(), tzinfo=timezone.utc).replace(tzinfo=None)
                
                # Ensure all transitions have consistent timezone handling (naive UTC)
                for t in transitions:
                    if hasattr(t['transition_time'], 'tzinfo') and t['transition_time'].tzinfo is not None:
                        # Convert to naive datetime if it has timezone info
                        t['transition_time'] = t['transition_time'].replace(tzinfo=None)
                
                # Check if we already have transitions at day boundaries
                has_start = any(t['transition_time'].time() == datetime.min.time() for t in transitions)
                has_end = any(t['transition_time'].time() == datetime.max.time() for t in transitions)
                
                # Add synthetic transitions if needed
                if not has_start:
                    transitions.insert(0, {
                        'id': uuid4(),
                        'source_name': 'system',
                        'signal_name': 'day_boundary',
                        'transition_time': start_of_day,
                        'from_state': 'previous_day',
                        'to_state': 'new_day',
                        'confidence': 1.0,
                        'detection_method': 'synthetic',
                        'transition_metadata': {'type': 'day_start'},
                        'macro_weight': 1.0  # Day boundaries are always important
                    })
                
                if not has_end:
                    transitions.append({
                        'id': uuid4(),
                        'source_name': 'system',
                        'signal_name': 'day_boundary',
                        'transition_time': end_of_day,
                        'from_state': 'current_day',
                        'to_state': 'next_day',
                        'confidence': 1.0,
                        'detection_method': 'synthetic',
                        'transition_metadata': {'type': 'day_end'},
                        'macro_weight': 1.0  # Day boundaries are always important
                    })
                
                # Prepare features for HDBSCAN
                timestamps = np.array([
                    (t['transition_time'] - start_of_day).total_seconds() 
                    for t in transitions
                ]).reshape(-1, 1)
                
                # Use weighted confidence (confidence × macro_weight)
                weighted_confidences = np.array([
                    t.get('confidence', 0.8) * t.get('macro_weight', 0.5) * 100
                    for t in transitions
                ]).reshape(-1, 1)
                
                features = np.hstack([timestamps, weighted_confidences])
                
                # Run HDBSCAN
                clusterer = hdbscan.HDBSCAN(
                    min_cluster_size=request.min_cluster_size,
                    min_samples=2,
                    metric='manhattan',
                    cluster_selection_epsilon=request.epsilon,
                    algorithm='best'
                )
                
                cluster_labels = clusterer.fit_predict(features)
                
                # Extract cluster information
                n_clusters = len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
                n_noise = list(cluster_labels).count(-1)
                
                # Clear existing events for this date
                db.execute(
                    text("DELETE FROM events WHERE date = :target_date"),
                    {"target_date": target_date}
                )
                
                # Process each cluster
                events_to_create = []
                for cluster_id in set(cluster_labels):
                    if cluster_id == -1:  # Skip noise points
                        continue
                        
                    # Get transitions in this cluster
                    cluster_mask = cluster_labels == cluster_id
                    cluster_transitions = [t for i, t in enumerate(transitions) if cluster_mask[i]]
                    
                    if not cluster_transitions:
                        continue
                    
                    # Skip synthetic day boundary transitions from event creation
                    # They're only used to influence clustering
                    cluster_transitions = [t for t in cluster_transitions if t.get('detection_method') != 'synthetic']
                    
                    if not cluster_transitions:  # If only synthetic transitions in cluster, skip
                        continue
                    
                    # Calculate cluster properties
                    start_time_cluster = min(t['transition_time'] for t in cluster_transitions)
                    end_time_cluster = max(t['transition_time'] for t in cluster_transitions)
                    
                    # Ensure minimum duration of 15 minutes
                    min_duration = timedelta(minutes=15)
                    if end_time_cluster - start_time_cluster < min_duration:
                        end_time_cluster = start_time_cluster + min_duration
                    
                    core_density = float(clusterer.probabilities_[cluster_mask].mean())
                    
                    # Get signal contributions
                    signal_counts = {}
                    for t in cluster_transitions:
                        sig_name = t['signal_name']
                        signal_counts[sig_name] = signal_counts.get(sig_name, 0) + 1
                    
                    events_to_create.append({
                        "id": uuid4(),
                        "date": target_date,
                        "cluster_id": int(cluster_id),
                        "start_time": start_time_cluster,
                        "end_time": end_time_cluster,
                        "core_density": core_density,
                        "cluster_size": len(cluster_transitions),
                        "persistence": float(clusterer.cluster_persistence_[cluster_id]) if hasattr(clusterer, 'cluster_persistence_') else None,
                        "transition_ids": [t['id'] for t in cluster_transitions if isinstance(t['id'], UUID)],  # Only include real UUIDs
                        "signal_contributions": json.dumps(signal_counts),
                        "event_metadata": json.dumps({
                            "duration_minutes": (end_time_cluster - start_time_cluster).total_seconds() / 60,
                            "avg_confidence": np.mean([t['confidence'] for t in cluster_transitions])
                        })
                    })
                
                # Sort events by start time
                events_to_create.sort(key=lambda e: e["start_time"])
                
                # Validate temporal integrity - ensure no overlaps
                for i in range(len(events_to_create) - 1):
                    current_event = events_to_create[i]
                    next_event = events_to_create[i + 1]
                    
                    # If current event ends after next event starts, trim current event
                    if current_event["end_time"] > next_event["start_time"]:
                        # Set end time to 1 second before next event starts
                        current_event["end_time"] = next_event["start_time"] - timedelta(seconds=1)
                        
                        # Update metadata
                        metadata = json.loads(current_event["event_metadata"])
                        metadata["duration_minutes"] = (current_event["end_time"] - current_event["start_time"]).total_seconds() / 60
                        metadata["trimmed"] = True
                        current_event["event_metadata"] = json.dumps(metadata)
                
                # Add unknown events for gaps
                all_events = []
                
                # First, add all clustered events
                for event in events_to_create:
                    event["event_type"] = "activity"
                    all_events.append(event)
                
                # Sort by start time
                all_events.sort(key=lambda e: e["start_time"])
                
                # Find gaps and create unknown events
                unknown_events = []
                
                # If no events at all, create one unknown event for the whole day
                if not all_events:
                    unknown_events.append({
                        "id": uuid4(),
                        "date": target_date,
                        "cluster_id": -1,
                        "start_time": start_of_day,
                        "end_time": end_of_day,
                        "core_density": 0.0,
                        "cluster_size": 0,
                        "persistence": None,
                        "transition_ids": [],
                        "signal_contributions": json.dumps({}),
                        "event_metadata": json.dumps({
                            "duration_minutes": 1440,  # 24 hours
                            "type": "unknown_period",
                            "reason": "no_events"
                        }),
                        "event_type": "unknown"
                    })
                # Check gap at start of day
                elif (all_events[0]["start_time"] - start_of_day).total_seconds() > 60:  # 1 minute gap
                    unknown_events.append({
                        "id": uuid4(),
                        "date": target_date,
                        "cluster_id": -1,  # Special ID for unknown
                        "start_time": start_of_day,
                        "end_time": all_events[0]["start_time"],
                        "core_density": 0.0,
                        "cluster_size": 0,
                        "persistence": None,
                        "transition_ids": [],
                        "signal_contributions": json.dumps({}),
                        "event_metadata": json.dumps({
                            "duration_minutes": (all_events[0]["start_time"] - start_of_day).total_seconds() / 60,
                            "type": "unknown_period",
                            "reason": "no_data"
                        }),
                        "event_type": "unknown"
                    })
                
                # Check gaps between events
                for i in range(len(all_events) - 1):
                    gap_start = all_events[i]["end_time"]
                    gap_end = all_events[i + 1]["start_time"]
                    gap_duration = (gap_end - gap_start).total_seconds()
                    
                    if gap_duration > 60:  # 1 minute gap - ensure no gaps
                        unknown_events.append({
                            "id": uuid4(),
                            "date": target_date,
                            "cluster_id": -1,
                            "start_time": gap_start,
                            "end_time": gap_end,
                            "core_density": 0.0,
                            "cluster_size": 0,
                            "persistence": None,
                            "transition_ids": [],
                            "signal_contributions": json.dumps({}),
                            "event_metadata": json.dumps({
                                "duration_minutes": gap_duration / 60,
                                "type": "unknown_period",
                                "reason": "data_gap"
                            }),
                            "event_type": "unknown"
                        })
                
                # Check gap at end of day
                if all_events and (end_of_day - all_events[-1]["end_time"]).total_seconds() > 60:
                    unknown_events.append({
                        "id": uuid4(),
                        "date": target_date,
                        "cluster_id": -1,
                        "start_time": all_events[-1]["end_time"],
                        "end_time": end_of_day,
                        "core_density": 0.0,
                        "cluster_size": 0,
                        "persistence": None,
                        "transition_ids": [],
                        "signal_contributions": json.dumps({}),
                        "event_metadata": json.dumps({
                            "duration_minutes": (end_of_day - all_events[-1]["end_time"]).total_seconds() / 60,
                            "type": "unknown_period",
                            "reason": "no_data"
                        }),
                        "event_type": "unknown"
                    })
                
                # Add unknown events to all events
                all_events.extend(unknown_events)
                all_events.sort(key=lambda e: e["start_time"])
                
                # Store all events
                events_created = []
                for event in all_events:
                    db.execute(
                        text("""
                            INSERT INTO events (
                                id, date, cluster_id, start_time, end_time,
                                core_density, cluster_size, persistence,
                                transition_ids, signal_contributions, event_metadata, event_type
                            ) VALUES (
                                :id, :date, :cluster_id, :start_time, :end_time,
                                :core_density, :cluster_size, :persistence,
                                :transition_ids, :signal_contributions, :event_metadata, :event_type
                            )
                        """),
                        event
                    )
                    
                    events_created.append({
                        "cluster_id": event["cluster_id"],
                        "start_time": event["start_time"].isoformat(),
                        "end_time": event["end_time"].isoformat(),
                        "size": event["cluster_size"],
                        "type": event["event_type"]
                    })
                
                db.commit()
                
                processing_time_ms = int((time.time() - start_time) * 1000)
                
                # Count event types
                activity_events = [e for e in events_created if e["type"] == "activity"]
                unknown_events_count = [e for e in events_created if e["type"] == "unknown"]
                
                return EventGenerationResponse(
                    success=True,
                    date=str(target_date),
                    transitions_processed=len(transitions),
                    events_created=len(events_created),
                    clusters_found=n_clusters,
                    noise_points=n_noise,
                    processing_time_ms=processing_time_ms,
                    events=events_created,
                    parameters={
                        "min_cluster_size": request.min_cluster_size,
                        "epsilon": request.epsilon,
                        "activity_events": len(activity_events),
                        "unknown_events": len(unknown_events_count)
                    }
                )
                
            finally:
                db.close()
                
    except Exception as e:
        logger.error(f"Error in event generation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)