"""Data normalization utilities for stream processing."""

from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timezone
import json
import hashlib


class DataNormalizer:
    """Normalizes data from various sources into consistent formats."""
    
    @staticmethod
    def normalize_timestamp(
        timestamp: Union[str, int, float, datetime]
    ) -> datetime:
        """
        Normalize various timestamp formats to datetime.
        
        Args:
            timestamp: Timestamp in various formats
            
        Returns:
            Normalized datetime object with timezone
        """
        if isinstance(timestamp, datetime):
            # Ensure timezone awareness
            if timestamp.tzinfo is None:
                return timestamp.replace(tzinfo=timezone.utc)
            return timestamp
        
        if isinstance(timestamp, (int, float)):
            # Unix timestamp
            if timestamp > 10**10:  # Milliseconds
                timestamp = timestamp / 1000
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        
        if isinstance(timestamp, str):
            # ISO format
            if 'T' in timestamp:
                if timestamp.endswith('Z'):
                    timestamp = timestamp[:-1] + '+00:00'
                return datetime.fromisoformat(timestamp)
            
            # Other string formats
            from dateutil import parser
            dt = parser.parse(timestamp)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        
        raise ValueError(f"Cannot normalize timestamp: {timestamp}")
    
    @staticmethod
    def normalize_coordinates(
        lat: Union[str, float],
        lon: Union[str, float]
    ) -> Dict[str, float]:
        """
        Normalize coordinate data.
        
        Args:
            lat: Latitude value
            lon: Longitude value
            
        Returns:
            Dictionary with normalized lat/lon
        """
        return {
            'latitude': float(lat),
            'longitude': float(lon)
        }
    
    @staticmethod
    def normalize_json_field(
        data: Union[str, dict, list]
    ) -> Union[dict, list]:
        """
        Normalize JSON field data.
        
        Args:
            data: JSON data as string or object
            
        Returns:
            Parsed JSON object
        """
        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return {'raw': data}
        return data
    
    @staticmethod
    def normalize_numeric(
        value: Union[str, int, float],
        default: float = 0.0
    ) -> float:
        """
        Normalize numeric values.
        
        Args:
            value: Value to normalize
            default: Default if conversion fails
            
        Returns:
            Float value
        """
        if value is None:
            return default
        
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    @staticmethod
    def normalize_boolean(
        value: Union[str, bool, int, None]
    ) -> bool:
        """
        Normalize boolean values.
        
        Args:
            value: Value to normalize
            
        Returns:
            Boolean value
        """
        if isinstance(value, bool):
            return value
        
        if isinstance(value, str):
            return value.lower() in ('true', 'yes', '1', 'on')
        
        if isinstance(value, int):
            return value != 0
        
        return False
    
    @staticmethod
    def normalize_string(
        value: Any,
        max_length: Optional[int] = None,
        default: str = ''
    ) -> str:
        """
        Normalize string values.
        
        Args:
            value: Value to normalize
            max_length: Optional max length
            default: Default if conversion fails
            
        Returns:
            String value
        """
        if value is None:
            return default
        
        result = str(value).strip()
        
        if max_length and len(result) > max_length:
            result = result[:max_length]
        
        return result
    
    @staticmethod
    def generate_hash(
        data: Dict[str, Any],
        fields: Optional[List[str]] = None
    ) -> str:
        """
        Generate hash for data deduplication.
        
        Args:
            data: Data dictionary
            fields: Optional list of fields to include in hash
            
        Returns:
            SHA256 hash string
        """
        if fields:
            hash_data = {k: data.get(k) for k in fields if k in data}
        else:
            hash_data = data
        
        # Create stable string representation
        stable_str = json.dumps(
            hash_data,
            sort_keys=True,
            default=str
        )
        
        return hashlib.sha256(stable_str.encode()).hexdigest()
    
    @staticmethod
    def normalize_units(
        value: float,
        from_unit: str,
        to_unit: str
    ) -> float:
        """
        Convert between common units.
        
        Args:
            value: Numeric value
            from_unit: Source unit
            to_unit: Target unit
            
        Returns:
            Converted value
        """
        conversions = {
            # Distance
            ('meters', 'kilometers'): lambda x: x / 1000,
            ('kilometers', 'meters'): lambda x: x * 1000,
            ('miles', 'kilometers'): lambda x: x * 1.60934,
            ('kilometers', 'miles'): lambda x: x / 1.60934,
            ('feet', 'meters'): lambda x: x * 0.3048,
            ('meters', 'feet'): lambda x: x / 0.3048,
            
            # Temperature
            ('celsius', 'fahrenheit'): lambda x: (x * 9/5) + 32,
            ('fahrenheit', 'celsius'): lambda x: (x - 32) * 5/9,
            
            # Speed
            ('m/s', 'km/h'): lambda x: x * 3.6,
            ('km/h', 'm/s'): lambda x: x / 3.6,
            ('mph', 'km/h'): lambda x: x * 1.60934,
            ('km/h', 'mph'): lambda x: x / 1.60934,
        }
        
        key = (from_unit.lower(), to_unit.lower())
        if key in conversions:
            return conversions[key](value)
        
        # No conversion needed or not supported
        return value
    
    @classmethod
    def normalize_stream_data(
        cls,
        data: Dict[str, Any],
        stream_type: str
    ) -> Dict[str, Any]:
        """
        Normalize data based on stream type.
        
        Args:
            data: Raw data dictionary
            stream_type: Type of stream (e.g., 'location', 'health')
            
        Returns:
            Normalized data dictionary
        """
        normalized = {}
        
        # Common fields
        if 'timestamp' in data:
            normalized['timestamp'] = cls.normalize_timestamp(data['timestamp'])
        
        # Stream-specific normalization
        if stream_type == 'location':
            if 'latitude' in data and 'longitude' in data:
                coords = cls.normalize_coordinates(
                    data['latitude'],
                    data['longitude']
                )
                normalized.update(coords)
            
            if 'altitude' in data:
                normalized['altitude'] = cls.normalize_numeric(data['altitude'])
            
            if 'speed' in data:
                normalized['speed'] = cls.normalize_numeric(data['speed'])
        
        elif stream_type == 'health':
            if 'heart_rate' in data:
                normalized['heart_rate'] = cls.normalize_numeric(
                    data['heart_rate']
                )
            
            if 'steps' in data:
                normalized['steps'] = int(cls.normalize_numeric(data['steps']))
        
        # Copy remaining fields
        for key, value in data.items():
            if key not in normalized:
                normalized[key] = value
        
        return normalized