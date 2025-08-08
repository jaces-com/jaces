"""Stream processor for Apple Mac App Activity stream data."""

from datetime import datetime, timezone as tz
from typing import Dict, Any, List
from uuid import uuid4
import json
from sqlalchemy import text
from sources.base.processing.dedup import generate_source_event_id


class MacAppActivityStreamProcessor:
    """Process Mac app activity stream data into signals."""
    
    def __init__(self):
        self.source_name = "mac"
    
    def process(
        self,
        stream_data: Dict[str, Any],
        signal_configs: Dict[str, str],
        db
    ) -> Dict[str, Any]:
        """
        Process Mac app activity stream data into signals.
        
        Args:
            stream_data: Raw stream data from MinIO
            signal_configs: Mapping of signal names to signal IDs
            db: Database session
            
        Returns:
            Processing result with signal counts
        """
        # Extract activity events
        activity_events = stream_data.get('activity_events', [])
        device_id = stream_data.get('device_id')
        batch_metadata = stream_data.get('batch_metadata', {})
        
        # Check if we have the signal config
        if 'apple_mac_apps' not in signal_configs:
            return {
                "status": "skipped",
                "reason": "apple_mac_apps signal not configured",
                "stream_name": "apple_mac_app_activity",
                "records_processed": 0
            }
        
        signal_id = signal_configs['apple_mac_apps']
        signals_created = 0
        
        # Process each activity event
        for event in activity_events:
            # Parse timestamp - handle both Unix timestamps and ISO strings
            timestamp_value = event.get('timestamp')
            if isinstance(timestamp_value, (int, float)):
                # Check if this is Apple's reference date (seconds since Jan 1, 2001)
                # If the timestamp is less than year 2000 in Unix time, it's likely Apple time
                if timestamp_value < 946684800:  # Jan 1, 2000 in Unix seconds
                    # This is Apple reference time - add the difference to Unix epoch
                    # Apple epoch: Jan 1, 2001 00:00:00 UTC = Unix timestamp 978307200
                    unix_timestamp = timestamp_value + 978307200
                    timestamp = datetime.fromtimestamp(unix_timestamp, tz=tz.utc).replace(tzinfo=None)
                elif timestamp_value > 4102444800:  # Jan 1, 2100 in seconds
                    # Timestamp is in milliseconds
                    timestamp = datetime.fromtimestamp(timestamp_value / 1000, tz=tz.utc).replace(tzinfo=None)
                else:
                    # Regular Unix timestamp in seconds
                    timestamp = datetime.fromtimestamp(timestamp_value, tz=tz.utc).replace(tzinfo=None)
            else:
                # ISO string
                timestamp = datetime.fromisoformat(timestamp_value.replace('Z', '+00:00'))
                if timestamp.tzinfo:
                    timestamp = timestamp.astimezone(tz.utc).replace(tzinfo=None)
            
            # Generate deterministic source event ID (mac apps are categorical type)
            event_data = {
                'app_name': app_name,
                'bundle_id': bundle_id,
                'event_type': signal_type
            }
            source_event_id = generate_source_event_id('categorical', timestamp, event_data)
            
            # Determine signal name based on event type
            signal_type = event.get('signalType', 'unknown')
            
            # Extract metadata from the event
            event_metadata = event.get('metadata', {})
            app_name = event_metadata.get('app_name', 'Unknown')
            bundle_id = event_metadata.get('bundle_id', '')
            
            # Create signal value - format: "app_name (event_type)"
            signal_value = f"{app_name} ({signal_type})"
            
            # Build metadata
            metadata = {
                'device_id': device_id,
                'app_name': app_name,
                'bundle_id': bundle_id,
                'event_type': signal_type,
                'window_title': event_metadata.get('window_title'),
                'duration': event_metadata.get('duration'),
                'batch_info': batch_metadata
            }
            
            # Remove None values from metadata
            metadata = {k: v for k, v in metadata.items() if v is not None}
            
            # Insert ambient signal
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
                    "signal_id": signal_id,
                    "source_name": self.source_name,
                    "timestamp": timestamp,
                    "confidence": 0.95,  # High confidence for direct app events
                    "signal_name": "apple_mac_apps",
                    "signal_value": signal_value,
                    "source_event_id": source_event_id,
                    "source_metadata": json.dumps(metadata),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            )
            signals_created += 1
        
        # Commit all signals
        db.commit()
        
        return {
            "status": "success",
            "stream_name": "apple_mac_app_activity",
            "records_processed": len(activity_events),
            "signals_created": signals_created
        }


