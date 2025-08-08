"""Altitude transition detector using PELT algorithm."""

from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from sources.base.transitions.pelt import BasePELTTransitionDetector, Transition


class AltitudeTransitionDetector(BasePELTTransitionDetector):
    """
    PELT-based altitude transition detector.
    
    Detects statistically significant changes in altitude using
    the PELT (Pruned Exact Linear Time) algorithm. Returns computational
    metrics without semantic interpretation.
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
        Initialize altitude transition detector.
        
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
        return "apple_ios_altitude"
    
    def get_source_name(self) -> str:
        return "ios"
    
    def extract_signal_values(self, signals: List[Dict[str, Any]]) -> List[float]:
        """Extract altitude values from signals."""
        return [float(signal['signal_value']) for signal in signals]
    
    def get_cost_function(self) -> str:
        """Use L2 (variance) cost for altitude - good for continuous data."""
        return "l2"
    
    def create_collection_transition(
        self,
        timestamp: datetime,
        is_start: bool,
        period_signals: List[Dict[str, Any]],
        period_index: int,
        total_periods: int
    ) -> Optional[Transition]:
        """Add altitude info to collection transitions."""
        transition = super().create_collection_transition(
            timestamp, is_start, period_signals, period_index, total_periods
        )
        
        if transition and period_signals:
            # Add altitude to metadata
            if is_start:
                altitude = float(period_signals[0]['signal_value'])
            else:
                altitude = float(period_signals[-1]['signal_value'])
            
            transition.metadata['altitude'] = round(altitude, 1)
        
        return transition