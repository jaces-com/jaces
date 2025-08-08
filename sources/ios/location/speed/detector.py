"""Speed transition detector using PELT algorithm."""

from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from sources.base.transitions.pelt import BasePELTTransitionDetector, Transition


class SpeedTransitionDetector(BasePELTTransitionDetector):
    """
    PELT-based speed transition detector.
    
    Detects statistically significant changes in movement speed using
    the PELT (Pruned Exact Linear Time) algorithm. Returns computational
    metrics without semantic interpretation.
    """
    
    def __init__(
        self,
        min_confidence: float = 0.8,
        gap_threshold_seconds: int = 900,  # 15 minutes
        min_segment_size: int = 5,
        penalty_multiplier: float = 1.2,  # Slightly higher to avoid over-segmentation
        config: Optional[Dict[str, Any]] = None  # Signal configuration
    ):
        """
        Initialize speed transition detector.
        
        Args:
            min_confidence: Minimum confidence threshold
            gap_threshold_seconds: Gap size to consider collection stopped
            min_segment_size: Minimum points per PELT segment
            penalty_multiplier: Adjust PELT sensitivity
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
        return "apple_ios_speed"
    
    def get_source_name(self) -> str:
        return "ios"
    
    def extract_signal_values(self, signals: List[Dict[str, Any]]) -> List[float]:
        """Extract speed values from signals."""
        return [float(signal['signal_value']) for signal in signals]
    
    def get_cost_function(self) -> str:
        """Use L1 (absolute deviation) for speed - robust to outliers."""
        return "l1"
    
    def create_collection_transition(
        self,
        timestamp: datetime,
        is_start: bool,
        period_signals: List[Dict[str, Any]],
        period_index: int,
        total_periods: int
    ) -> Optional[Transition]:
        """Add speed metrics to collection transitions."""
        transition = super().create_collection_transition(
            timestamp, is_start, period_signals, period_index, total_periods
        )
        
        if transition and period_signals:
            # Add speed metrics to metadata
            if is_start:
                speed = float(period_signals[0]['signal_value'])
            else:
                speed = float(period_signals[-1]['signal_value'])
            
            transition.metadata['speed_m_s'] = round(speed, 1)
            transition.metadata['speed_km_h'] = round(speed * 3.6, 1)
        
        return transition