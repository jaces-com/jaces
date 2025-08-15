"""Strava Activities stream processor."""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from uuid import uuid4

from sources.base.processing.normalization import StreamProcessor as BaseStreamProcessor
from sources.base.generated_models.signals import Signals


class StreamProcessor(BaseStreamProcessor):
    """Process Strava activities into normalized signals."""
    
    def __init__(self):
        super().__init__(
            source_name="strava",
            stream_type="activities"
        )
    
    def normalize_data(self, raw_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Normalize Strava activity data into signal format.
        
        Args:
            raw_data: Raw activity data from Strava API
            
        Returns:
            List of normalized signal dictionaries
        """
        normalized = []
        
        # Skip if this is athlete stats metadata
        if raw_data.get("_sync_metadata", {}).get("type") == "athlete_stats":
            return []
        
        # Extract activity fields
        activity_id = raw_data.get("id")
        if not activity_id:
            return []
        
        # Parse activity start time
        start_date_str = raw_data.get("start_date") or raw_data.get("start_date_local")
        if not start_date_str:
            return []
        
        try:
            # Strava returns ISO format timestamps
            timestamp = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
        except:
            return []
        
        # Extract key metrics
        activity_type = raw_data.get("type", "Unknown")
        name = raw_data.get("name", "Untitled Activity")
        distance = raw_data.get("distance", 0)  # meters
        moving_time = raw_data.get("moving_time", 0)  # seconds
        elapsed_time = raw_data.get("elapsed_time", 0)  # seconds
        total_elevation_gain = raw_data.get("total_elevation_gain", 0)  # meters
        
        # Performance metrics
        average_speed = raw_data.get("average_speed", 0)  # m/s
        max_speed = raw_data.get("max_speed", 0)  # m/s
        average_heartrate = raw_data.get("average_heartrate")
        max_heartrate = raw_data.get("max_heartrate")
        average_cadence = raw_data.get("average_cadence")
        average_watts = raw_data.get("average_watts")
        max_watts = raw_data.get("max_watts")
        kilojoules = raw_data.get("kilojoules")
        
        # Achievement counts
        achievement_count = raw_data.get("achievement_count", 0)
        pr_count = raw_data.get("pr_count", 0)
        
        # Build metadata
        metadata = {
            "activity_id": activity_id,
            "activity_type": activity_type,
            "name": name,
            "distance_meters": distance,
            "distance_km": round(distance / 1000, 2) if distance else 0,
            "distance_miles": round(distance / 1609.34, 2) if distance else 0,
            "moving_time_seconds": moving_time,
            "elapsed_time_seconds": elapsed_time,
            "elevation_gain_meters": total_elevation_gain,
            "average_speed_mps": average_speed,
            "average_speed_kph": round(average_speed * 3.6, 2) if average_speed else 0,
            "average_speed_mph": round(average_speed * 2.237, 2) if average_speed else 0,
            "max_speed_mps": max_speed,
            "achievement_count": achievement_count,
            "pr_count": pr_count,
            "sport_type": raw_data.get("sport_type"),
            "workout_type": raw_data.get("workout_type"),
            "gear_id": raw_data.get("gear_id"),
            "is_manual": raw_data.get("manual", False),
            "is_private": raw_data.get("private", False),
            "is_commute": raw_data.get("commute", False),
            "is_trainer": raw_data.get("trainer", False),
            "device_name": raw_data.get("device_name"),
            "has_kudos": raw_data.get("has_kudosed", False),
            "kudos_count": raw_data.get("kudos_count", 0),
            "comment_count": raw_data.get("comment_count", 0),
            "athlete_count": raw_data.get("athlete_count", 1),
            "photo_count": raw_data.get("photo_count", 0),
            "suffer_score": raw_data.get("suffer_score")
        }
        
        # Add heart rate data if available
        if average_heartrate:
            metadata["average_heartrate"] = average_heartrate
        if max_heartrate:
            metadata["max_heartrate"] = max_heartrate
        
        # Add cadence data if available
        if average_cadence:
            metadata["average_cadence"] = average_cadence
        
        # Add power data if available
        if average_watts:
            metadata["average_watts"] = average_watts
        if max_watts:
            metadata["max_watts"] = max_watts
        if kilojoules:
            metadata["kilojoules"] = kilojoules
        
        # Add location data if available
        if raw_data.get("start_latlng"):
            metadata["start_lat"] = raw_data["start_latlng"][0]
            metadata["start_lng"] = raw_data["start_latlng"][1]
        if raw_data.get("end_latlng"):
            metadata["end_lat"] = raw_data["end_latlng"][0]
            metadata["end_lng"] = raw_data["end_latlng"][1]
        
        # Add weather data if available
        if raw_data.get("average_temp"):
            metadata["average_temp_celsius"] = raw_data["average_temp"]
        
        # Add segment efforts count
        if raw_data.get("segment_efforts"):
            metadata["segment_efforts_count"] = len(raw_data["segment_efforts"])
        
        # Add lap count
        laps = raw_data.get("laps", [])
        if laps:
            metadata["lap_count"] = len(laps)
        
        # Check if activity has streams (detailed time series data)
        has_streams = bool(raw_data.get("streams"))
        metadata["has_streams"] = has_streams
        
        # Calculate performance metrics
        if moving_time > 0:
            if distance > 0:
                # Pace in seconds per km
                pace_per_km = moving_time / (distance / 1000)
                metadata["pace_seconds_per_km"] = round(pace_per_km, 0)
                metadata["pace_min_per_km"] = f"{int(pace_per_km // 60)}:{int(pace_per_km % 60):02d}"
                
                # Pace in seconds per mile
                pace_per_mile = moving_time / (distance / 1609.34)
                metadata["pace_seconds_per_mile"] = round(pace_per_mile, 0)
                metadata["pace_min_per_mile"] = f"{int(pace_per_mile // 60)}:{int(pace_per_mile % 60):02d}"
        
        # Determine primary value based on activity type
        if activity_type in ["Run", "Walk", "Hike"]:
            value = distance / 1000  # km
            metadata["value_unit"] = "km"
        elif activity_type in ["Ride", "VirtualRide"]:
            value = distance / 1000  # km
            metadata["value_unit"] = "km"
        elif activity_type in ["Swim"]:
            value = distance  # meters
            metadata["value_unit"] = "meters"
        elif activity_type in ["Workout", "WeightTraining", "Yoga"]:
            value = moving_time / 60  # minutes
            metadata["value_unit"] = "minutes"
        else:
            value = moving_time / 60  # default to minutes
            metadata["value_unit"] = "minutes"
        
        # Create the normalized signal
        signal = {
            "id": str(uuid4()),
            "signal_type": "strava_activities",
            "source": "strava",
            "stream": "activities",
            "timestamp": timestamp.isoformat(),
            "value": round(value, 2),
            "metadata": metadata,
            "raw_data": raw_data  # Store complete raw data for future reference
        }
        
        normalized.append(signal)
        
        return normalized
    
    def deduplicate(self, signals: List[Signals]) -> List[Signals]:
        """
        Deduplicate signals based on activity ID.
        
        Args:
            signals: List of signal records
            
        Returns:
            Deduplicated list of signals
        """
        seen_activities = {}
        deduplicated = []
        
        for signal in signals:
            activity_id = signal.metadata.get("activity_id") if signal.metadata else None
            if not activity_id:
                # Keep signals without activity IDs
                deduplicated.append(signal)
                continue
            
            if activity_id not in seen_activities:
                seen_activities[activity_id] = signal
                deduplicated.append(signal)
            else:
                # Keep the most recent version (by sync time)
                existing = seen_activities[activity_id]
                if signal.created_at > existing.created_at:
                    # Remove old, add new
                    deduplicated.remove(existing)
                    deduplicated.append(signal)
                    seen_activities[activity_id] = signal
        
        return deduplicated