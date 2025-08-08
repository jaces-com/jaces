"""Coordinates transition detector using PELT algorithm."""

from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import math

from sources.base.transitions.pelt import BasePELTTransitionDetector, Transition


class CoordinatesTransitionDetector(BasePELTTransitionDetector):
    """
    PELT-based coordinates transition detector.
    
    Detects statistically significant changes in geographic location using
    the PELT (Pruned Exact Linear Time) algorithm. Returns computational
    metrics without semantic interpretation.
    """
    
    def __init__(
        self,
        min_confidence: float = 0.8,
        gap_threshold_seconds: int = 900,  # 15 minutes
        min_segment_size: int = 5,
        penalty_multiplier: float = 1.5,  # Higher to avoid over-segmentation
        config: Optional[Dict[str, Any]] = None  # Signal configuration
    ):
        """
        Initialize coordinates transition detector.
        
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
        return "apple_ios_coordinates"
    
    def get_source_name(self) -> str:
        return "ios"
    
    def extract_signal_values(self, signals: List[Dict[str, Any]]) -> List[float]:
        """
        Extract values for PELT analysis.
        
        For coordinates, we use cumulative distance traveled from start.
        This creates a monotonically increasing signal that PELT can segment.
        """
        if not signals:
            return []
        
        # Get starting coordinates
        first_coords = self._extract_coordinates(signals[0])
        if not first_coords:
            return []
        
        # Calculate cumulative distance from start
        distances = [0.0]  # Start at 0
        prev_coords = first_coords
        
        for signal in signals[1:]:
            coords = self._extract_coordinates(signal)
            if coords:
                # Add distance from previous point
                dist = self._calculate_distance(
                    prev_coords[0], prev_coords[1],
                    coords[0], coords[1]
                )
                distances.append(distances[-1] + dist)
                prev_coords = coords
            else:
                # If extraction fails, repeat last distance
                distances.append(distances[-1])
        
        return distances
    
    def get_cost_function(self) -> str:
        """Use L2 (variance) for distance data."""
        return "l2"
    
    def create_collection_transition(
        self,
        timestamp: datetime,
        is_start: bool,
        period_signals: List[Dict[str, Any]],
        period_index: int,
        total_periods: int
    ) -> Optional[Transition]:
        """Add location info to collection transitions."""
        transition = super().create_collection_transition(
            timestamp, is_start, period_signals, period_index, total_periods
        )
        
        if transition and period_signals:
            # Add location to metadata
            if is_start:
                coords = self._extract_coordinates(period_signals[0])
            else:
                coords = self._extract_coordinates(period_signals[-1])
            
            if coords:
                transition.metadata['location'] = {
                    'lat': round(coords[0], 6),
                    'lng': round(coords[1], 6)
                }
        
        return transition
    
    
    def _get_segment_center(
        self, 
        signals: List[Dict[str, Any]]
    ) -> Optional[Tuple[float, float]]:
        """Calculate the geographic center of a segment."""
        coords_list = []
        for signal in signals:
            coords = self._extract_coordinates(signal)
            if coords:
                coords_list.append(coords)
        
        if not coords_list:
            return None
        
        # Calculate centroid
        center_lat = float(np.mean([c[0] for c in coords_list]))
        center_lng = float(np.mean([c[1] for c in coords_list]))
        
        return (center_lat, center_lng)
    
    def _extract_coordinates(self, signal: Dict[str, Any]) -> Optional[Tuple[float, float]]:
        """Extract latitude and longitude from signal data."""
        # Try to get from coordinates field
        coords = signal.get('coordinates')
        if coords and isinstance(coords, dict):
            lat = coords.get('lat')
            lng = coords.get('lng') or coords.get('lon')
            if lat is not None and lng is not None:
                return (lat, lng)
        
        # Try parsing from signal_value
        try:
            value = signal.get('signal_value', '')
            if ',' in value:
                lat_str, lon_str = value.split(',', 1)
                return (float(lat_str.strip()), float(lon_str.strip()))
        except:
            pass
            
        return None
    
    def _calculate_distance(
        self,
        lat1: float,
        lng1: float,
        lat2: float,
        lng2: float
    ) -> float:
        """
        Calculate distance between two coordinates using Haversine formula.
        
        Returns:
            Distance in meters
        """
        R = 6371000  # Earth's radius in meters
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lng = math.radians(lng2 - lng1)
        
        a = (math.sin(delta_lat / 2) ** 2 +
             math.cos(lat1_rad) * math.cos(lat2_rad) *
             math.sin(delta_lng / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c
    
