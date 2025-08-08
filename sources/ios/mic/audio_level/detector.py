"""Audio level transition detector using PELT algorithm."""

from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from sources.base.transitions.pelt import BasePELTTransitionDetector, Transition


class AudioLevelTransitionDetector(BasePELTTransitionDetector):
    """
    PELT-based audio level transition detector.
    
    Detects statistically significant changes in ambient audio levels using
    the PELT (Pruned Exact Linear Time) algorithm. Returns computational
    metrics without semantic interpretation.
    """
    
    def __init__(
        self,
        min_confidence: float = 0.85,
        gap_threshold_seconds: int = 600,  # 10 minutes
        min_segment_size: int = 3,  # Minimum 3 chunks (1.5 minutes)
        penalty_multiplier: float = 1.5,  # Slightly higher to avoid too many transitions
        config: Optional[Dict[str, Any]] = None  # Signal configuration
    ):
        """
        Initialize audio level transition detector.
        
        Args:
            min_confidence: Minimum confidence threshold
            gap_threshold_seconds: Gap size to consider audio collection stopped
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
        return "apple_ios_audio_level"
    
    def get_source_name(self) -> str:
        return "ios"
    
    def extract_signal_values(self, signals: List[Dict[str, Any]]) -> List[float]:
        """Extract audio level values from signals."""
        return [float(signal['signal_value']) for signal in signals]
    
    def get_cost_function(self) -> str:
        """Use L2 (variance) cost for audio level data."""
        return "l2"