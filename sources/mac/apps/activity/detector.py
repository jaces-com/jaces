"""Mac app activity transition detector using PELT algorithm."""

from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from sources.base.transitions.pelt import BasePELTTransitionDetector, Transition


class AppActivityTransitionDetector(BasePELTTransitionDetector):
    """
    PELT-based application activity transition detector.
    
    Detects significant changes in application usage patterns.
    Tracks transitions between different focus states and app categories.
    
    Uses PELT to find optimal change points where app usage behavior changes.
    """
    
    def __init__(
        self,
        min_confidence: float = 0.8,
        gap_threshold_seconds: int = 300,  # 5 minutes
        min_segment_size: int = 10,
        penalty_multiplier: float = 1.5,
        config: Optional[Dict[str, Any]] = None  # Signal configuration
    ):
        """
        Initialize app activity transition detector.
        
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
        
        # Load app categories from config if available
        self.app_categories = {}
        if config and 'app_categories' in config:
            self.app_categories = config['app_categories']
    
    def get_signal_name(self) -> str:
        return "mac_app_activity"
    
    def get_source_name(self) -> str:
        return "mac"
    
    def extract_signal_values(self, signals: List[Dict[str, Any]]) -> List[float]:
        """Extract app focus duration values from signals."""
        return [float(signal['signal_value']) for signal in signals]
    
    def get_cost_function(self) -> str:
        """Use L2 norm for continuous focus duration data."""
        return "l2"
    
    def compute_confidence(self, segment_data: np.ndarray) -> float:
        """
        Compute confidence based on app usage consistency.
        
        Args:
            segment_data: Array of app focus duration values
            
        Returns:
            Confidence score between 0 and 1
        """
        if len(segment_data) < 2:
            return 0.5
        
        # Calculate statistics
        mean_duration = np.mean(segment_data)
        std_duration = np.std(segment_data)
        
        # No activity = low confidence
        if mean_duration == 0:
            return 0.3
        
        # Coefficient of variation (lower is more consistent)
        cv = std_duration / mean_duration
        
        # Additional factor: sustained focus periods increase confidence
        sustained_focus = np.sum(segment_data > 30) / len(segment_data)  # % of time > 30 min
        
        # Combine factors
        consistency_score = max(0.0, min(1.0, 1.0 - (cv / 2.0)))
        focus_score = sustained_focus
        
        # Weighted average
        confidence = (consistency_score * 0.7 + focus_score * 0.3)
        
        return max(0.0, min(1.0, confidence))
    
    def categorize_activity(self, app_name: str) -> str:
        """
        Categorize an app into productivity categories.
        
        Args:
            app_name: Name of the application
            
        Returns:
            Category name or 'other'
        """
        for category, apps in self.app_categories.items():
            if app_name in apps:
                return category
        return 'other'