"""Google Calendar events transition detector using PELT algorithm."""

from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from sources.base.transitions.pelt import BasePELTTransitionDetector, Transition


class CalendarEventsTransitionDetector(BasePELTTransitionDetector):
    """
    PELT-based calendar events transition detector.
    
    Detects significant changes in calendar event density and patterns.
    Tracks transitions between different meeting intensities.
    
    Uses PELT to find optimal change points where calendar activity changes.
    """
    
    def __init__(
        self,
        min_confidence: float = 0.75,
        gap_threshold_seconds: int = 3600,  # 1 hour
        min_segment_size: int = 5,
        penalty_multiplier: float = 1.2,
        config: Optional[Dict[str, Any]] = None  # Signal configuration
    ):
        """
        Initialize calendar events transition detector.
        
        Args:
            min_confidence: Minimum confidence threshold
            gap_threshold_seconds: Gap size to consider collection stopped
            min_segment_size: Minimum points per PELT segment
            penalty_multiplier: Adjust PELT sensitivity (higher = fewer transitions)
            config: Optional signal configuration dict
        """
        super().__init__(
            min_confidence=min_confidence,
            gap_threshold_seconds=gap_threshold_seconds,
            min_segment_size=min_segment_size,
            penalty_multiplier=penalty_multiplier,
            config=config
        )
    
    def get_signal_name(self) -> str:
        return "google_calendar_events"
    
    def get_source_name(self) -> str:
        return "google"
    
    def extract_signal_values(self, signals: List[Dict[str, Any]]) -> List[float]:
        """Extract event density values from signals."""
        return [float(signal['signal_value']) for signal in signals]
    
    def get_cost_function(self) -> str:
        """Use L1 norm for categorical event data."""
        return "l1"
    
    def compute_confidence(self, segment_data: np.ndarray) -> float:
        """
        Compute confidence based on event pattern consistency.
        
        Args:
            segment_data: Array of event density values
            
        Returns:
            Confidence score between 0 and 1
        """
        if len(segment_data) < 2:
            return 0.5
        
        # Higher confidence for consistent patterns
        std_dev = np.std(segment_data)
        mean_val = np.mean(segment_data)
        
        if mean_val == 0:
            return 0.5
        
        # Coefficient of variation (lower is more consistent)
        cv = std_dev / mean_val
        
        # Convert to confidence (inverse relationship)
        confidence = max(0.0, min(1.0, 1.0 - (cv / 2.0)))
        
        return confidence