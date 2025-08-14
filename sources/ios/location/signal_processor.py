"""Signal processor for iOS location signals - queues transition detection."""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from celery import signature, group


class SignalProcessor:
    """
    Signal processor that queues transition detection for location-based signals.
    Handles multiple signals: speed, coordinates, altitude.
    """
    
    def __init__(self, signal_names: Optional[List[str]] = None):
        """
        Initialize the signal processor.
        
        Args:
            signal_names: List of signal names to process, defaults to all location signals
        """
        if signal_names is None:
            signal_names = ['ios_speed', 'ios_coordinates', 'ios_altitude']
        self.signal_names = signal_names
        self.source_name = 'ios'
    
    def queue_transition_detection(
        self,
        signal_name: str,
        start_time: datetime,
        end_time: datetime,
        timezone: str = "America/Chicago"
    ) -> Optional[str]:
        """
        Queue transition detection for a specific signal.
        
        Args:
            signal_name: The specific signal to process
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
                    signal_name,
                    date,
                    start_time.isoformat(),
                    end_time.isoformat(),
                    timezone
                ],
                queue='celery'
            )
            
            result = transition_task.apply_async()
            print(f"[SignalProcessor] Queued transition detection for {signal_name}: {result.id}")
            return result.id
            
        except Exception as e:
            print(f"[SignalProcessor] Failed to queue transition detection for {signal_name}: {e}")
            return None
    
    def process_after_stream(
        self,
        stream_data: Dict[str, Any],
        signals_created: Dict[str, int]
    ) -> Dict[str, Any]:
        """
        Process after stream processing completes.
        
        Args:
            stream_data: Original stream data with metadata
            signals_created: Dictionary of signal_name -> count created
            
        Returns:
            Processing result with transition detection task info
        """
        result = {
            'signals_created': signals_created,
            'transition_detection_queued': {}
        }
        
        # Check if any signals were created
        total_signals = sum(signals_created.values())
        if total_signals == 0:
            print(f"[SignalProcessor] No signals created, skipping transition detection")
            return result
        
        # Extract time window from stream metadata
        metadata = stream_data.get('metadata', {})
        
        # Use the batch time range from the stream
        if 'start_time' in metadata and 'end_time' in metadata:
            start_time = datetime.fromisoformat(metadata['start_time'])
            end_time = datetime.fromisoformat(metadata['end_time'])
        elif 'batch_start' in metadata and 'batch_end' in metadata:
            start_time = datetime.fromisoformat(metadata['batch_start'])
            end_time = datetime.fromisoformat(metadata['batch_end'])
        else:
            # Default to last hour if no time range specified
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)
        
        # Queue transition detection for each signal type that has data
        for signal_name in self.signal_names:
            # Only queue if this signal had data created
            if signals_created.get(signal_name, 0) > 0:
                task_id = self.queue_transition_detection(
                    signal_name=signal_name,
                    start_time=start_time,
                    end_time=end_time
                )
                
                if task_id:
                    result['transition_detection_queued'][signal_name] = task_id
        
        return result
    
    def queue_batch_transition_detection(
        self,
        start_time: datetime,
        end_time: datetime,
        timezone: str = "America/Chicago"
    ) -> Optional[List[str]]:
        """
        Queue transition detection for all location signals in parallel.
        
        Args:
            start_time: Start of the time window
            end_time: End of the time window
            timezone: Timezone for detection
            
        Returns:
            List of task IDs if queued successfully
        """
        try:
            date = start_time.strftime('%Y-%m-%d')
            
            # Create a group of parallel tasks
            tasks = []
            for signal_name in self.signal_names:
                task = signature(
                    'run_single_signal_transition_detection',
                    args=[
                        signal_name,
                        date,
                        start_time.isoformat(),
                        end_time.isoformat(),
                        timezone
                    ],
                    queue='celery'
                )
                tasks.append(task)
            
            # Execute tasks in parallel
            job = group(tasks)
            result = job.apply_async()
            
            print(f"[SignalProcessor] Queued {len(tasks)} transition detection tasks in parallel")
            return result.id
            
        except Exception as e:
            print(f"[SignalProcessor] Failed to queue batch transition detection: {e}")
            return None