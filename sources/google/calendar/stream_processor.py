"""Generic configuration-driven stream processor for Google Calendar."""

from datetime import datetime, timezone as tz
from typing import Dict, Any, List, Optional
from uuid import uuid4
import json
from pathlib import Path
from sqlalchemy import text
from sources.base.processing.dedup import generate_idempotency_key
from sources.base.processing.normalization import DataNormalizer
from sources.base.processing.validation import DataValidator


class StreamProcessor:
    """
    Generic stream processor for Google Calendar events.
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
        self.source_name = 'google'  # Google Calendar is always from Google source
        self.stream_type = 'events'
        self.dedup_strategy = 'single'
        self.event_id_fields = ['id']  # Google Calendar event ID field
    
    def _detect_stream_name(self) -> str:
        """
        Auto-detect stream name from the file path.
        Assumes structure: sources/<source>/<stream>/stream_processor.py
        """
        # Get the path of this file
        current_path = Path(__file__).resolve()
        
        # Extract source and stream from path
        # Expected: .../sources/google/calendar/stream_processor.py
        parts = current_path.parts
        
        # Find 'sources' in the path
        try:
            sources_idx = parts.index('sources')
            if sources_idx + 2 < len(parts):
                source = parts[sources_idx + 1]
                stream = parts[sources_idx + 2]
                # Construct stream name (e.g., google_calendar)
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
        # For event-based streams, we expect an 'events' array
        if self.stream_type == 'events':
            return self._process_events(stream_data, signal_configs, db)
        else:
            # Could extend to other stream types (continuous, categorical, etc.)
            return {
                "status": "error",
                "reason": f"Unsupported stream type: {self.stream_type}",
                "stream_name": self.stream_name
            }
    
    def _process_events(
        self,
        stream_data: Dict[str, Any],
        signal_configs: Dict[str, str],
        db
    ) -> Dict[str, Any]:
        """Process event-based stream data."""
        
        events = stream_data.get('events', [])
        sync_metadata = stream_data.get('sync_metadata', {})
        
        # Track signals created per signal type
        signals_created = {}
        
        # Process for each signal configured in the database
        for signal_name, signal_id in signal_configs.items():
            count = 0
            
            # Process each event for this signal
            print(f"Processing {len(events)} events for signal {signal_name}")
            for event_wrapper in events:
                # Extract calendar and event info (Google Calendar specific structure)
                # This could be made more generic with field mapping in config
                calendar_info = event_wrapper.get('calendar', {})
                event = event_wrapper.get('event', {})
                
                # Apply any filtering rules
                if not self._should_process_event(event, signal_name):
                    print(f"Skipping event {event.get('id', 'unknown')} - failed should_process check")
                    continue
                
                # Parse timestamps
                start_time = self._parse_event_time(event.get('start'))
                end_time = self._parse_event_time(event.get('end'))
                
                if not start_time or not end_time:
                    continue
                
                # Extract signal value
                signal_value = self._extract_signal_value(event, signal_name)
                
                # Generate source event ID using configured fields
                event_data = self._build_event_data(event, calendar_info)
                idempotency_key = generate_idempotency_key(
                    self.dedup_strategy, 
                    start_time, 
                    event_data
                )
                
                # Build metadata
                metadata = self._build_metadata(event, calendar_info, start_time, end_time)
                
                # Calculate confidence
                confidence = self._calculate_confidence(event, signal_name)
                
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
                        "timestamp": start_time,
                        "confidence": confidence,
                        "signal_name": signal_name,
                        "signal_value": signal_value,
                        "idempotency_key": idempotency_key,
                        "source_metadata": json.dumps(metadata),
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                )
                count += 1
                if count % 50 == 0:
                    print(f"Inserted {count} signals so far for {signal_name}")
            
            print(f"Total signals created for {signal_name}: {count}")
            signals_created[signal_name] = count
        
        # Commit all signals
        db.commit()
        
        return {
            "status": "success",
            "stream_name": self.stream_name,
            "records_processed": len(events),
            "signals_created": signals_created,
            "total_signals": sum(signals_created.values()),
            "sync_metadata": sync_metadata
        }
    
    def _should_process_event(self, event: Dict[str, Any], signal_name: str) -> bool:
        """
        Determine if an event should be processed based on signal configuration.
        """
        # Skip declined or cancelled events
        status = event.get('status', 'confirmed')
        if status in ['declined', 'cancelled']:
            print(f"  Skipping due to status: {status}")
            return False
        
        # Require event ID
        if not event.get('id'):
            print(f"  Skipping - no event ID")
            return False
        
        # Could add more filtering based on signal_config metadata
        # For example, filtering by event types if specified
        # NOTE: Commenting out for now - Google Calendar events don't have eventType field
        # metadata = signal_config.get('metadata', {})
        # if 'event_types' in metadata:
        #     event_type = event.get('eventType', 'default')
        #     if event_type not in metadata['event_types']:
        #         return False
        
        return True
    
    def _extract_signal_value(self, event: Dict[str, Any], signal_name: str) -> str:
        """
        Extract the signal value from the event.
        """
        # Default to event summary/title
        summary = event.get('summary', 'Untitled Event')
        
        # Handle all-day events
        if self._is_all_day_event(event):
            summary = f"[All Day] {summary}"
        
        return summary
    
    def _build_event_data(self, event: Dict[str, Any], calendar_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build event data dictionary for deduplication based on configured fields.
        """
        event_data = {}
        
        # Add configured fields for deduplication
        for field in self.event_id_fields:
            if field == 'event_id':
                event_data['event_id'] = event.get('id')
            elif field == 'calendar_id':
                event_data['calendar_id'] = calendar_info.get('id')
            elif field in event:
                event_data[field] = event[field]
        
        # Always include summary for additional uniqueness
        event_data['summary'] = event.get('summary', '')
        
        return event_data
    
    def _build_metadata(
        self, 
        event: Dict[str, Any], 
        calendar_info: Dict[str, Any],
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """Build structured metadata for the signal."""
        
        status = event.get('status', 'confirmed')
        
        metadata = {
            'calendar': {
                'id': calendar_info.get('id'),
                'name': calendar_info.get('summary'),
                'timezone': calendar_info.get('timeZone')
            },
            'event': {
                'id': event.get('id'),
                'status': status,
                'event_type': event.get('eventType', 'default'),
                'visibility': event.get('visibility', 'default'),
                'transparency': event.get('transparency', 'opaque'),
                'is_recurring': bool(event.get('recurringEventId')),
                'is_all_day': self._is_all_day_event(event),
                'response_status': event.get('responseStatus'),
                'html_link': event.get('htmlLink')
            },
            'timing': {
                'start': start_time.isoformat(),
                'end': end_time.isoformat(),
                'duration_minutes': int((end_time - start_time).total_seconds() / 60)
            }
        }
        
        # Add optional fields if present
        if event.get('location'):
            metadata['event']['location'] = event['location']
        if event.get('description'):
            metadata['event']['description'] = event['description'][:500]
        if event.get('attendees'):
            metadata['attendees'] = [
                {
                    'email': a.get('email'),
                    'response_status': a.get('responseStatus'),
                    'optional': a.get('optional', False)
                }
                for a in event['attendees'][:20]
            ]
        if event.get('organizer'):
            metadata['organizer'] = {
                'email': event['organizer'].get('email'),
                'display_name': event['organizer'].get('displayName')
            }
        if event.get('created'):
            metadata['timestamps'] = {
                'created': event['created'],
                'updated': event.get('updated', event['created'])
            }
        
        return metadata
    
    def _calculate_confidence(self, event: Dict[str, Any], signal_name: str) -> float:
        """Calculate confidence score for the signal."""
        
        response_status = event.get('responseStatus', 'accepted')
        
        if response_status == 'accepted' or not response_status:
            confidence = 0.95
        elif response_status == 'tentative':
            confidence = 0.7
        elif response_status == 'needsAction':
            confidence = 0.6
        else:
            confidence = 0.5
        
        return confidence
    
    def _parse_event_time(self, time_obj: Optional[Dict[str, Any]]) -> Optional[datetime]:
        """Parse event time object to datetime."""
        if not time_obj:
            return None
        
        # Handle dateTime format (with time)
        if 'dateTime' in time_obj:
            # Use DataNormalizer for consistent timestamp parsing
            return DataNormalizer.normalize_timestamp(time_obj['dateTime'])
        
        # Handle date format (all-day events)
        elif 'date' in time_obj:
            # Parse date and set to midnight UTC
            date_str = time_obj['date']
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            return dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=tz.utc).replace(tzinfo=None)
        
        return None
    
    def _is_all_day_event(self, event: Dict[str, Any]) -> bool:
        """Check if an event is an all-day event."""
        start = event.get('start', {})
        end = event.get('end', {})
        # All-day events have 'date' instead of 'dateTime'
        return 'date' in start and 'date' in end