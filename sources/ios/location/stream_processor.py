"""Stream processor for Apple iOS Core Location unified stream data."""

import json
from datetime import datetime, timezone as tz
from typing import Dict, Any, List
from uuid import uuid4
from sqlalchemy import text
from sources.base.processing.dedup import generate_source_event_id


class CoreLocationStreamProcessor:
    """Process unified CoreLocation stream data into signals."""
    
    def __init__(self):
        self.source_name = "ios"
    
    def process(
        self,
        stream_data: Dict[str, Any],
        signal_configs: Dict[str, str],
        db
    ) -> Dict[str, Any]:
        """
        Process CoreLocation stream data into multiple signals.
        
        Args:
            stream_data: Raw stream data from MinIO
            signal_configs: Mapping of signal names to signal IDs
            db: Database session
            
        Returns:
            Processing result with signal counts
        """
        # Extract location data array
        locations = stream_data.get('data', [])
        device_id = stream_data.get('device_id')
        batch_metadata = stream_data.get('batch_metadata', {})
        
        # Track signals created
        signal_counts = {
            'coordinates': 0,
            'altitude': 0,
            'speed': 0
        }
        
        # Process each location entry
        for location in locations:
            # Parse timestamp first (needed for source_event_id)
            timestamp_str = location.get('timestamp')
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            if timestamp.tzinfo:
                timestamp = timestamp.astimezone(tz.utc)
            else:
                # If no timezone info, assume UTC
                timestamp = timestamp.replace(tzinfo=tz.utc)
            
            # For location data, we'll use the base timestamp as the source_event_id
            # This allows different signals (speed, altitude, coordinates) from the same
            # location reading to share the same timestamp-based ID
            base_source_event_id = timestamp.isoformat()
            
            # Extract common metadata
            base_metadata = {
                'device_id': device_id,
                'activity_type': location.get('activity_type'),
                'activity_confidence': location.get('activity_confidence'),
                'battery_level': location.get('battery_level'),
                'horizontal_accuracy': location.get('horizontal_accuracy'),
                'vertical_accuracy': location.get('vertical_accuracy')
            }
            
            # 1. Create coordinates signal
            if 'apple_ios_coordinates' in signal_configs:
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
                            ON CONFLICT (source_name, source_event_id, signal_name) DO NOTHING
                        """),
                        {
                            "id": str(uuid4()),  # Unique ID for this record
                            "signal_id": signal_configs['apple_ios_coordinates'],
                            "source_name": self.source_name,
                            "timestamp": timestamp,
                            "confidence": confidence,
                            "signal_name": "apple_ios_coordinates",
                            "signal_value": f"{lat},{lon}",
                            "lat": lat,
                            "lon": lon,
                            "source_event_id": base_source_event_id,
                            "source_metadata": json.dumps(base_metadata),
                            "created_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                    )
                    signal_counts['coordinates'] += 1
            
            # 2. Create altitude signal
            if 'apple_ios_altitude' in signal_configs:
                altitude = location.get('altitude')
                
                if altitude is not None:
                    # Altitude confidence based on vertical accuracy
                    vertical_accuracy = location.get('vertical_accuracy', 10)
                    confidence = min(1.0, 5.0 / max(vertical_accuracy, 1.0)) * 0.95
                    
                    db.execute(
                        text("""
                            INSERT INTO signals 
                            (id, signal_id, source_name, timestamp, 
                             confidence, signal_name, signal_value, source_event_id, 
                             source_metadata, created_at, updated_at)
                            VALUES (:id, :signal_id, :source_name, :timestamp, 
                                    :confidence, :signal_name, :signal_value, :source_event_id, 
                                    :source_metadata, :created_at, :updated_at)
                            ON CONFLICT (source_name, source_event_id, signal_name) DO NOTHING
                        """),
                        {
                            "id": str(uuid4()),
                            "signal_id": signal_configs['apple_ios_altitude'],
                            "source_name": self.source_name,
                            "timestamp": timestamp,
                            "confidence": confidence,
                            "signal_name": "apple_ios_altitude",
                            "signal_value": str(altitude),
                            "source_event_id": base_source_event_id,
                            "source_metadata": json.dumps({**base_metadata, 'altitude_meters': altitude}),
                            "created_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                    )
                    signal_counts['altitude'] += 1
            
            # 3. Create speed signal
            if 'apple_ios_speed' in signal_configs:
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
                            ON CONFLICT (source_name, source_event_id, signal_name) DO NOTHING
                        """),
                        {
                            "id": str(uuid4()),
                            "signal_id": signal_configs['apple_ios_speed'],
                            "source_name": self.source_name,
                            "timestamp": timestamp,
                            "confidence": confidence,
                            "signal_name": "apple_ios_speed",
                            "signal_value": str(speed),
                            "source_event_id": base_source_event_id,
                            "source_metadata": json.dumps(speed_metadata),
                            "created_at": datetime.utcnow(),
                            "updated_at": datetime.utcnow()
                        }
                    )
                    signal_counts['speed'] += 1
        
        # Commit all signals
        db.commit()
        
        return {
            "status": "success",
            "stream_name": "apple_ios_core_location",
            "records_processed": len(locations),
            "signals_created": {
                "apple_ios_coordinates": signal_counts['coordinates'],
                "apple_ios_altitude": signal_counts['altitude'],
                "apple_ios_speed": signal_counts['speed']
            },
            "total_signals": sum(signal_counts.values())
        }


