"""
Ambient signal boundary detection

Handles continuous streams of data like:
- GPS location
- Heart rate
- Audio environment classification
"""
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from uuid import UUID
import logging
import numpy as np

from sqlalchemy.orm import Session
from sqlalchemy import and_

from sources.base.generated_models.signals import Signals

logger = logging.getLogger(__name__)


class AmbientBoundaryDetector:
    """
    Detects boundaries from ambient signals using statistical change detection
    """
    
    def __init__(self, db_session: Session):
        self.db = db_session
        
    def detect(
        self, 
        user_id: UUID, 
        start_time: datetime, 
        end_time: datetime
    ) -> List[Dict[str, Any]]:
        """
        Extract boundaries from ambient signals
        
        Args:
            user_id: User ID
            start_time: Start of time window
            end_time: End of time window
            
        Returns:
            List of boundary dicts with start, end, confidence
        """
        boundaries = []
        
        # Query ambient signals in time range
        signals = self.db.query(Signals).filter(
            and_(
                Signals.user_id == user_id,
                Signals.timestamp >= start_time,
                Signals.timestamp <= end_time
            )
        ).order_by(Signals.timestamp).all()
        
        logger.info(f"Processing {len(signals)} ambient signals")
        
        # Group signals by source for source-specific processing
        signals_by_source = {}
        for signal in signals:
            if signal.source_name not in signals_by_source:
                signals_by_source[signal.source_name] = []
            signals_by_source[signal.source_name].append(signal)
        
        # Process each source
        for source_name, source_signals in signals_by_source.items():
            if 'gps' in source_name.lower() or 'location' in source_name.lower():
                boundaries.extend(self._process_location_signals(source_signals))
            elif 'sound' in source_name.lower() or 'audio' in source_name.lower():
                boundaries.extend(self._process_audio_signals(source_signals))
            elif 'heart' in source_name.lower() or 'health' in source_name.lower():
                boundaries.extend(self._process_health_signals(source_signals))
            else:
                # Generic processing for other ambient sources
                boundaries.extend(self._process_generic_ambient(source_signals, source_name))
        
        return boundaries
    
    def _process_location_signals(self, signals: List[Signals]) -> List[Dict[str, Any]]:
        """
        Process GPS/location signals
        Detect boundaries when location changes significantly
        """
        boundaries = []
        
        if len(signals) < 2:
            return boundaries
        
        # Simple distance-based change detection
        current_location = None
        boundary_start = signals[0].timestamp
        
        for i, signal in enumerate(signals):
            if signal.latitude is None or signal.longitude is None:
                continue
                
            new_location = (signal.latitude, signal.longitude)
            
            if current_location is None:
                current_location = new_location
                continue
            
            # Calculate distance (simple euclidean for now, could use haversine)
            distance = self._calculate_distance(current_location, new_location)
            
            # If moved more than 100 meters, create a boundary
            if distance > 100:  # meters
                boundaries.append({
                    'start': boundary_start,
                    'end': signal.timestamp,
                    'confidence': 0.8,
                    'source': 'ambient_location',
                    'metadata': {
                        'distance_moved': distance,
                        'from_location': current_location,
                        'to_location': new_location
                    }
                })
                boundary_start = signal.timestamp
                current_location = new_location
        
        # Add final boundary if we have remaining data
        if len(signals) > 0 and boundary_start < signals[-1].timestamp:
            boundaries.append({
                'start': boundary_start,
                'end': signals[-1].timestamp,
                'confidence': 0.7,
                'source': 'ambient_location'
            })
        
        return boundaries
    
    def _process_audio_signals(self, signals: List[Signals]) -> List[Dict[str, Any]]:
        """
        Process audio environment classification signals
        Detect boundaries when audio environment changes
        """
        boundaries = []
        
        if len(signals) < 2:
            return boundaries
        
        # Group by classification
        current_classification = signals[0].classification
        boundary_start = signals[0].timestamp
        
        for signal in signals[1:]:
            if signal.classification != current_classification:
                # Environment changed
                boundaries.append({
                    'start': boundary_start,
                    'end': signal.timestamp,
                    'confidence': signal.confidence or 0.7,
                    'source': 'ambient_audio',
                    'metadata': {
                        'environment': current_classification
                    }
                })
                current_classification = signal.classification
                boundary_start = signal.timestamp
        
        # Add final boundary
        if len(signals) > 0:
            boundaries.append({
                'start': boundary_start,
                'end': signals[-1].timestamp,
                'confidence': signals[-1].confidence or 0.7,
                'source': 'ambient_audio',
                'metadata': {
                    'environment': current_classification
                }
            })
        
        return boundaries
    
    def _process_health_signals(self, signals: List[Signals]) -> List[Dict[str, Any]]:
        """
        Process health signals (heart rate, etc.)
        Detect boundaries based on activity level changes
        """
        boundaries = []
        
        if len(signals) < 5:  # Need enough data for statistics
            return boundaries
        
        # Simple threshold-based detection for heart rate
        # Could be enhanced with proper change-point detection
        window_size = 5
        
        for i in range(window_size, len(signals)):
            window = signals[i-window_size:i]
            
            # Calculate statistics for the window
            values = [s.value for s in window if s.value is not None]
            if len(values) < window_size // 2:
                continue
                
            mean_hr = np.mean(values)
            std_hr = np.std(values)
            
            # Check if current value is significantly different
            if signals[i].value is not None:
                z_score = abs(signals[i].value - mean_hr) / (std_hr + 1e-6)
                
                if z_score > 2:  # Significant change
                    boundaries.append({
                        'start': signals[i-1].timestamp,
                        'end': signals[i].timestamp,
                        'confidence': min(0.9, z_score / 3),  # Higher z-score = higher confidence
                        'source': 'ambient_health',
                        'metadata': {
                            'change_type': 'activity_level',
                            'from_hr': mean_hr,
                            'to_hr': signals[i].value
                        }
                    })
        
        return boundaries
    
    def _process_generic_ambient(self, signals: List[Signals], source_name: str) -> List[Dict[str, Any]]:
        """
        Generic processing for ambient signals using simple change detection
        """
        boundaries = []
        
        if len(signals) < 2:
            return boundaries
        
        # Simple gap-based detection
        max_gap_minutes = 15  # If no signal for 15 minutes, assume boundary
        
        for i in range(1, len(signals)):
            time_gap = (signals[i].timestamp - signals[i-1].timestamp).total_seconds() / 60
            
            if time_gap > max_gap_minutes:
                boundaries.append({
                    'start': signals[i-1].timestamp,
                    'end': signals[i].timestamp,
                    'confidence': 0.6,
                    'source': f'ambient_{source_name}',
                    'metadata': {
                        'gap_minutes': time_gap
                    }
                })
        
        return boundaries
    
    def _calculate_distance(self, loc1: tuple, loc2: tuple) -> float:
        """
        Calculate distance between two GPS coordinates in meters
        Simple euclidean approximation for small distances
        """
        # For more accuracy, use haversine formula
        lat_diff = loc2[0] - loc1[0]
        lon_diff = loc2[1] - loc1[1]
        
        # Rough approximation: 1 degree latitude = 111km
        # 1 degree longitude varies by latitude, using 111km * cos(latitude)
        lat_meters = lat_diff * 111000
        lon_meters = lon_diff * 111000 * np.cos(np.radians(loc1[0]))
        
        return np.sqrt(lat_meters**2 + lon_meters**2)