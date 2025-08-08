"""Abstract base class for transition detectors."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass


@dataclass
class Transition:
    """Represents a state transition in a signal."""
    start_time: datetime
    end_time: datetime
    from_state: Any
    to_state: Any
    confidence: float
    metadata: Optional[Dict[str, Any]] = None


class BaseTransitionDetector(ABC):
    """
    Abstract base class for all transition detection algorithms.
    
    Transition detectors identify state changes in time series data.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the transition detector.
        
        Args:
            config: Optional configuration for the detector
        """
        self.config = config or {}
    
    @abstractmethod
    def detect_transitions(
        self,
        data: List[Dict[str, Any]],
        signal_type: str
    ) -> List[Transition]:
        """
        Detect transitions in the provided data.
        
        Args:
            data: Time series data to analyze
            signal_type: Type of signal being analyzed
            
        Returns:
            List of detected transitions
        """
        pass
    
    @abstractmethod
    def get_states(self, data: List[Dict[str, Any]]) -> List[Any]:
        """
        Extract states from the data.
        
        Args:
            data: Time series data
            
        Returns:
            List of states in the data
        """
        pass
    
    @abstractmethod
    def calculate_confidence(
        self,
        transition: Transition,
        data: List[Dict[str, Any]]
    ) -> float:
        """
        Calculate confidence score for a transition.
        
        Args:
            transition: The transition to score
            data: The data context
            
        Returns:
            Confidence score between 0 and 1
        """
        pass
    
    def filter_transitions(
        self,
        transitions: List[Transition],
        min_confidence: float = 0.5,
        min_duration_seconds: Optional[int] = None
    ) -> List[Transition]:
        """
        Filter transitions based on criteria.
        
        Args:
            transitions: List of transitions to filter
            min_confidence: Minimum confidence threshold
            min_duration_seconds: Minimum duration in seconds
            
        Returns:
            Filtered list of transitions
        """
        filtered = [t for t in transitions if t.confidence >= min_confidence]
        
        if min_duration_seconds:
            filtered = [
                t for t in filtered
                if (t.end_time - t.start_time).total_seconds() >= min_duration_seconds
            ]
        
        return filtered
    
    def merge_adjacent_transitions(
        self,
        transitions: List[Transition],
        gap_threshold_seconds: int = 60
    ) -> List[Transition]:
        """
        Merge adjacent transitions with small gaps.
        
        Args:
            transitions: List of transitions
            gap_threshold_seconds: Maximum gap to merge
            
        Returns:
            Merged list of transitions
        """
        if not transitions:
            return []
        
        # Sort by start time
        sorted_transitions = sorted(transitions, key=lambda t: t.start_time)
        merged = [sorted_transitions[0]]
        
        for current in sorted_transitions[1:]:
            last = merged[-1]
            gap = (current.start_time - last.end_time).total_seconds()
            
            # Merge if gap is small and states match
            if gap <= gap_threshold_seconds and last.to_state == current.from_state:
                # Create merged transition
                merged[-1] = Transition(
                    start_time=last.start_time,
                    end_time=current.end_time,
                    from_state=last.from_state,
                    to_state=current.to_state,
                    confidence=min(last.confidence, current.confidence),
                    metadata={
                        'merged': True,
                        'original_count': 2 + last.metadata.get('original_count', 1)
                        if last.metadata else 2
                    }
                )
            else:
                merged.append(current)
        
        return merged