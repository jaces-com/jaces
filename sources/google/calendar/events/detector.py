"""Google Calendar events transition detector using event boundaries."""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import json
from sources.base.transitions.categorical import BaseCategoricalTransitionDetector, Transition


class CalendarEventsTransitionDetector(BaseCategoricalTransitionDetector):
    """
    Event-based calendar transition detector.
    
    Creates transitions at calendar event boundaries (start/end times).
    Perfect for discrete events with clear temporal boundaries.
    """
    
    def __init__(
        self,
        min_confidence: float = 0.95,  # High confidence for explicit boundaries
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize calendar events transition detector.
        
        Args:
            min_confidence: Minimum confidence threshold (default high for events)
            config: Optional signal configuration dict
        """
        super().__init__(min_confidence=min_confidence)
        self.config = config
    
    def get_signal_name(self) -> str:
        return "google_calendar_events"
    
    def get_source_name(self) -> str:
        return "google"
    
    def detect_transitions(
        self,
        signals: List[Dict[str, Any]],
        start_time: datetime,
        end_time: datetime
    ) -> List[Transition]:
        """
        Detect transitions at calendar event boundaries.
        
        Args:
            signals: List of signal dictionaries containing calendar events
            
        Returns:
            List of transitions at event start/end times
        """
        if not signals:
            return []
        
        transitions = []
        
        # Process each signal as a calendar event
        for signal in signals:
            # Parse metadata to get event timing
            metadata = signal.get('source_metadata', {})
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except:
                    metadata = {}
            
            # Get event timing information
            timing = metadata.get('timing', {})
            event_info = metadata.get('event', {})
            
            # Get start and end times
            if timing.get('start'):
                start_time = datetime.fromisoformat(timing['start'].replace('Z', '+00:00'))
            else:
                start_time = datetime.fromisoformat(signal['timestamp'].replace('Z', '+00:00'))
            
            # Calculate end time
            if timing.get('end'):
                end_time = datetime.fromisoformat(timing['end'].replace('Z', '+00:00'))
            elif timing.get('duration_minutes'):
                end_time = start_time + timedelta(minutes=timing['duration_minutes'])
            elif event_info.get('is_all_day'):
                # All-day events end at 23:59:59
                end_time = start_time.replace(hour=23, minute=59, second=59)
            else:
                # Default to 1 hour duration
                end_time = start_time + timedelta(hours=1)
            
            # Get event title
            title = signal.get('signal_value', 'Unknown Event')
            
            # Create start transition
            start_transition = Transition(
                transition_time=start_time,
                transition_type='changepoint',  # Using standard type
                change_magnitude=1.0,  # Event presence
                change_direction='increase',
                before_mean=0.0,  # No event before
                before_std=0.0,
                after_mean=1.0,   # Event active
                after_std=0.0,
                confidence=0.98,  # High confidence for explicit boundaries
                detection_method='event_boundary',
                metadata={
                    'event_title': title,
                    'event_type': 'calendar_start',
                    'location': event_info.get('location'),
                    'is_all_day': event_info.get('is_all_day', False),
                    'duration_minutes': timing.get('duration_minutes'),
                    'source_event_id': signal.get('source_event_id')
                }
            )
            transitions.append(start_transition)
            
            # Create end transition
            end_transition = Transition(
                transition_time=end_time,
                transition_type='changepoint',  # Using standard type
                change_magnitude=1.0,  # Event absence
                change_direction='decrease',
                before_mean=1.0,  # Event was active
                before_std=0.0,
                after_mean=0.0,   # No event after
                after_std=0.0,
                confidence=0.98,  # High confidence for explicit boundaries
                detection_method='event_boundary',
                metadata={
                    'event_title': title,
                    'event_type': 'calendar_end',
                    'location': event_info.get('location'),
                    'is_all_day': event_info.get('is_all_day', False),
                    'duration_minutes': timing.get('duration_minutes'),
                    'source_event_id': signal.get('source_event_id')
                }
            )
            transitions.append(end_transition)
        
        # Sort transitions by time
        transitions.sort(key=lambda t: t.transition_time)
        
        # Filter by minimum confidence and time window
        transitions = [
            t for t in transitions 
            if t.confidence >= self.min_confidence
            and start_time <= t.transition_time <= end_time
        ]
        
        return transitions