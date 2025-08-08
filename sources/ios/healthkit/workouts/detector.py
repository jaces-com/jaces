"""Workout transition detector for episodic workout events."""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import numpy as np

from sources.base.transitions.categorical import BaseCategoricalTransitionDetector, Transition


class WorkoutsTransitionDetector(BaseCategoricalTransitionDetector):
    """
    Workout transition detector for episodic workout data.
    
    Detects event boundaries for workout episodes without semantic interpretation.
    Records start and end times of workout events.
    
    Workouts are episodic events with start/end times rather than
    continuous signals, so we generate transitions from the event metadata.
    """
    
    def __init__(
        self,
        min_confidence: float = 0.9,
        min_workout_duration_minutes: int = 5,  # Minimum duration for valid workout
        rest_threshold_minutes: int = 30  # Time after workout to return to rest
    ):
        """
        Initialize workout transition detector.
        
        Args:
            min_confidence: Minimum confidence threshold
            min_workout_duration_minutes: Minimum workout duration to process
            rest_threshold_minutes: Minutes after workout to transition to rest
        """
        super().__init__(min_confidence)
        self.min_workout_duration_minutes = min_workout_duration_minutes
        self.rest_threshold_minutes = rest_threshold_minutes
    
    def get_signal_name(self) -> str:
        """Return the signal name this detector handles."""
        return 'apple_ios_workouts'
    
    def get_source_name(self) -> str:
        """Return the source name this detector handles."""
        return 'ios'
    
    def detect_transitions(
        self,
        signals: List[Dict[str, Any]],
        start_time: datetime,
        end_time: datetime
    ) -> List[Transition]:
        """Detect workout transitions from episodic workout events."""
        if not signals:
            return []
        
        # Sort signals by timestamp
        sorted_signals = sorted(signals, key=lambda x: x['timestamp'])
        
        transitions = []
        
        for signal in sorted_signals:
            # Extract workout metadata
            metadata = {}
            if isinstance(signal.get('source_metadata'), dict):
                metadata = signal['source_metadata']
            elif isinstance(signal.get('source_metadata'), str):
                try:
                    import json
                    metadata = json.loads(signal['source_metadata'])
                except:
                    metadata = {}
            
            # Get workout details
            workout_type = metadata.get('workout_type', '').lower()
            duration_minutes = metadata.get('duration_minutes', 0)
            
            # Skip very short workouts
            if duration_minutes < self.min_workout_duration_minutes:
                continue
            
            # Get workout timestamps
            workout_start = signal['timestamp']
            
            # Calculate workout end time from duration if available
            if duration_minutes > 0:
                workout_end = workout_start + timedelta(minutes=duration_minutes)
            else:
                # Fallback: assume 30 minute workout
                workout_end = workout_start + timedelta(minutes=30)
            
            # Ensure workout doesn't extend past end_time
            if workout_end > end_time:
                workout_end = end_time
            
            # Create workout start transition
            transitions.append(Transition(
                transition_time=workout_start,
                transition_type='event_start',
                change_magnitude=None,
                change_direction=None,
                before_mean=None,
                before_std=None,
                after_mean=None,
                after_std=None,
                confidence=self._calculate_confidence(signal, metadata),
                detection_method='episodic_event',
                metadata={
                    'event_type': 'workout',
                    'workout_type': workout_type,
                    'duration_minutes': duration_minutes,
                    'calories': metadata.get('calories'),
                    'distance_km': metadata.get('distance_km'),
                    'source_metadata': metadata
                }
            ))
            
            # Create workout end transition
            transitions.append(Transition(
                transition_time=workout_end,
                transition_type='event_end',
                change_magnitude=None,
                change_direction=None,
                before_mean=None,
                before_std=None,
                after_mean=None,
                after_std=None,
                confidence=self._calculate_confidence(signal, metadata),
                detection_method='episodic_event',
                metadata={
                    'event_type': 'workout',
                    'workout_type': workout_type,
                    'duration_minutes': duration_minutes,
                    'calories': metadata.get('calories'),
                    'distance_km': metadata.get('distance_km'),
                    'source_metadata': metadata
                }
            ))
        
        # Merge overlapping workouts
        transitions = self._merge_overlapping_workouts(transitions)
        
        return transitions
    
    def _merge_overlapping_workouts(
        self,
        transitions: List[Transition]
    ) -> List[Transition]:
        """Merge overlapping workout periods."""
        if len(transitions) <= 2:
            return transitions
        
        # Sort by timestamp
        sorted_transitions = sorted(transitions, key=lambda x: x.timestamp)
        
        merged = []
        i = 0
        
        while i < len(sorted_transitions):
            current = sorted_transitions[i]
            
            if current.transition_type == 'event_start':
                # This is a workout start
                workout_start = current
                workout_end = None
                
                # Find corresponding end
                j = i + 1
                while j < len(sorted_transitions):
                    if sorted_transitions[j].transition_type == 'event_end':
                        workout_end = sorted_transitions[j]
                        break
                    j += 1
                
                if workout_end:
                    # Check if there's another workout starting before this one ends
                    overlapping = False
                    for k in range(i + 1, j):
                        if sorted_transitions[k].transition_type == 'event_start':
                            overlapping = True
                            break
                    
                    if overlapping:
                        # Merge workouts - keep the start, skip intermediate transitions
                        merged.append(workout_start)
                        # Find the last workout end after all overlaps
                        last_end_idx = j
                        for k in range(j + 1, len(sorted_transitions)):
                            if sorted_transitions[k].transition_type == 'event_end':
                                last_end_idx = k
                        
                        # Update the final end transition
                        final_end = sorted_transitions[last_end_idx]
                        final_end.metadata['merged_events'] = True
                        merged.append(final_end)
                        i = last_end_idx + 1
                    else:
                        # No overlap, add both transitions
                        merged.append(workout_start)
                        merged.append(workout_end)
                        i = j + 1
                else:
                    # No corresponding end found
                    merged.append(current)
                    i += 1
            else:
                # This shouldn't happen if transitions are properly paired
                merged.append(current)
                i += 1
        
        return merged
    
    def _calculate_confidence(
        self,
        signal: Dict[str, Any],
        metadata: Dict[str, Any]
    ) -> float:
        """Calculate confidence based on workout data completeness."""
        base_confidence = signal.get('confidence', 0.9)
        
        # Boost confidence based on data quality
        boosts = 0.0
        
        # Has duration data
        if metadata.get('duration_minutes', 0) > 0:
            boosts += 0.02
        
        # Has calorie data  
        if metadata.get('calories', 0) > 0:
            boosts += 0.02
        
        # Has distance data
        if metadata.get('distance_km', 0) > 0:
            boosts += 0.02
        
        # Has specific workout type
        if metadata.get('workout_type'):
            boosts += 0.01
        
        return min(base_confidence + boosts, 0.99)