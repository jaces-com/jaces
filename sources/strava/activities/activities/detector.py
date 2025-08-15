"""Strava Activities transition detector."""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from sources.base.interfaces.detector import TransitionDetector
from sources.base.generated_models.signals import Signals


class StravaActivitiesTransitionDetector(TransitionDetector):
    """Detect transitions in Strava activities data."""
    
    def __init__(self, min_gap_seconds: int = 900, confidence_threshold: float = 0.9):
        """
        Initialize the detector.
        
        Args:
            min_gap_seconds: Minimum gap between activities to consider them separate
            confidence_threshold: Confidence threshold for transitions
        """
        super().__init__()
        self.min_gap_seconds = min_gap_seconds
        self.confidence_threshold = confidence_threshold
    
    def detect_transitions(self, signals: List[Signals]) -> List[Dict[str, Any]]:
        """
        Detect transitions in activity data.
        
        Activities are discrete events, so each activity represents a transition.
        We group activities that occur close together (e.g., multi-sport events).
        
        Args:
            signals: List of activity signals
            
        Returns:
            List of transition dictionaries
        """
        if not signals:
            return []
        
        # Sort signals by timestamp
        sorted_signals = sorted(signals, key=lambda s: s.timestamp)
        
        transitions = []
        current_group = []
        
        for i, signal in enumerate(sorted_signals):
            if not current_group:
                # Start a new group
                current_group.append(signal)
            else:
                # Check if this activity is close enough to the previous one
                last_signal = current_group[-1]
                time_diff = (signal.timestamp - last_signal.timestamp).total_seconds()
                
                # Also check if the previous activity ended
                last_duration = last_signal.metadata.get("elapsed_time_seconds", 0) if last_signal.metadata else 0
                time_since_last_ended = time_diff - last_duration
                
                if time_since_last_ended <= self.min_gap_seconds:
                    # Add to current group (multi-sport or back-to-back activities)
                    current_group.append(signal)
                else:
                    # Process current group and start a new one
                    transition = self._create_transition_from_group(current_group)
                    if transition:
                        transitions.append(transition)
                    current_group = [signal]
        
        # Process the last group
        if current_group:
            transition = self._create_transition_from_group(current_group)
            if transition:
                transitions.append(transition)
        
        return transitions
    
    def _create_transition_from_group(self, signals: List[Signals]) -> Optional[Dict[str, Any]]:
        """
        Create a transition from a group of related activities.
        
        Args:
            signals: Group of activity signals
            
        Returns:
            Transition dictionary or None
        """
        if not signals:
            return None
        
        # Get start and end times
        start_time = signals[0].timestamp
        last_signal = signals[-1]
        last_duration = last_signal.metadata.get("elapsed_time_seconds", 0) if last_signal.metadata else 0
        end_time = last_signal.timestamp + timedelta(seconds=last_duration)
        
        # Aggregate metrics
        total_distance = 0
        total_elevation_gain = 0
        total_moving_time = 0
        total_elapsed_time = 0
        total_calories = 0
        activity_types = []
        activity_names = []
        
        # Heart rate data
        heart_rates = []
        max_heart_rate = 0
        
        # Power data
        power_values = []
        max_power = 0
        
        for signal in signals:
            metadata = signal.metadata or {}
            
            # Distance
            total_distance += metadata.get("distance_meters", 0)
            
            # Elevation
            total_elevation_gain += metadata.get("elevation_gain_meters", 0)
            
            # Time
            total_moving_time += metadata.get("moving_time_seconds", 0)
            total_elapsed_time += metadata.get("elapsed_time_seconds", 0)
            
            # Calories (if available)
            if metadata.get("kilojoules"):
                # Convert kilojoules to calories (approximate)
                total_calories += metadata["kilojoules"] * 0.239
            
            # Activity type and name
            activity_type = metadata.get("activity_type", "Unknown")
            if activity_type not in activity_types:
                activity_types.append(activity_type)
            
            activity_name = metadata.get("name", "")
            if activity_name:
                activity_names.append(activity_name)
            
            # Heart rate
            if metadata.get("average_heartrate"):
                heart_rates.append(metadata["average_heartrate"])
            if metadata.get("max_heartrate"):
                max_heart_rate = max(max_heart_rate, metadata["max_heartrate"])
            
            # Power
            if metadata.get("average_watts"):
                power_values.append(metadata["average_watts"])
            if metadata.get("max_watts"):
                max_power = max(max_power, metadata["max_watts"])
        
        # Calculate averages
        avg_heart_rate = np.mean(heart_rates) if heart_rates else None
        avg_power = np.mean(power_values) if power_values else None
        
        # Determine transition type
        if len(signals) > 1:
            transition_type = "multi_activity"
            description = f"Multi-sport: {', '.join(activity_types)}"
        else:
            transition_type = "single_activity"
            description = activity_types[0] if activity_types else "Activity"
        
        # Build transition metadata
        metadata = {
            "activity_count": len(signals),
            "activity_types": activity_types,
            "activity_names": activity_names,
            "total_distance_meters": total_distance,
            "total_distance_km": round(total_distance / 1000, 2),
            "total_elevation_gain_meters": total_elevation_gain,
            "total_moving_time_seconds": total_moving_time,
            "total_elapsed_time_seconds": total_elapsed_time,
            "duration_formatted": self._format_duration(total_elapsed_time)
        }
        
        if total_calories > 0:
            metadata["estimated_calories"] = round(total_calories)
        
        if avg_heart_rate:
            metadata["average_heart_rate"] = round(avg_heart_rate)
        if max_heart_rate > 0:
            metadata["max_heart_rate"] = max_heart_rate
        
        if avg_power:
            metadata["average_power_watts"] = round(avg_power)
        if max_power > 0:
            metadata["max_power_watts"] = max_power
        
        # Calculate average pace if applicable
        if total_distance > 0 and total_moving_time > 0:
            pace_per_km = total_moving_time / (total_distance / 1000)
            metadata["average_pace_min_per_km"] = f"{int(pace_per_km // 60)}:{int(pace_per_km % 60):02d}"
            
            speed_mps = total_distance / total_moving_time
            metadata["average_speed_kph"] = round(speed_mps * 3.6, 2)
        
        return {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "transition_type": transition_type,
            "description": description,
            "confidence": self.confidence_threshold,
            "metadata": metadata,
            "signal_ids": [s.id for s in signals]
        }
    
    def _format_duration(self, seconds: int) -> str:
        """
        Format duration in seconds to human-readable string.
        
        Args:
            seconds: Duration in seconds
            
        Returns:
            Formatted duration string
        """
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"
    
    def calculate_confidence(self, signals: List[Signals]) -> float:
        """
        Calculate confidence score for detected transitions.
        
        Args:
            signals: List of signals in the transition
            
        Returns:
            Confidence score between 0 and 1
        """
        if not signals:
            return 0.0
        
        # For activities, confidence is based on data completeness
        confidence_factors = []
        
        for signal in signals:
            metadata = signal.metadata or {}
            
            # Check for key data points
            has_distance = metadata.get("distance_meters", 0) > 0
            has_time = metadata.get("moving_time_seconds", 0) > 0
            has_type = metadata.get("activity_type") is not None
            has_name = metadata.get("name") is not None
            has_heart_rate = metadata.get("average_heartrate") is not None
            has_power = metadata.get("average_watts") is not None
            has_streams = metadata.get("has_streams", False)
            
            # Calculate completeness score
            completeness = sum([
                has_distance * 0.2,
                has_time * 0.2,
                has_type * 0.2,
                has_name * 0.1,
                has_heart_rate * 0.1,
                has_power * 0.1,
                has_streams * 0.1
            ])
            
            confidence_factors.append(completeness)
        
        return min(np.mean(confidence_factors) if confidence_factors else 0.0, 1.0)