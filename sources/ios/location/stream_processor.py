"""Generic configuration-driven stream processor for iOS location data."""

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
    Generic stream processor for iOS location data.
    Reads configuration from the generated registry and processes location signals.
    """
    
    def __init__(self, stream_name: Optional[str] = None):
        """
        Initialize the processor with configuration from the registry.
        
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
        self.source_name = 'ios'  # iOS location is always from iOS source
        self.stream_type = 'array'  # iOS location uses array type
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
        
        print(f"[DEBUG iOS Location] Processing stream_data with keys: {stream_data.keys()}")
        
        # Extract location data array
        locations = stream_data.get('data', [])
        device_id = stream_data.get('device_id')
        batch_metadata = stream_data.get('batch_metadata', {})
        
        # Track signals created per signal type
        signals_created = {}
        
        # Initialize counters for each signal type we're actually processing
        for signal_name in signal_configs.keys():
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
            
            # Generate idempotency key based on timestamp (for deduplication)
            idempotency_key = generate_idempotency_key(
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
            if 'ios_coordinates' in signal_configs:
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
                             idempotency_key, source_metadata, created_at, updated_at)
                            VALUES (:id, :signal_id, :source_name, :timestamp, 
                                    :confidence, :signal_name, :signal_value, 
                                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), 
                                    :idempotency_key, :source_metadata, :created_at, :updated_at)
                            ON CONFLICT (source_name, idempotency_key, signal_name) DO UPDATE SET
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
                            "idempotency_key": idempotency_key,
                            "source_metadata": json.dumps(base_metadata),
                            "created_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                    )
                    signals_created['ios_coordinates'] += 1
            
            # Process altitude signal
            if 'ios_altitude' in signal_configs:
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
                            "signal_id": signal_configs['ios_altitude'],
                            "source_name": self.source_name,
                            "timestamp": timestamp,
                            "confidence": confidence,
                            "signal_name": "ios_altitude",
                            "signal_value": str(altitude),
                            "idempotency_key": idempotency_key,
                            "source_metadata": json.dumps(altitude_metadata),
                            "created_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                    )
                    signals_created['ios_altitude'] += 1
            
            # Process speed signal
            if 'ios_speed' in signal_configs:
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
                            "signal_id": signal_configs['ios_speed'],
                            "source_name": self.source_name,
                            "timestamp": timestamp,
                            "confidence": confidence,
                            "signal_name": "ios_speed",
                            "signal_value": str(speed),
                            "idempotency_key": idempotency_key,
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