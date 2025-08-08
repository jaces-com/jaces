"""Base class for signal-specific transition detection."""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import uuid


@dataclass
class Transition:
    """Represents a detected changepoint or data gap in a signal."""
    transition_time: datetime
    transition_type: str  # 'changepoint' or 'data_gap'
    change_magnitude: Optional[float]  # Size of the change
    change_direction: Optional[str]  # 'increase', 'decrease', or None for gaps
    before_mean: Optional[float]  # Mean value before transition
    before_std: Optional[float]  # Std deviation before transition
    after_mean: Optional[float]  # Mean value after transition
    after_std: Optional[float]  # Std deviation after transition
    confidence: float
    detection_method: str
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "id": str(uuid.uuid4()),
            "transition_time": self.transition_time,
            "transition_type": self.transition_type,
            "change_magnitude": self.change_magnitude,
            "change_direction": self.change_direction,
            "before_mean": self.before_mean,
            "before_std": self.before_std,
            "after_mean": self.after_mean,
            "after_std": self.after_std,
            "confidence": self.confidence,
            "detection_method": self.detection_method,
            "transition_metadata": self.metadata or {}
        }


class BaseCategoricalTransitionDetector(ABC):
    """
    Base class for implementing signal-specific transition detection.

    Each signal type (e.g., speed, altitude, coordinates) should implement
    its own transition detection logic that understands the semantics of that data.
    """

    def __init__(self, min_confidence: float = 0.3):
        """
        Initialize the transition detector.

        Args:
            min_confidence: Minimum confidence threshold for transitions
        """
        self.min_confidence = min_confidence

    @abstractmethod
    def get_signal_name(self) -> str:
        """Return the signal name this detector handles."""
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """Return the source name this detector handles."""
        pass

    @abstractmethod
    def detect_transitions(
        self,
        signals: List[Dict[str, Any]],
        start_time: datetime,
        end_time: datetime
    ) -> List[Transition]:
        """
        Detect transitions in the given signals.

        Args:
            signals: List of signal dictionaries from the database
            start_time: Start of the time window
            end_time: End of the time window

        Returns:
            List of detected transitions
        """
        pass

    def validate_transitions(
        self,
        transitions: List[Transition],
        start_time: datetime,
        end_time: datetime
    ) -> List[Transition]:
        """
        Validate transitions are within the time window and properly ordered.

        Args:
            transitions: List of transitions
            start_time: Start of the time window
            end_time: End of the time window

        Returns:
            Validated transitions
        """
        validated = []

        for transition in transitions:
            # Ensure transition is within time window
            if start_time <= transition.transition_time <= end_time:
                # Filter by confidence threshold
                if transition.confidence >= self.min_confidence:
                    validated.append(transition)

        # Sort by transition time
        validated.sort(key=lambda t: t.transition_time)

        return validated

    def detect_collection_periods(
        self,
        signals: List[Dict[str, Any]],
        gap_threshold_seconds: int = 300  # 5 minutes default
    ) -> List[Tuple[datetime, datetime, List[Dict[str, Any]]]]:
        """
        Detect periods of continuous data collection based on gaps between signals.

        Args:
            signals: List of signal dictionaries from the database
            gap_threshold_seconds: Maximum seconds between signals to consider continuous

        Returns:
            List of tuples: (start_time, end_time, signals_in_period)
        """
        if not signals:
            return []

        # Sort signals by timestamp
        sorted_signals = sorted(signals, key=lambda s: s['timestamp'])

        periods = []
        current_period_start = sorted_signals[0]['timestamp']
        current_period_signals = [sorted_signals[0]]

        for i in range(1, len(sorted_signals)):
            current_signal = sorted_signals[i]
            prev_signal = sorted_signals[i-1]

            # Calculate time gap
            time_gap = (current_signal['timestamp'] -
                        prev_signal['timestamp']).total_seconds()

            if time_gap > gap_threshold_seconds:
                # Gap detected - end current period
                periods.append((
                    current_period_start,
                    prev_signal['timestamp'],
                    current_period_signals
                ))

                # Start new period
                current_period_start = current_signal['timestamp']
                current_period_signals = [current_signal]
            else:
                # Continue current period
                current_period_signals.append(current_signal)

        # Add final period
        if current_period_signals:
            periods.append((
                current_period_start,
                current_period_signals[-1]['timestamp'],
                current_period_signals
            ))

        return periods
