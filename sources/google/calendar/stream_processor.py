"""Stream processor for Google Calendar Events stream data."""

from datetime import datetime, timezone as tz
from typing import Dict, Any, List
from uuid import uuid4
import json
from sqlalchemy import text
from sources.base.processing.dedup import generate_source_event_id


class GoogleCalendarStreamProcessor:
    """Process Google Calendar stream data into episodic signals."""
    
    def __init__(self):
        self.source_name = "google"
    
    def process(
        self,
        stream_data: Dict[str, Any],
        signal_configs: Dict[str, str],
        db
    ) -> Dict[str, Any]:
        """
        Process Google Calendar stream data into episodic signals.
        
        Args:
            stream_data: Raw stream data from MinIO
            signal_configs: Mapping of signal names to signal IDs
            db: Database session
            
        Returns:
            Processing result with signal counts
        """
        # Extract events
        events = stream_data.get('events', [])
        sync_metadata = stream_data.get('sync_metadata', {})
        
        # Check if we have the signal config
        if 'google_api_calendar' not in signal_configs:
            return {
                "status": "skipped",
                "reason": "google_api_calendar signal not configured",
                "stream_name": "google_calendar_events",
                "records_processed": 0
            }
        
        signal_id = signal_configs['google_api_calendar']
        signals_created = 0
        
        # Process each calendar event
        for event in events:
            # Skip declined events
            if event.get('status') == 'declined':
                continue
            
            # Parse timestamps
            start_time = self._parse_event_time(event.get('start'))
            end_time = self._parse_event_time(event.get('end'))
            
            if not start_time or not end_time:
                continue
            
            # Generate deterministic source event ID (calendar is parallel type)
            # Include the Google event ID for consistent deduplication
            event_data = {
                'event_id': event.get('id'),
                'summary': summary
            }
            source_event_id = generate_source_event_id('parallel', start_time, event_data)
            
            # Create summary
            summary = event.get('summary', 'Untitled Event')
            if event.get('is_all_day'):
                summary = f"[All Day] {summary}"
            
            # Build metadata
            metadata = {
                'calendar_id': event.get('calendar_id'),
                'calendar_name': event.get('calendar_name'),
                'event_type': event.get('event_type', 'default'),
                'location': event.get('location'),
                'description': event.get('description'),
                'attendees': event.get('attendees', []),
                'is_recurring': event.get('is_recurring', False),
                'is_all_day': event.get('is_all_day', False),
                'response_status': event.get('response_status'),
                'visibility': event.get('visibility', 'default'),
                'organizer': event.get('organizer'),
                'created': event.get('created'),
                'updated': event.get('updated')
            }
            
            # Remove None values and empty lists
            metadata = {k: v for k, v in metadata.items() if v is not None and v != []}
            
            # Determine confidence based on response status
            confidence = 0.95  # Default high confidence
            if event.get('response_status') == 'tentative':
                confidence = 0.7
            elif event.get('response_status') == 'needsAction':
                confidence = 0.6
            
            # Add event duration info to metadata
            metadata['start_timestamp'] = start_time.isoformat()
            metadata['end_timestamp'] = end_time.isoformat()
            metadata['duration_minutes'] = int((end_time - start_time).total_seconds() / 60)
            
            # Insert signal (using start time as the main timestamp)
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
                    "signal_id": signal_id,
                    "source_name": self.source_name,
                    "timestamp": start_time,
                    "confidence": confidence,
                    "signal_name": "google_api_calendar",
                    "signal_value": summary,
                    "source_event_id": source_event_id,
                    "source_metadata": json.dumps(metadata),
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow()
                }
            )
            signals_created += 1
        
        # Update sync token if provided
        if sync_metadata.get('next_sync_token'):
            # Store sync token for next incremental sync
            # This would typically be stored in a sync_state table
            pass
        
        # Commit all signals
        db.commit()
        
        return {
            "status": "success",
            "stream_name": "google_calendar_events",
            "records_processed": len(events),
            "signals_created": signals_created,
            "sync_metadata": sync_metadata
        }
    
    def _parse_event_time(self, time_obj: Dict[str, Any]) -> datetime:
        """Parse Google Calendar time object to datetime."""
        if not time_obj:
            return None
        
        # Handle dateTime format (with time)
        if 'dateTime' in time_obj:
            dt = datetime.fromisoformat(time_obj['dateTime'].replace('Z', '+00:00'))
            if dt.tzinfo:
                dt = dt.astimezone(tz.utc).replace(tzinfo=None)
            return dt
        
        # Handle date format (all-day events)
        elif 'date' in time_obj:
            # Parse date and set to midnight UTC
            date_str = time_obj['date']
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        
        return None


