"""Base class for PELT-based transition detectors."""

from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from abc import abstractmethod
import numpy as np

try:
    import ruptures as rpt
except ImportError:
    raise ImportError("ruptures library required for PELT detection. Install with: pip install ruptures")

from sources.base.transitions.categorical import BaseCategoricalTransitionDetector, Transition


class BasePELTTransitionDetector(BaseCategoricalTransitionDetector):
    """
    Base class for transition detectors using PELT (Pruned Exact Linear Time) algorithm.
    
    This class handles:
    1. Collection period detection (managing gaps in data)
    2. PELT change point detection within each collection period
    3. Converting change points to meaningful state transitions
    
    Subclasses should override methods to customize:
    - Signal value extraction
    - Cost functions
    - State determination
    - Transition creation
    """
    
    def __init__(
        self,
        min_confidence: float = 0.8,
        gap_threshold_seconds: int = 900,  # 15 minutes default
        min_segment_size: int = 5,  # Minimum points per segment
        penalty_multiplier: float = 1.0,  # Adjust PELT sensitivity
        config: Optional[Dict[str, Any]] = None  # Signal configuration
    ):
        """
        Initialize PELT-based transition detector.
        
        Args:
            min_confidence: Minimum confidence threshold
            gap_threshold_seconds: Gap size to consider collection stopped
            min_segment_size: Minimum number of points in a segment
            penalty_multiplier: Multiply automatic penalty by this factor
            config: Optional signal configuration dict with computation parameters
        """
        super().__init__(min_confidence)
        
        # Use config values if provided, otherwise use defaults
        if config and 'computation' in config:
            comp = config['computation']
            self.gap_threshold_seconds = comp.get('gap_threshold_seconds', gap_threshold_seconds)
            self.min_segment_size = comp.get('min_segment_size', min_segment_size)
            self.penalty_multiplier = comp.get('penalty_multiplier', penalty_multiplier)
        else:
            self.gap_threshold_seconds = gap_threshold_seconds
            self.min_segment_size = min_segment_size
            self.penalty_multiplier = penalty_multiplier
    
    def detect_transitions(
        self,
        signals: List[Dict[str, Any]],
        start_time: datetime,
        end_time: datetime
    ) -> List[Transition]:
        """
        Detect transitions using collection periods + PELT within each period.
        """
        if not signals:
            return []
        
        transitions = []
        
        # Layer 1: Detect collection periods (handles gaps)
        collection_periods = self.detect_collection_periods(
            signals, 
            self.gap_threshold_seconds
        )
        
        # Process each collection period
        for i, (period_start, period_end, period_signals) in enumerate(collection_periods):
            # Add collection started transition
            collection_start_transition = self.create_collection_transition(
                timestamp=period_start,
                is_start=True,
                period_signals=period_signals,
                period_index=i,
                total_periods=len(collection_periods)
            )
            if collection_start_transition:
                transitions.append(collection_start_transition)
            
            # Layer 2: Run PELT within this collection period
            if len(period_signals) >= self.min_segment_size * 2:
                pelt_transitions = self._run_pelt_detection(period_signals)
                transitions.extend(pelt_transitions)
            
            # Add collection stopped transition
            should_add_stop = (
                i < len(collection_periods) - 1 or 
                (end_time - period_end).total_seconds() > self.gap_threshold_seconds
            )
            
            if should_add_stop:
                collection_stop_transition = self.create_collection_transition(
                    timestamp=period_end,
                    is_start=False,
                    period_signals=period_signals,
                    period_index=i,
                    total_periods=len(collection_periods)
                )
                if collection_stop_transition:
                    transitions.append(collection_stop_transition)
        
        # Merge transitions that are too close together
        transitions = self.merge_close_transitions(transitions)
        
        return self.validate_transitions(transitions, start_time, end_time)
    
    def _run_pelt_detection(
        self, 
        signals: List[Dict[str, Any]]
    ) -> List[Transition]:
        """
        Run PELT algorithm on a collection period's signals.
        """
        # Extract signal values
        values = self.extract_signal_values(signals)
        if len(values) < self.min_segment_size * 2:
            return []
        
        # Convert to numpy array for ruptures
        signal_array = np.array(values)
        
        # Get cost function and penalty
        cost_function = self.get_cost_function()
        penalty_value = self.get_penalty_value(signal_array)
        
        # Create and fit PELT model
        model = rpt.Pelt(model=cost_function, min_size=self.min_segment_size)
        model.fit(signal_array)
        
        # Find change points
        try:
            change_points = model.predict(pen=penalty_value)
        except Exception as e:
            # If PELT fails, return empty list
            print(f"PELT detection failed: {e}")
            return []
        
        # Convert change points to transitions
        transitions = self._convert_changepoints_to_transitions(
            signals, values, change_points
        )
        
        return transitions
    
    def _convert_changepoints_to_transitions(
        self,
        signals: List[Dict[str, Any]],
        values: List[float],
        change_points: List[int]
    ) -> List[Transition]:
        """
        Convert PELT change points to transitions.
        """
        transitions = []
        
        # Change points include the end of data, so we ignore the last one
        if not change_points or change_points[-1] == len(values):
            change_points = change_points[:-1]
        
        if not change_points:
            return []
        
        # Add 0 to beginning for first segment
        segment_boundaries = [0] + change_points + [len(values)]
        
        # Process each changepoint
        for i in range(1, len(segment_boundaries) - 1):
            # Get before and after segments
            before_start = segment_boundaries[i-1]
            before_end = segment_boundaries[i]
            after_start = segment_boundaries[i]
            after_end = segment_boundaries[i+1]
            
            before_values = values[before_start:before_end]
            after_values = values[after_start:after_end]
            
            # Calculate statistics
            before_mean = float(np.mean(before_values)) if before_values else None
            before_std = float(np.std(before_values)) if before_values else None
            after_mean = float(np.mean(after_values)) if after_values else None
            after_std = float(np.std(after_values)) if after_values else None
            
            # Calculate change characteristics
            if before_mean is not None and after_mean is not None:
                change_magnitude = abs(after_mean - before_mean)
                change_direction = 'increase' if after_mean > before_mean else 'decrease'
            else:
                change_magnitude = None
                change_direction = None
            
            # Calculate confidence based on segment stability
            confidence = self._calculate_changepoint_confidence(
                before_values, after_values, signals[after_start]['timestamp']
            )
            
            # Create transition
            transition = Transition(
                transition_time=signals[after_start]['timestamp'],
                transition_type='changepoint',
                change_magnitude=change_magnitude,
                change_direction=change_direction,
                before_mean=before_mean,
                before_std=before_std,
                after_mean=after_mean,
                after_std=after_std,
                confidence=confidence,
                detection_method='pelt_changepoint',
                metadata={
                    'before_segment_size': len(before_values),
                    'after_segment_size': len(after_values),
                    'changepoint_index': i
                }
            )
            
            transitions.append(transition)
        
        return transitions
    
    # Abstract methods that subclasses must implement
    
    @abstractmethod
    def extract_signal_values(self, signals: List[Dict[str, Any]]) -> List[float]:
        """
        Extract numerical values from signals for PELT analysis.
        
        Args:
            signals: List of signal dictionaries
            
        Returns:
            List of float values
        """
        pass
    
    @abstractmethod
    def get_cost_function(self) -> str:
        """
        Get the cost function to use for PELT.
        
        Options:
            - "l1": Absolute deviation
            - "l2": Squared deviation (variance)
            - "rbf": Radial basis function
            - "normal": Gaussian likelihood
            
        Returns:
            Cost function name
        """
        pass
    
    
    # Optional methods that subclasses can override
    
    def get_penalty_value(self, signal_array: np.ndarray) -> float:
        """
        Calculate penalty value for PELT.
        
        Default uses BIC (Bayesian Information Criterion).
        Subclasses can override for custom penalty.
        
        Args:
            signal_array: Numpy array of signal values
            
        Returns:
            Penalty value
        """
        n = len(signal_array)
        # BIC penalty
        penalty = np.log(n) * self.penalty_multiplier
        return penalty
    
    def create_collection_transition(
        self,
        timestamp: datetime,
        is_start: bool,
        period_signals: List[Dict[str, Any]],
        period_index: int,
        total_periods: int
    ) -> Optional[Transition]:
        """
        Create a collection start/stop transition.
        
        Subclasses can override to customize or suppress these transitions.
        
        Args:
            timestamp: When collection started/stopped
            is_start: True if collection started, False if stopped
            period_signals: All signals in this collection period
            period_index: Index of this period (0-based)
            total_periods: Total number of periods in the time range
            
        Returns:
            Transition object or None to skip
        """
        # For data gaps, we only create transitions when data stops (not when it starts)
        if is_start:
            return None
            
        return Transition(
            transition_time=timestamp,
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
                "period_duration_minutes": (
                    period_signals[-1]['timestamp'] - period_signals[0]['timestamp']
                ).total_seconds() / 60,
                "signal_count": len(period_signals),
                "period_index": period_index
            }
        )
    
    def _calculate_changepoint_confidence(
        self,
        before_values: List[float],
        after_values: List[float],
        transition_time: datetime
    ) -> float:
        """
        Calculate confidence for a changepoint based on segment characteristics.
        
        Args:
            before_values: Values before the changepoint
            after_values: Values after the changepoint
            transition_time: When the transition occurred
            
        Returns:
            Confidence score between 0 and 1
        """
        if not before_values or not after_values:
            return 0.5
        
        # Calculate coefficient of variation for each segment
        before_mean = np.mean(before_values)
        after_mean = np.mean(after_values)
        
        before_cv = np.std(before_values) / before_mean if before_mean != 0 else 1.0
        after_cv = np.std(after_values) / after_mean if after_mean != 0 else 1.0
        
        # Lower CV means more stable segment, higher confidence
        avg_cv = (before_cv + after_cv) / 2
        
        if avg_cv < 0.1:
            stability_score = 0.95
        elif avg_cv < 0.2:
            stability_score = 0.85
        elif avg_cv < 0.3:
            stability_score = 0.75
        else:
            stability_score = 0.65
        
        # Adjust based on segment sizes
        min_segment_size = min(len(before_values), len(after_values))
        if min_segment_size < 10:
            size_penalty = 0.1
        elif min_segment_size < 20:
            size_penalty = 0.05
        else:
            size_penalty = 0.0
        
        confidence = stability_score - size_penalty
        return max(self.min_confidence, min(1.0, confidence))
    
    
    def merge_close_transitions(self, transitions: List[Transition]) -> List[Transition]:
        """
        Merge transitions that are too close together based on signal configuration.
        
        This helps reduce micro-transitions that don't represent meaningful activity changes.
        """
        if len(transitions) <= 1:
            return transitions
        
        # Get min_transition_gap from signal config (will be set by subclasses)
        min_gap_seconds = getattr(self, 'min_transition_gap', 300)  # Default 5 minutes
        
        # Sort transitions by time
        sorted_transitions = sorted(transitions, key=lambda t: t.transition_time)
        
        merged = []
        current_group = [sorted_transitions[0]]
        
        for i in range(1, len(sorted_transitions)):
            transition = sorted_transitions[i]
            last_in_group = current_group[-1]
            
            # Check time gap from last transition in current group
            gap_seconds = (transition.transition_time - last_in_group.transition_time).total_seconds()
            
            if gap_seconds < min_gap_seconds:
                # Too close, add to current group
                current_group.append(transition)
            else:
                # Far enough, finalize current group and start new one
                merged_transition = self._merge_transition_group(current_group)
                if merged_transition:
                    merged.append(merged_transition)
                current_group = [transition]
        
        # Don't forget the last group
        if current_group:
            merged_transition = self._merge_transition_group(current_group)
            if merged_transition:
                merged.append(merged_transition)
        
        return merged
    
    def _merge_transition_group(self, group: List[Transition]) -> Optional[Transition]:
        """
        Merge a group of close transitions into a single transition.
        
        Takes the highest confidence transition as the representative.
        """
        if not group:
            return None
        
        if len(group) == 1:
            return group[0]
        
        # Use the transition with highest confidence as representative
        representative = max(group, key=lambda t: t.confidence)
        
        # Update metadata to indicate merging
        representative.metadata = representative.metadata or {}
        representative.metadata['merged_count'] = len(group)
        representative.metadata['merged_transitions'] = [
            {
                'time': t.transition_time.isoformat(),
                'type': t.transition_type,
                'magnitude': t.change_magnitude,
                'direction': t.change_direction,
                'confidence': t.confidence
            } for t in group
        ]
        
        # Boost confidence slightly since multiple transitions agreed
        representative.confidence = min(1.0, representative.confidence * 1.1)
        
        return representative