"""Generic configuration-driven stream processor for iOS HealthKit data."""

from datetime import datetime, timezone as tz
from typing import Dict, Any, List, Optional
from uuid import uuid4
import json
from pathlib import Path
from sqlalchemy import text
from sources.base.processing.dedup import generate_idempotency_key
from sources.base.processing.normalization import DataNormalizer


class StreamProcessor:
    """
    Generic stream processor for iOS HealthKit data.
    Configuration passed via signal_configs parameter in process().
    """
    
    def __init__(self, stream_name: Optional[str] = None):
        """
        Initialize the processor.
        
        Args:
            stream_name: Optional stream name. If not provided, auto-detects from path.
        """
        # Note: Registry no longer used - processor relies on passed signal_configs
        
        # Auto-detect stream name if not provided
        if not stream_name:
            stream_name = self._detect_stream_name()
        
        self.stream_name = stream_name
        
        # Configuration will be passed via signal_configs parameter in process()
        # Set defaults for processor configuration
        self.source_name = 'ios'  # iOS HealthKit is always from iOS source
        self.stream_type = 'array'  # HealthKit uses array type
        self.dedup_strategy = 'single'
    
    def _detect_stream_name(self) -> str:
        """
        Auto-detect stream name from the file path.
        Assumes structure: sources/<source>/<stream>/stream_processor.py
        """
        # Get the path of this file
        current_path = Path(__file__).resolve()
        
        # Extract source and stream from path
        parts = current_path.parts
        
        # Find 'sources' in the path
        try:
            sources_idx = parts.index('sources')
            if sources_idx + 2 < len(parts):
                source = parts[sources_idx + 1]
                stream = parts[sources_idx + 2]
                # Construct stream name (e.g., ios_healthkit)
                return f"{source}_{stream}"
        except (ValueError, IndexError):
            pass
        
        raise ValueError("Could not auto-detect stream name from path")
    
    def process(
        self,
        stream_data: Dict[str, Any],
        signal_configs: Dict[str, str],
        db
    ) -> Dict[str, Any]:
        """
        Process stream data into signals based on registry configuration.
        
        Args:
            stream_data: Raw stream data from MinIO
            signal_configs: Mapping of signal names to signal IDs from database
            db: Database session
            
        Returns:
            Processing result with signal counts
        """
        # For HealthKit, we expect a 'data' array
        return self._process_healthkit_array(stream_data, signal_configs, db)
    
    def _process_healthkit_array(
        self,
        stream_data: Dict[str, Any],
        signal_configs: Dict[str, str],
        db
    ) -> Dict[str, Any]:
        """Process HealthKit array data into signals."""
        
        # Extract data array from stream
        data = stream_data.get('data', [])
        device_id = stream_data.get('device_id')
        batch_metadata = stream_data.get('batch_metadata', {})
        
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
        print(f"Processing {len(data)} HealthKit entries")
        for metric in data:
            metric_type = metric.get('metric_type')
            if metric_type in metrics_by_type:
                metrics_by_type[metric_type].append(metric)
        
        # Track signals created per signal type
        signals_created = {}
        
        # Process each metric type
        # Heart Rate
        if metrics_by_type['heart_rate'] and 'ios_heart_rate' in signal_configs:
            count = self._process_heart_rate(
                metrics_by_type['heart_rate'],
                signal_configs['ios_heart_rate'],
                device_id,
                db
            )
            signals_created['ios_heart_rate'] = count
        
        # Steps
        if metrics_by_type['steps'] and 'ios_steps' in signal_configs:
            count = self._process_steps(
                metrics_by_type['steps'],
                signal_configs['ios_steps'],
                device_id,
                db
            )
            signals_created['ios_steps'] = count
        
        # Sleep
        if metrics_by_type['sleep'] and 'ios_sleep' in signal_configs:
            count = self._process_sleep(
                metrics_by_type['sleep'],
                signal_configs['ios_sleep'],
                device_id,
                db
            )
            signals_created['ios_sleep'] = count
        
        # Active Energy
        if metrics_by_type['active_energy'] and 'ios_active_energy' in signal_configs:
            count = self._process_active_energy(
                metrics_by_type['active_energy'],
                signal_configs['ios_active_energy'],
                device_id,
                db
            )
            signals_created['ios_active_energy'] = count
        
        # Workouts
        if metrics_by_type['workouts'] and 'ios_workouts' in signal_configs:
            count = self._process_workouts(
                metrics_by_type['workouts'],
                signal_configs['ios_workouts'],
                device_id,
                db
            )
            signals_created['ios_workouts'] = count
        
        # Heart Rate Variability
        if metrics_by_type['heart_rate_variability'] and 'ios_heart_rate_variability' in signal_configs:
            count = self._process_hrv(
                metrics_by_type['heart_rate_variability'],
                signal_configs['ios_heart_rate_variability'],
                device_id,
                db
            )
            signals_created['ios_heart_rate_variability'] = count
        
        # Commit all signals
        db.commit()
        
        # Print final counts
        for signal_name, count in signals_created.items():
            print(f"Total signals created for {signal_name}: {count}")
        
        return {
            "status": "success",
            "stream_name": self.stream_name,
            "records_processed": len(data),
            "signals_created": signals_created,
            "total_signals": sum(signals_created.values()),
            "batch_metadata": batch_metadata
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
            # Parse timestamp using DataNormalizer for consistency
            timestamp_str = metric.get('timestamp')
            if not timestamp_str:
                continue
                
            timestamp = DataNormalizer.normalize_timestamp(timestamp_str)
            if not timestamp:
                continue
            
            # Generate idempotency key based on timestamp (for deduplication)
            idempotency_key = generate_idempotency_key(
                self.dedup_strategy,
                timestamp,
                {'timestamp': timestamp.isoformat(), 'metric_type': 'heart_rate'}
            )
            
            # Extract metadata
            metadata = metric.get('metadata', {})
            activity_context = metadata.get('activity_context', 'unknown')
            
            # Calculate confidence based on activity context
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
            
            # Insert signal
            db.execute(
                text("""
                    INSERT INTO signals 
                    (id, signal_id, source_name, timestamp, 
                     confidence, signal_name, signal_value, idempotency_key, 
                     source_metadata, created_at, updated_at)
                    VALUES (:id, :signal_id, :source_name, :timestamp, 
                            :confidence, :signal_name, :signal_value, :idempotency_key, 
                            :source_metadata, :created_at, :updated_at)
                    ON CONFLICT (source_name, idempotency_key, signal_name) DO UPDATE SET
                        timestamp = EXCLUDED.timestamp,
                        signal_value = EXCLUDED.signal_value,
                        confidence = EXCLUDED.confidence,
                        source_metadata = EXCLUDED.source_metadata,
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    "id": str(uuid4()),
                    "signal_id": signal_id,
                    "source_name": self.source_name,
                    "timestamp": timestamp,
                    "confidence": confidence,
                    "signal_name": "ios_heart_rate",
                    "signal_value": str(metric['value']),
                    "idempotency_key": idempotency_key,
                    "source_metadata": json.dumps(source_metadata),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            )
            count += 1
            
            if count % 50 == 0:
                print(f"Processed {count} heart rate signals so far...")
        
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
            # Parse timestamp using DataNormalizer for consistency
            timestamp_str = metric.get('timestamp')
            if not timestamp_str:
                continue
                
            timestamp = DataNormalizer.normalize_timestamp(timestamp_str)
            if not timestamp:
                continue
            
            # Generate idempotency key
            idempotency_key = generate_idempotency_key(
                self.dedup_strategy,
                timestamp,
                {'timestamp': timestamp.isoformat(), 'metric_type': 'steps'}
            )
            
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
            
            # Insert signal
            db.execute(
                text("""
                    INSERT INTO signals 
                    (id, signal_id, source_name, timestamp, 
                     confidence, signal_name, signal_value, idempotency_key, 
                     source_metadata, created_at, updated_at)
                    VALUES (:id, :signal_id, :source_name, :timestamp, 
                            :confidence, :signal_name, :signal_value, :idempotency_key, 
                            :source_metadata, :created_at, :updated_at)
                    ON CONFLICT (source_name, idempotency_key, signal_name) DO UPDATE SET
                        timestamp = EXCLUDED.timestamp,
                        signal_value = EXCLUDED.signal_value,
                        confidence = EXCLUDED.confidence,
                        source_metadata = EXCLUDED.source_metadata,
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    "id": str(uuid4()),
                    "signal_id": signal_id,
                    "source_name": self.source_name,
                    "timestamp": timestamp,
                    "confidence": confidence,
                    "signal_name": "ios_steps",
                    "signal_value": str(metric['value']),
                    "idempotency_key": idempotency_key,
                    "source_metadata": json.dumps(source_metadata),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            )
            count += 1
            
            if count % 50 == 0:
                print(f"Processed {count} step signals so far...")
        
        return count
    
    def _process_sleep(
        self,
        metrics: List[Dict[str, Any]],
        signal_id: str,
        device_id: str,
        db
    ) -> int:
        """Process sleep metrics."""
        count = 0
        
        # Map HealthKit sleep states
        sleep_state_mapping = {
            'in_bed': 'in_bed',
            'awake': 'awake',
            'asleep': 'asleep',
            'asleep_core': 'asleep_core',
            'asleep_deep': 'asleep_deep',
            'asleep_rem': 'asleep_rem',
            'unknown': 'unknown'
        }
        
        for metric in metrics:
            # Parse timestamp using DataNormalizer for consistency
            timestamp_str = metric.get('timestamp')
            if not timestamp_str:
                continue
                
            timestamp = DataNormalizer.normalize_timestamp(timestamp_str)
            if not timestamp:
                continue
            
            # Generate idempotency key
            idempotency_key = generate_idempotency_key(
                self.dedup_strategy,
                timestamp,
                {'timestamp': timestamp.isoformat(), 'metric_type': 'sleep'}
            )
            
            # Extract metadata
            metadata = metric.get('metadata', {})
            raw_sleep_state = metadata.get('sleep_state', 'unknown')
            sleep_state = sleep_state_mapping.get(raw_sleep_state, raw_sleep_state.lower())
            duration_minutes = metadata.get('duration_minutes', 0)
            
            # Calculate confidence
            confidence = 0.90
            if sleep_state != 'unknown' and duration_minutes > 0:
                confidence = 0.95
            
            # Build source metadata
            source_metadata = {
                'device_id': device_id,
                'sleep_state': sleep_state,
                'raw_sleep_state': raw_sleep_state,
                'duration_minutes': duration_minutes,
                'state_value': metric['value']
            }
            
            # Insert signal
            db.execute(
                text("""
                    INSERT INTO signals 
                    (id, signal_id, source_name, timestamp, 
                     confidence, signal_name, signal_value, idempotency_key, 
                     source_metadata, created_at, updated_at)
                    VALUES (:id, :signal_id, :source_name, :timestamp, 
                            :confidence, :signal_name, :signal_value, :idempotency_key, 
                            :source_metadata, :created_at, :updated_at)
                    ON CONFLICT (source_name, idempotency_key, signal_name) DO UPDATE SET
                        timestamp = EXCLUDED.timestamp,
                        signal_value = EXCLUDED.signal_value,
                        confidence = EXCLUDED.confidence,
                        source_metadata = EXCLUDED.source_metadata,
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    "id": str(uuid4()),
                    "signal_id": signal_id,
                    "source_name": self.source_name,
                    "timestamp": timestamp,
                    "confidence": confidence,
                    "signal_name": "ios_sleep",
                    "signal_value": sleep_state,
                    "idempotency_key": idempotency_key,
                    "source_metadata": json.dumps(source_metadata),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            )
            count += 1
            
            if count % 50 == 0:
                print(f"Processed {count} sleep signals so far...")
        
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
            # Parse timestamp using DataNormalizer for consistency
            timestamp_str = metric.get('timestamp')
            if not timestamp_str:
                continue
                
            timestamp = DataNormalizer.normalize_timestamp(timestamp_str)
            if not timestamp:
                continue
            
            # Generate idempotency key
            idempotency_key = generate_idempotency_key(
                self.dedup_strategy,
                timestamp,
                {'timestamp': timestamp.isoformat(), 'metric_type': 'active_energy'}
            )
            
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
            
            # Insert signal
            db.execute(
                text("""
                    INSERT INTO signals 
                    (id, signal_id, source_name, timestamp, 
                     confidence, signal_name, signal_value, idempotency_key, 
                     source_metadata, created_at, updated_at)
                    VALUES (:id, :signal_id, :source_name, :timestamp, 
                            :confidence, :signal_name, :signal_value, :idempotency_key, 
                            :source_metadata, :created_at, :updated_at)
                    ON CONFLICT (source_name, idempotency_key, signal_name) DO UPDATE SET
                        timestamp = EXCLUDED.timestamp,
                        signal_value = EXCLUDED.signal_value,
                        confidence = EXCLUDED.confidence,
                        source_metadata = EXCLUDED.source_metadata,
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    "id": str(uuid4()),
                    "signal_id": signal_id,
                    "source_name": self.source_name,
                    "timestamp": timestamp,
                    "confidence": confidence,
                    "signal_name": "ios_active_energy",
                    "signal_value": str(metric['value']),
                    "idempotency_key": idempotency_key,
                    "source_metadata": json.dumps(source_metadata),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            )
            count += 1
            
            if count % 50 == 0:
                print(f"Processed {count} active energy signals so far...")
        
        return count
    
    def _process_workouts(
        self,
        metrics: List[Dict[str, Any]],
        signal_id: str,
        device_id: str,
        db
    ) -> int:
        """Process workout metrics."""
        count = 0
        
        for metric in metrics:
            # Parse timestamp using DataNormalizer for consistency
            timestamp_str = metric.get('timestamp')
            if not timestamp_str:
                continue
                
            timestamp = DataNormalizer.normalize_timestamp(timestamp_str)
            if not timestamp:
                continue
            
            # Generate idempotency key (workouts allow multiple at same time)
            idempotency_key = generate_idempotency_key(
                'multiple',  # Allow multiple workouts at same timestamp
                timestamp,
                {'timestamp': timestamp.isoformat(), 'metric_type': 'workouts', 'value': metric.get('value')}
            )
            
            # Extract metadata
            metadata = metric.get('metadata', {})
            workout_type = metadata.get('workout_type', 'unknown')
            end_date = metadata.get('end_date')
            total_energy = metadata.get('total_energy', 0)
            
            # Calculate confidence
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
            
            # Insert signal
            db.execute(
                text("""
                    INSERT INTO signals 
                    (id, signal_id, source_name, timestamp, 
                     confidence, signal_name, signal_value, idempotency_key, 
                     source_metadata, created_at, updated_at)
                    VALUES (:id, :signal_id, :source_name, :timestamp, 
                            :confidence, :signal_name, :signal_value, :idempotency_key, 
                            :source_metadata, :created_at, :updated_at)
                    ON CONFLICT (source_name, idempotency_key, signal_name) DO UPDATE SET
                        timestamp = EXCLUDED.timestamp,
                        signal_value = EXCLUDED.signal_value,
                        confidence = EXCLUDED.confidence,
                        source_metadata = EXCLUDED.source_metadata,
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    "id": str(uuid4()),
                    "signal_id": signal_id,
                    "source_name": self.source_name,
                    "timestamp": timestamp,
                    "confidence": confidence,
                    "signal_name": "ios_workouts",
                    "signal_value": workout_type,
                    "idempotency_key": idempotency_key,
                    "source_metadata": json.dumps(source_metadata),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            )
            count += 1
            
            if count % 50 == 0:
                print(f"Processed {count} workout signals so far...")
        
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
            # Parse timestamp using DataNormalizer for consistency
            timestamp_str = metric.get('timestamp')
            if not timestamp_str:
                continue
                
            timestamp = DataNormalizer.normalize_timestamp(timestamp_str)
            if not timestamp:
                continue
            
            # Generate idempotency key
            idempotency_key = generate_idempotency_key(
                self.dedup_strategy,
                timestamp,
                {'timestamp': timestamp.isoformat(), 'metric_type': 'heart_rate_variability'}
            )
            
            # Extract metadata
            metadata = metric.get('metadata', {})
            
            # Calculate confidence
            confidence = 0.95
            
            # Build source metadata
            source_metadata = {
                'device_id': device_id,
                'hrv_ms': metric['value'],
                'measurement_context': metadata.get('context', 'unknown')
            }
            
            # Insert signal
            db.execute(
                text("""
                    INSERT INTO signals 
                    (id, signal_id, source_name, timestamp, 
                     confidence, signal_name, signal_value, idempotency_key, 
                     source_metadata, created_at, updated_at)
                    VALUES (:id, :signal_id, :source_name, :timestamp, 
                            :confidence, :signal_name, :signal_value, :idempotency_key, 
                            :source_metadata, :created_at, :updated_at)
                    ON CONFLICT (source_name, idempotency_key, signal_name) DO UPDATE SET
                        timestamp = EXCLUDED.timestamp,
                        signal_value = EXCLUDED.signal_value,
                        confidence = EXCLUDED.confidence,
                        source_metadata = EXCLUDED.source_metadata,
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    "id": str(uuid4()),
                    "signal_id": signal_id,
                    "source_name": self.source_name,
                    "timestamp": timestamp,
                    "confidence": confidence,
                    "signal_name": "ios_heart_rate_variability",
                    "signal_value": str(metric['value']),
                    "idempotency_key": idempotency_key,
                    "source_metadata": json.dumps(source_metadata),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            )
            count += 1
            
            if count % 50 == 0:
                print(f"Processed {count} HRV signals so far...")
        
        return count