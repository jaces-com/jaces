"""Signal processor for Google Calendar events - queues transition detection."""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from celery import signature


class SignalProcessor:
    """
    Signal processor that queues transition detection for calendar events.
    Called after stream processing completes.
    """
    
    def __init__(self, signal_name: str = 'google_calendar_events'):
        """
        Initialize the signal processor.
        
        Args:
            signal_name: The signal name to process
        """
        self.signal_name = signal_name
        self.source_name = 'google'
    
    def queue_transition_detection(
        self,
        start_time: datetime,
        end_time: datetime,
        timezone: str = "America/Chicago"
    ) -> Optional[str]:
        """
        Queue transition detection for the processed signals.
        
        Args:
            start_time: Start of the time window
            end_time: End of the time window
            timezone: Timezone for detection
            
        Returns:
            Task ID if queued successfully, None otherwise
        """
        try:
            # Format date for the task
            date = start_time.strftime('%Y-%m-%d')
            
            # Queue single signal transition detection
            transition_task = signature(
                'run_single_signal_transition_detection',
                args=[
                    self.signal_name,
                    date,
                    start_time.isoformat(),
                    end_time.isoformat(),
                    timezone
                ],
                queue='celery'
            )
            
            result = transition_task.apply_async()
            print(f"[SignalProcessor] Queued transition detection for {self.signal_name}: {result.id}")
            return result.id
            
        except Exception as e:
            print(f"[SignalProcessor] Failed to queue transition detection: {e}")
            return None
    
    def process_after_stream(
        self,
        stream_data: Dict[str, Any],
        signals_created: int
    ) -> Dict[str, Any]:
        """
        Process after stream processing completes.
        
        Args:
            stream_data: Original stream data with metadata
            signals_created: Number of signals created
            
        Returns:
            Processing result with transition detection task info
        """
        result = {
            'signals_created': signals_created,
            'transition_detection_queued': False
        }
        
        if signals_created == 0:
            print(f"[SignalProcessor] No signals created, skipping transition detection")
            return result
        
        # Extract time window from stream metadata
        metadata = stream_data.get('metadata', {})
        
        # For calendar events, use the event time range
        if 'start_time' in metadata and 'end_time' in metadata:
            start_time = datetime.fromisoformat(metadata['start_time'])
            end_time = datetime.fromisoformat(metadata['end_time'])
        else:
            # Default to today if no time range specified
            now = datetime.now()
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Queue transition detection
        # TODO: Get timezone from database or use default
        task_id = self.queue_transition_detection(
            start_time=start_time,
            end_time=end_time
        )
        
        if task_id:
            result['transition_detection_queued'] = True
            result['transition_task_id'] = task_id
        
        return result