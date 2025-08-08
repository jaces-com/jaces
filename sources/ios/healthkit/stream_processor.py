"""Stream processor for iOS HealthKit data."""

import json
from datetime import datetime, timezone as tz
from typing import Dict, Any, List
from uuid import uuid4
from sqlalchemy import text
from sources.base.processing.dedup import generate_source_event_id


class HealthKitStreamProcessor:
    """Processes HealthKit stream data and splits into individual signals."""
    
    def __init__(self):
        self.source_name = "ios"
    
    def process(
        self,
        stream_data: Dict[str, Any],
        signal_configs: Dict[str, str],
        db
    ) -> Dict[str, Any]:
        """
        Process HealthKit stream batch.
        
        Args:
            stream_data: Raw stream data from MinIO
            signal_configs: Mapping of signal names to signal IDs
            db: Database session
            
        Returns:
            Processing result with counts
        """
        print(f"Processing HealthKit stream")
        
        # Extract data array from stream
        data = stream_data.get('data', [])
        device_id = stream_data.get('device_id')
        
        # Group metrics by type
        metrics_by_type = {
            'heart_rate': [],
            'steps': [],
            'sleep': [],
            'active_energy': [],
            'workouts': [],
            'heart_rate_variability': []
        }
        
        # Sort metrics into appropriate buckets
        for metric in data:
            metric_type = metric.get('metric_type')
            if metric_type in metrics_by_type:
                metrics_by_type[metric_type].append(metric)
        
        # Process each metric type
        signals_created = {}
        
        # Heart Rate
        if metrics_by_type['heart_rate'] and 'apple_ios_heart_rate' in signal_configs:
            count = self._process_heart_rate(
                metrics_by_type['heart_rate'],
                signal_configs['apple_ios_heart_rate'],
                device_id,
                db
            )
            signals_created['heart_rate'] = count
        
        # Steps
        if metrics_by_type['steps'] and 'apple_ios_steps' in signal_configs:
            count = self._process_steps(
                metrics_by_type['steps'],
                signal_configs['apple_ios_steps'],
                device_id,
                db
            )
            signals_created['steps'] = count
        
        # Sleep
        if metrics_by_type['sleep'] and 'apple_ios_sleep' in signal_configs:
            count = self._process_sleep(
                metrics_by_type['sleep'],
                signal_configs['apple_ios_sleep'],
                device_id,
                db
            )
            signals_created['sleep'] = count
        
        # Active Energy
        if metrics_by_type['active_energy'] and 'apple_ios_active_energy' in signal_configs:
            count = self._process_active_energy(
                metrics_by_type['active_energy'],
                signal_configs['apple_ios_active_energy'],
                device_id,
                db
            )
            signals_created['active_energy'] = count
        
        # Workouts
        if metrics_by_type['workouts'] and 'apple_ios_workouts' in signal_configs:
            count = self._process_workouts(
                metrics_by_type['workouts'],
                signal_configs['apple_ios_workouts'],
                device_id,
                db
            )
            signals_created['workouts'] = count
        
        # Heart Rate Variability
        if metrics_by_type['heart_rate_variability'] and 'apple_ios_heart_rate_variability' in signal_configs:
            count = self._process_hrv(
                metrics_by_type['heart_rate_variability'],
                signal_configs['apple_ios_heart_rate_variability'],
                device_id,
                db
            )
            signals_created['heart_rate_variability'] = count
        
        db.commit()
        
        total_created = sum(signals_created.values())
        print(f"Created {total_created} ambient signals from HealthKit data")
        print(f"Breakdown: {signals_created}")
        
        return {
            "status": "success",
            "stream_name": "apple_ios_healthkit",
            "records_processed": len(data),
            "signals_created": {
                f"apple_ios_{key}": count for key, count in signals_created.items()
            },
            "total_signals": total_created
        }
    
    def _process_heart_rate(
        self,
        metrics: List[Dict[str, Any]],
        signal_id: str,
        
        device_id: str,
        db
    ) -> int:
        """Process heart rate metrics."""
        count = 0
        
        for metric in metrics:
            # Parse timestamp first (needed for source_event_id)
            timestamp_str = metric['timestamp']
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            if timestamp.tzinfo:
                timestamp = timestamp.astimezone(tz.utc)
            else:
                timestamp = timestamp.replace(tzinfo=tz.utc)
            
            # Generate deterministic source event ID
            source_event_id = generate_source_event_id('continuous', timestamp, metric)
            
            # Extract metadata
            metadata = metric.get('metadata', {})
            activity_context = metadata.get('activity_context', 'unknown')
            
            # Calculate confidence based on activity context
            # Higher confidence for resting measurements
            confidence = 0.95
            if activity_context == 'resting':
                confidence = 0.98
            elif activity_context == 'exercising':
                confidence = 0.90
            
            # Build source metadata
            source_metadata = {
                'device_id': device_id,
                'activity_context': activity_context,
                'bpm': metric['value']
            }
            
            # Insert ambient signal
            db.execute(
                text("""
                    INSERT INTO signals 
                    (id,  signal_id, source_name, timestamp, 
                     confidence, signal_name, signal_value, source_event_id, 
                     source_metadata, created_at, updated_at)
                    VALUES (:id, :signal_id, :source_name, :timestamp, 
                            :confidence, :signal_name, :signal_value, :source_event_id, 
                            :source_metadata, :created_at, :updated_at)
                    ON CONFLICT (source_name, source_event_id, signal_name) DO NOTHING
                """),
                {
                    "id": str(uuid4()),
                    "signal_id": signal_id,
                    "source_name": self.source_name,
                    "timestamp": timestamp,
                    "confidence": confidence,
                    "signal_name": "apple_ios_heart_rate",
                    "signal_value": str(metric['value']),
                    "source_event_id": source_event_id,
                    "source_metadata": json.dumps(source_metadata),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            )
            count += 1
        
        return count
    
    def _process_steps(
        self,
        metrics: List[Dict[str, Any]],
        signal_id: str,
        
        device_id: str,
        db
    ) -> int:
        """Process step count metrics."""
        count = 0
        
        for metric in metrics:
            # Parse timestamp first (needed for source_event_id)
            timestamp_str = metric['timestamp']
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            if timestamp.tzinfo:
                timestamp = timestamp.astimezone(tz.utc)
            else:
                timestamp = timestamp.replace(tzinfo=tz.utc)
            
            # Generate deterministic source event ID (steps are count type)
            source_event_id = generate_source_event_id('count', timestamp, metric)
            
            # Extract metadata
            metadata = metric.get('metadata', {})
            
            # Fixed high confidence for step data
            confidence = 0.95
            
            # Build source metadata
            source_metadata = {
                'device_id': device_id,
                'step_count': metric['value'],
                'period': metadata.get('period', 'hourly')
            }
            
            # Insert ambient signal
            db.execute(
                text("""
                    INSERT INTO signals 
                    (id,  signal_id, source_name, timestamp, 
                     confidence, signal_name, signal_value, source_event_id, 
                     source_metadata, created_at, updated_at)
                    VALUES (:id, :signal_id, :source_name, :timestamp, 
                            :confidence, :signal_name, :signal_value, :source_event_id, 
                            :source_metadata, :created_at, :updated_at)
                    ON CONFLICT (source_name, source_event_id, signal_name) DO NOTHING
                """),
                {
                    "id": str(uuid4()),
                    "signal_id": signal_id,
                    "source_name": self.source_name,
                    "timestamp": timestamp,
                    "confidence": confidence,
                    "signal_name": "apple_ios_steps",
                    "signal_value": str(metric['value']),
                    "source_event_id": source_event_id,
                    "source_metadata": json.dumps(source_metadata),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            )
            count += 1
        
        return count
    
    def _process_sleep(
        self,
        metrics: List[Dict[str, Any]],
        signal_id: str,
        
        device_id: str,
        db
    ) -> int:
        """Process sleep metrics as ambient signals."""
        count = 0
        
        # Map HealthKit sleep states - use native iOS values
        sleep_state_mapping = {
            'in_bed': 'in_bed',
            'awake': 'awake',
            'asleep': 'asleep',  # asleepUnspecified
            'asleep_core': 'asleep_core',
            'asleep_deep': 'asleep_deep',
            'asleep_rem': 'asleep_rem',
            'unknown': 'unknown'
        }
        
        for metric in metrics:
            # Parse timestamp first (needed for source_event_id)
            timestamp_str = metric['timestamp']
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            if timestamp.tzinfo:
                timestamp = timestamp.astimezone(tz.utc)
            else:
                timestamp = timestamp.replace(tzinfo=tz.utc)
            
            # Generate deterministic source event ID (sleep is categorical)
            source_event_id = generate_source_event_id('categorical', timestamp, metric)
            
            # Extract metadata
            metadata = metric.get('metadata', {})
            raw_sleep_state = metadata.get('sleep_state', 'unknown')
            # Map to our standard states
            sleep_state = sleep_state_mapping.get(raw_sleep_state, raw_sleep_state.lower())
            duration_minutes = metadata.get('duration_minutes', 0)
            
            # Calculate confidence based on data completeness
            confidence = 0.90
            if sleep_state != 'unknown' and duration_minutes > 0:
                confidence = 0.95
            
            # Build source metadata
            source_metadata = {
                'device_id': device_id,
                'sleep_state': sleep_state,
                'raw_sleep_state': raw_sleep_state,  # Keep original for debugging
                'duration_minutes': duration_minutes,
                'state_value': metric['value']
            }
            
            # Insert ambient signal
            db.execute(
                text("""
                    INSERT INTO signals 
                    (id,  signal_id, source_name, timestamp, 
                     confidence, signal_name, signal_value, source_event_id, 
                     source_metadata, created_at, updated_at)
                    VALUES (:id, :signal_id, :source_name, :timestamp, 
                            :confidence, :signal_name, :signal_value, :source_event_id, 
                            :source_metadata, :created_at, :updated_at)
                    ON CONFLICT (source_name, source_event_id, signal_name) DO NOTHING
                """),
                {
                    "id": str(uuid4()),
                    "signal_id": signal_id,
                    "source_name": self.source_name,
                    "timestamp": timestamp,
                    "confidence": confidence,
                    "signal_name": "apple_ios_sleep",
                    "signal_value": sleep_state,
                    "source_event_id": source_event_id,
                    "source_metadata": json.dumps(source_metadata),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            )
            count += 1
        
        return count
    
    def _process_active_energy(
        self,
        metrics: List[Dict[str, Any]],
        signal_id: str,
        
        device_id: str,
        db
    ) -> int:
        """Process active energy metrics."""
        count = 0
        
        for metric in metrics:
            # Parse timestamp first (needed for source_event_id)
            timestamp_str = metric['timestamp']
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            if timestamp.tzinfo:
                timestamp = timestamp.astimezone(tz.utc)
            else:
                timestamp = timestamp.replace(tzinfo=tz.utc)
            
            # Generate deterministic source event ID (active energy is count type)
            source_event_id = generate_source_event_id('count', timestamp, metric)
            
            # Extract metadata
            metadata = metric.get('metadata', {})
            
            # Fixed confidence for energy data
            confidence = 0.95
            
            # Build source metadata
            source_metadata = {
                'device_id': device_id,
                'kcal': metric['value'],
                'activity_type': metadata.get('activity_type', 'unknown')
            }
            
            # Insert ambient signal
            db.execute(
                text("""
                    INSERT INTO signals 
                    (id,  signal_id, source_name, timestamp, 
                     confidence, signal_name, signal_value, source_event_id, 
                     source_metadata, created_at, updated_at)
                    VALUES (:id, :signal_id, :source_name, :timestamp, 
                            :confidence, :signal_name, :signal_value, :source_event_id, 
                            :source_metadata, :created_at, :updated_at)
                    ON CONFLICT (source_name, source_event_id, signal_name) DO NOTHING
                """),
                {
                    "id": str(uuid4()),
                    "signal_id": signal_id,
                    "source_name": self.source_name,
                    "timestamp": timestamp,
                    "confidence": confidence,
                    "signal_name": "apple_ios_active_energy",
                    "signal_value": str(metric['value']),
                    "source_event_id": source_event_id,
                    "source_metadata": json.dumps(source_metadata),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            )
            count += 1
        
        return count
    
    def _process_workouts(
        self,
        metrics: List[Dict[str, Any]],
        signal_id: str,
        
        device_id: str,
        db
    ) -> int:
        """Process workout metrics as ambient signals."""
        count = 0
        
        for metric in metrics:
            # Parse timestamp first (needed for source_event_id)
            timestamp_str = metric['timestamp']
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            if timestamp.tzinfo:
                timestamp = timestamp.astimezone(tz.utc)
            else:
                timestamp = timestamp.replace(tzinfo=tz.utc)
            
            # Generate deterministic source event ID (workouts are parallel type)
            source_event_id = generate_source_event_id('parallel', timestamp, metric)
            
            # Extract metadata
            metadata = metric.get('metadata', {})
            workout_type = metadata.get('workout_type', 'unknown')
            end_date = metadata.get('end_date')
            total_energy = metadata.get('total_energy', 0)
            
            # Calculate confidence based on data completeness
            confidence = 0.90
            if workout_type != 'unknown' and end_date:
                confidence = 0.95
            
            # Build source metadata
            source_metadata = {
                'device_id': device_id,
                'workout_type': workout_type,
                'duration_minutes': metric['value'],
                'total_energy': total_energy
            }
            
            if end_date:
                source_metadata['end_date'] = end_date
            
            # Insert ambient signal
            db.execute(
                text("""
                    INSERT INTO signals 
                    (id,  signal_id, source_name, timestamp, 
                     confidence, signal_name, signal_value, source_event_id, 
                     source_metadata, created_at, updated_at)
                    VALUES (:id, :signal_id, :source_name, :timestamp, 
                            :confidence, :signal_name, :signal_value, :source_event_id, 
                            :source_metadata, :created_at, :updated_at)
                    ON CONFLICT (source_name, source_event_id, signal_name) DO NOTHING
                """),
                {
                    "id": str(uuid4()),
                    "signal_id": signal_id,
                    "source_name": self.source_name,
                    "timestamp": timestamp,
                    "confidence": confidence,
                    "signal_name": "apple_ios_workouts",
                    "signal_value": workout_type,
                    "source_event_id": source_event_id,
                    "source_metadata": json.dumps(source_metadata),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            )
            count += 1
        
        return count
    
    def _process_hrv(
        self,
        metrics: List[Dict[str, Any]],
        signal_id: str,
        
        device_id: str,
        db
    ) -> int:
        """Process heart rate variability metrics."""
        count = 0
        
        for metric in metrics:
            # Parse timestamp first (needed for source_event_id)
            timestamp_str = metric['timestamp']
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            if timestamp.tzinfo:
                timestamp = timestamp.astimezone(tz.utc)
            else:
                timestamp = timestamp.replace(tzinfo=tz.utc)
            
            # Generate deterministic source event ID (HRV is continuous)
            source_event_id = generate_source_event_id('continuous', timestamp, metric)
            
            # Extract metadata
            metadata = metric.get('metadata', {})
            
            # Calculate confidence based on measurement quality
            # HRV measurements are generally high quality
            confidence = 0.95
            
            # Build source metadata
            source_metadata = {
                'device_id': device_id,
                'hrv_ms': metric['value'],
                'measurement_context': metadata.get('context', 'unknown')
            }
            
            # Insert ambient signal
            db.execute(
                text("""
                    INSERT INTO signals 
                    (id,  signal_id, source_name, timestamp, 
                     confidence, signal_name, signal_value, source_event_id, 
                     source_metadata, created_at, updated_at)
                    VALUES (:id, :signal_id, :source_name, :timestamp, 
                            :confidence, :signal_name, :signal_value, :source_event_id, 
                            :source_metadata, :created_at, :updated_at)
                    ON CONFLICT (source_name, source_event_id, signal_name) DO NOTHING
                """),
                {
                    "id": str(uuid4()),
                    "signal_id": signal_id,
                    "source_name": self.source_name,
                    "timestamp": timestamp,
                    "confidence": confidence,
                    "signal_name": "apple_ios_heart_rate_variability",
                    "signal_value": str(metric['value']),
                    "source_event_id": source_event_id,
                    "source_metadata": json.dumps(source_metadata),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            )
            count += 1
        
        return count