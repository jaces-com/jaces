"""Heart rate transition detector using PELT algorithm."""

from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from sources.base.transitions.pelt import BasePELTTransitionDetector, Transition


class HeartRateTransitionDetector(BasePELTTransitionDetector):
    """
    PELT-based heart rate transition detector.
    
    Detects significant changes in heart rate using changepoint detection.
    No semantic interpretation - purely computational detection of changes.
    
    Uses PELT to find optimal change points where heart rate behavior changes.
    """
    
    def __init__(
        self,
        min_confidence: float = 0.8,
        gap_threshold_seconds: int = 1800,  # 30 minutes
        min_segment_size: int = 5,
        penalty_multiplier: float = 1.0,
        config: Optional[Dict[str, Any]] = None  # Signal configuration
    ):
        """
        Initialize heart rate transition detector.
        
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
        return "apple_ios_heart_rate"
    
    def get_source_name(self) -> str:
        return "ios"
    
    def extract_signal_values(self, signals: List[Dict[str, Any]]) -> List[float]:
        """Extract heart rate values from signals."""
        return [float(signal['signal_value']) for signal in signals]
    
    def get_cost_function(self) -> str:
        """Use L2 norm for heart rate data."""
        return "l2"
    
    
