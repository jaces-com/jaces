"""Sleep transition detector using categorical value changes."""

from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from sources.base.transitions.categorical import BaseCategoricalTransitionDetector, Transition


class SleepTransitionDetector(BaseCategoricalTransitionDetector):
    """
    Sleep transition detector for categorical sleep data.
    
    Detects changes in categorical sleep values without semantic interpretation.
    Records when the categorical value changes and captures the raw values.
    
    Since sleep data is categorical, we detect transitions by identifying
    value changes rather than using PELT.
    """
    
    def __init__(
        self,
        min_confidence: float = 0.85,
        min_duration_minutes: int = 5,  # Minimum duration to consider a valid state
        gap_threshold_minutes: int = 30  # Gap to consider sleep session ended
    ):
        """
        Initialize sleep transition detector.
        
        Args:
            min_confidence: Minimum confidence threshold
            min_duration_minutes: Minimum minutes in a state to be valid
            gap_threshold_minutes: Minutes of gap to end sleep session
        """
        super().__init__(min_confidence)
        self.min_duration_minutes = min_duration_minutes
        self.gap_threshold_minutes = gap_threshold_minutes
        
        # Track any non-empty categorical values (no semantic filtering)
        self.min_value_duration_minutes = min_duration_minutes
    
    def get_signal_name(self) -> str:
        """Return the signal name this detector handles."""
        return 'apple_ios_sleep'
    
    def get_source_name(self) -> str:
        """Return the source name this detector handles."""
        return 'ios'
    
    def detect_transitions(
        self,
        signals: List[Dict[str, Any]],
        start_time: datetime,
        end_time: datetime
    ) -> List[Transition]:
        """Detect sleep state transitions from categorical data."""
        if not signals:
            return []
        
        # Sort signals by timestamp
        sorted_signals = sorted(signals, key=lambda x: x['timestamp'])
        
        # Debug logging
        print(f"[SleepTransitionDetector] Processing {len(sorted_signals)} signals")
        unique_values = set(s.get('signal_value', '').lower() for s in sorted_signals)
        print(f"[SleepTransitionDetector] Unique values found: {unique_values}")
        
        transitions = []
        previous_value = None
        previous_timestamp = None
        value_start_time = None
        value_duration_minutes = 0
        
        for i, signal in enumerate(sorted_signals):
            current_value = signal.get('signal_value', '').lower()
            current_timestamp = signal['timestamp']
            
            # Skip empty values
            if not current_value:
                if i < 5:  # Log first few skips
                    print(f"[SleepTransitionDetector] Skipping empty value")
                continue
            
            # Check for gap indicating data discontinuity
            if previous_timestamp:
                gap_minutes = (current_timestamp - previous_timestamp).total_seconds() / 60
                if gap_minutes > self.gap_threshold_minutes:
                    # Add data gap transition
                    if previous_value:
                        transitions.append(Transition(
                            transition_time=previous_timestamp,
                            transition_type='data_gap',
                            change_magnitude=None,
                            change_direction=None,
                            before_mean=None,
                            before_std=None,
                            after_mean=None,
                            after_std=None,
                            confidence=1.0,
                            detection_method='gap_detection',
                            metadata={
                                'gap_minutes': gap_minutes,
                                'last_value': previous_value
                            }
                        ))
                    # Reset value tracking
                    previous_value = None
                    value_start_time = None
            
            # Detect value change
            if previous_value and current_value != previous_value:
                # Calculate duration of previous value
                if value_start_time:
                    value_duration_minutes = (current_timestamp - value_start_time).total_seconds() / 60
                
                # Only create transition if previous value lasted long enough
                if value_duration_minutes >= self.min_value_duration_minutes:
                    transition = Transition(
                        transition_time=current_timestamp,
                        transition_type='categorical_change',
                        change_magnitude=None,  # Not applicable for categorical
                        change_direction=None,  # Not applicable for categorical
                        before_mean=None,
                        before_std=None,
                        after_mean=None,
                        after_std=None,
                        confidence=self._calculate_confidence(
                            signal, 
                            value_duration_minutes
                        ),
                        detection_method='categorical_change',
                        metadata={
                            'previous_value': previous_value,
                            'current_value': current_value,
                            'previous_value_duration_minutes': value_duration_minutes,
                            'source_metadata': signal.get('source_metadata', {})
                        }
                    )
                    transitions.append(transition)
                    print(f"[SleepTransitionDetector] Created transition: {previous_value} → {current_value}")
                else:
                    print(f"[SleepTransitionDetector] Value duration too short ({value_duration_minutes:.1f} < {self.min_value_duration_minutes} min): {previous_value}")
                
                # Update value tracking
                value_start_time = current_timestamp
            elif not previous_value:
                # First valid value
                value_start_time = current_timestamp
            
            previous_value = current_value
            previous_timestamp = current_timestamp
        
        # Handle end of data - no semantic assumptions
        return transitions
    
    
    def _calculate_confidence(
        self,
        signal: Dict[str, Any],
        value_duration_minutes: float
    ) -> float:
        """Calculate confidence based on signal quality and value duration."""
        base_confidence = signal.get('confidence', 0.9)
        
        # Boost confidence for longer-lasting values
        if value_duration_minutes >= 30:
            duration_boost = 0.05
        elif value_duration_minutes >= 15:
            duration_boost = 0.03
        else:
            duration_boost = 0
        
        return min(base_confidence + duration_boost, 0.99)