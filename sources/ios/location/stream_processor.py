"""Generic configuration-driven stream processor for iOS location data."""

from datetime import datetime, timezone as tz
from typing import Dict, Any, List, Optional
from uuid import uuid4
import json
from pathlib import Path
from sqlalchemy import text
from sources.base.processing.dedup import generate_source_event_id
from sources.base.processing.normalization import DataNormalizer


class StreamProcessor:
    """
    Generic stream processor for iOS location data.
    Reads configuration from the generated registry and processes location signals.
    """
    
    def __init__(self, stream_name: Optional[str] = None):
        """
        Initialize the processor with configuration from the registry.
        
        Args:
            stream_name: Optional stream name. If not provided, auto-detects from path.
        """
        # Import registry (at runtime to get latest generated version)
        from sources._generated_registry import STREAMS, SIGNALS
        
        # Auto-detect stream name if not provided
        if not stream_name:
            stream_name = self._detect_stream_name()
        
        self.stream_name = stream_name
        
        # Get stream configuration from registry
        if stream_name not in STREAMS:
            raise ValueError(f"Stream '{stream_name}' not found in registry")
        
        self.stream_config = STREAMS[stream_name]
        
        # Extract processor configuration
        processor_config = self.stream_config.get('processor_config', {})
        self.source_name = processor_config.get('source_name', self.stream_config.get('source'))
        self.stream_type = processor_config.get('stream_type', 'array')  # iOS location uses array type
        self.dedup_strategy = processor_config.get('deduplication_strategy', 'single')
        
        # Get signal configurations from registry
        self.signal_configs = {}
        signal_names = self.stream_config.get('signals', []) or self.stream_config.get('produces_signals', [])
        for signal_name in signal_names:
            if signal_name in SIGNALS:
                self.signal_configs[signal_name] = SIGNALS[signal_name]
                print(f"Loaded signal config: {signal_name}")
    
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
                # Construct stream name (e.g., ios_location)
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
        # For iOS location, we expect a 'data' array
        return self._process_location_array(stream_data, signal_configs, db)
    
    def _process_location_array(
        self,
        stream_data: Dict[str, Any],
        signal_configs: Dict[str, str],
        db
    ) -> Dict[str, Any]:
        """Process location array data into signals."""
        
        # Extract location data array
        locations = stream_data.get('data', [])
        device_id = stream_data.get('device_id')
        batch_metadata = stream_data.get('batch_metadata', {})
        
        # Track signals created per signal type
        signals_created = {}
        
        # Initialize counters for each signal type
        for signal_name in self.signal_configs.keys():
            signals_created[signal_name] = 0
        
        # Process each location entry
        print(f"Processing {len(locations)} location entries")
        for location in locations:
            # Parse timestamp using DataNormalizer for consistency
            timestamp_str = location.get('timestamp')
            if not timestamp_str:
                continue
                
            timestamp = DataNormalizer.normalize_timestamp(timestamp_str)
            if not timestamp:
                continue
            
            # Generate source event ID based on timestamp (for deduplication)
            source_event_id = generate_source_event_id(
                self.dedup_strategy,
                timestamp,
                {'timestamp': timestamp.isoformat()}
            )
            
            # Extract common metadata
            base_metadata = {
                'device_id': device_id,
                'activity_type': location.get('activity_type'),
                'activity_confidence': location.get('activity_confidence'),
                'battery_level': location.get('battery_level'),
                'horizontal_accuracy': location.get('horizontal_accuracy'),
                'vertical_accuracy': location.get('vertical_accuracy')
            }
            
            # Process coordinates signal
            if 'ios_coordinates' in signal_configs and 'ios_coordinates' in self.signal_configs:
                lat = location.get('latitude')
                lon = location.get('longitude')
                
                if lat is not None and lon is not None:
                    # Calculate confidence based on accuracy
                    horizontal_accuracy = location.get('horizontal_accuracy', 50)
                    confidence = min(1.0, 10.0 / max(horizontal_accuracy, 1.0)) * 0.95
                    
                    # Insert with PostGIS geometry
                    db.execute(
                        text("""
                            INSERT INTO signals 
                            (id, signal_id, source_name, timestamp, 
                             confidence, signal_name, signal_value, coordinates, 
                             source_event_id, source_metadata, created_at, updated_at)
                            VALUES (:id, :signal_id, :source_name, :timestamp, 
                                    :confidence, :signal_name, :signal_value, 
                                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 
                                    :source_event_id, :source_metadata, :created_at, :updated_at)
                            ON CONFLICT (source_name, source_event_id, signal_name) DO UPDATE SET
                                timestamp = EXCLUDED.timestamp,
                                signal_value = EXCLUDED.signal_value,
                                coordinates = EXCLUDED.coordinates,
                                confidence = EXCLUDED.confidence,
                                source_metadata = EXCLUDED.source_metadata,
                                updated_at = EXCLUDED.updated_at
                        """),
                        {
                            "id": str(uuid4()),
                            "signal_id": signal_configs['ios_coordinates'],
                            "source_name": self.source_name,
                            "timestamp": timestamp,
                            "confidence": confidence,
                            "signal_name": "ios_coordinates",
                            "signal_value": f"{lat},{lon}",
                            "lat": lat,
                            "lon": lon,
                            "source_event_id": source_event_id,
                            "source_metadata": json.dumps(base_metadata),
                            "created_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                    )
                    signals_created['ios_coordinates'] += 1
            
            # Process altitude signal
            if 'ios_altitude' in signal_configs and 'ios_altitude' in self.signal_configs:
                altitude = location.get('altitude')
                
                if altitude is not None:
                    # Altitude confidence based on vertical accuracy
                    vertical_accuracy = location.get('vertical_accuracy', 10)
                    confidence = min(1.0, 5.0 / max(vertical_accuracy, 1.0)) * 0.95
                    
                    altitude_metadata = {**base_metadata, 'altitude_meters': altitude}
                    
                    db.execute(
                        text("""
                            INSERT INTO signals 
                            (id, signal_id, source_name, timestamp, 
                             confidence, signal_name, signal_value, source_event_id, 
                             source_metadata, created_at, updated_at)
                            VALUES (:id, :signal_id, :source_name, :timestamp, 
                                    :confidence, :signal_name, :signal_value, :source_event_id, 
                                    :source_metadata, :created_at, :updated_at)
                            ON CONFLICT (source_name, source_event_id, signal_name) DO UPDATE SET
                                timestamp = EXCLUDED.timestamp,
                                signal_value = EXCLUDED.signal_value,
                                confidence = EXCLUDED.confidence,
                                source_metadata = EXCLUDED.source_metadata,
                                updated_at = EXCLUDED.updated_at
                        """),
                        {
                            "id": str(uuid4()),
                            "signal_id": signal_configs['ios_altitude'],
                            "source_name": self.source_name,
                            "timestamp": timestamp,
                            "confidence": confidence,
                            "signal_name": "ios_altitude",
                            "signal_value": str(altitude),
                            "source_event_id": source_event_id,
                            "source_metadata": json.dumps(altitude_metadata),
                            "created_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                    )
                    signals_created['ios_altitude'] += 1
            
            # Process speed signal
            if 'ios_speed' in signal_configs and 'ios_speed' in self.signal_configs:
                speed = location.get('speed', 0)
                
                # Only create speed signal if valid (>= 0)
                if speed >= 0:
                    # Speed confidence based on horizontal accuracy and speed value
                    horizontal_accuracy = location.get('horizontal_accuracy', 50)
                    # Lower confidence for very low speeds as they may be noise
                    speed_factor = 1.0 if speed > 0.5 else 0.7
                    confidence = min(1.0, 10.0 / max(horizontal_accuracy, 1.0)) * 0.95 * speed_factor
                    
                    speed_metadata = {
                        **base_metadata,
                        'speed_m_s': speed,
                        'speed_km_h': speed * 3.6,
                        'speed_mph': speed * 2.237
                    }
                    
                    # Add course if available
                    course = location.get('course')
                    if course is not None and course >= 0:
                        speed_metadata['course'] = course
                    
                    db.execute(
                        text("""
                            INSERT INTO signals 
                            (id, signal_id, source_name, timestamp, 
                             confidence, signal_name, signal_value, source_event_id, 
                             source_metadata, created_at, updated_at)
                            VALUES (:id, :signal_id, :source_name, :timestamp, 
                                    :confidence, :signal_name, :signal_value, :source_event_id, 
                                    :source_metadata, :created_at, :updated_at)
                            ON CONFLICT (source_name, source_event_id, signal_name) DO UPDATE SET
                                timestamp = EXCLUDED.timestamp,
                                signal_value = EXCLUDED.signal_value,
                                confidence = EXCLUDED.confidence,
                                source_metadata = EXCLUDED.source_metadata,
                                updated_at = EXCLUDED.updated_at
                        """),
                        {
                            "id": str(uuid4()),
                            "signal_id": signal_configs['ios_speed'],
                            "source_name": self.source_name,
                            "timestamp": timestamp,
                            "confidence": confidence,
                            "signal_name": "ios_speed",
                            "signal_value": str(speed),
                            "source_event_id": source_event_id,
                            "source_metadata": json.dumps(speed_metadata),
                            "created_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                    )
                    signals_created['ios_speed'] += 1
            
            # Print progress every 50 locations
            total_processed = sum(signals_created.values())
            if total_processed % 50 == 0 and total_processed > 0:
                print(f"Processed {total_processed} signals so far...")
        
        # Commit all signals
        db.commit()
        
        # Print final counts
        for signal_name, count in signals_created.items():
            print(f"Total signals created for {signal_name}: {count}")
        
        return {
            "status": "success",
            "stream_name": self.stream_name,
            "records_processed": len(locations),
            "signals_created": signals_created,
            "total_signals": sum(signals_created.values()),
            "batch_metadata": batch_metadata
        }