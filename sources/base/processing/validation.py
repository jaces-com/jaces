"""Data validation utilities for stream processing."""

from typing import Any, Dict, List, Optional, Union, Callable
from datetime import datetime, timedelta
import re


class DataValidator:
    """Validates data from various sources."""
    
    @staticmethod
    def validate_required_fields(
        data: Dict[str, Any],
        required_fields: List[str]
    ) -> bool:
        """
        Check if all required fields are present.
        
        Args:
            data: Data dictionary to validate
            required_fields: List of required field names
            
        Returns:
            True if all required fields present
        """
        return all(field in data and data[field] is not None 
                  for field in required_fields)
    
    @staticmethod
    def validate_timestamp(
        timestamp: Any,
        min_date: Optional[datetime] = None,
        max_date: Optional[datetime] = None
    ) -> bool:
        """
        Validate timestamp is within reasonable bounds.
        
        Args:
            timestamp: Timestamp to validate
            min_date: Optional minimum date
            max_date: Optional maximum date
            
        Returns:
            True if timestamp is valid
        """
        if not timestamp:
            return False
        
        # Default bounds if not specified
        if min_date is None:
            min_date = datetime(2000, 1, 1)
        if max_date is None:
            max_date = datetime.now() + timedelta(days=1)
        
        if isinstance(timestamp, datetime):
            return min_date <= timestamp <= max_date
        
        try:
            # Try to parse if string
            if isinstance(timestamp, str):
                from dateutil import parser
                dt = parser.parse(timestamp)
                return min_date <= dt <= max_date
            
            # Try as unix timestamp
            if isinstance(timestamp, (int, float)):
                if timestamp > 10**10:  # Milliseconds
                    timestamp = timestamp / 1000
                dt = datetime.fromtimestamp(timestamp)
                return min_date <= dt <= max_date
        except Exception:
            return False
        
        return False
    
    @staticmethod
    def validate_coordinates(
        lat: Any,
        lon: Any
    ) -> bool:
        """
        Validate GPS coordinates.
        
        Args:
            lat: Latitude value
            lon: Longitude value
            
        Returns:
            True if coordinates are valid
        """
        try:
            lat_float = float(lat)
            lon_float = float(lon)
            
            # Valid ranges
            return -90 <= lat_float <= 90 and -180 <= lon_float <= 180
        except (ValueError, TypeError):
            return False
    
    @staticmethod
    def validate_numeric_range(
        value: Any,
        min_value: Optional[float] = None,
        max_value: Optional[float] = None
    ) -> bool:
        """
        Validate numeric value is within range.
        
        Args:
            value: Value to validate
            min_value: Optional minimum value
            max_value: Optional maximum value
            
        Returns:
            True if value is within range
        """
        try:
            numeric = float(value)
            
            if min_value is not None and numeric < min_value:
                return False
            if max_value is not None and numeric > max_value:
                return False
            
            return True
        except (ValueError, TypeError):
            return False
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """
        Validate email address format.
        
        Args:
            email: Email address to validate
            
        Returns:
            True if email format is valid
        """
        if not email or not isinstance(email, str):
            return False
        
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))
    
    @staticmethod
    def validate_url(url: str) -> bool:
        """
        Validate URL format.
        
        Args:
            url: URL to validate
            
        Returns:
            True if URL format is valid
        """
        if not url or not isinstance(url, str):
            return False
        
        pattern = r'^https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)$'
        return bool(re.match(pattern, url))
    
    @staticmethod
    def validate_uuid(uuid_string: str) -> bool:
        """
        Validate UUID format.
        
        Args:
            uuid_string: UUID string to validate
            
        Returns:
            True if UUID format is valid
        """
        if not uuid_string or not isinstance(uuid_string, str):
            return False
        
        pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
        return bool(re.match(pattern, uuid_string.lower()))
    
    @staticmethod
    def validate_json_schema(
        data: Dict[str, Any],
        schema: Dict[str, Any]
    ) -> bool:
        """
        Validate data against a simple schema.
        
        Args:
            data: Data to validate
            schema: Schema definition
            
        Returns:
            True if data matches schema
        """
        for field, rules in schema.items():
            if 'required' in rules and rules['required']:
                if field not in data:
                    return False
            
            if field in data:
                value = data[field]
                
                # Type validation
                if 'type' in rules:
                    expected_type = rules['type']
                    if expected_type == 'string' and not isinstance(value, str):
                        return False
                    elif expected_type == 'number' and not isinstance(value, (int, float)):
                        return False
                    elif expected_type == 'boolean' and not isinstance(value, bool):
                        return False
                    elif expected_type == 'array' and not isinstance(value, list):
                        return False
                    elif expected_type == 'object' and not isinstance(value, dict):
                        return False
                
                # Range validation for numbers
                if isinstance(value, (int, float)):
                    if 'min' in rules and value < rules['min']:
                        return False
                    if 'max' in rules and value > rules['max']:
                        return False
                
                # Length validation for strings
                if isinstance(value, str):
                    if 'minLength' in rules and len(value) < rules['minLength']:
                        return False
                    if 'maxLength' in rules and len(value) > rules['maxLength']:
                        return False
                    if 'pattern' in rules and not re.match(rules['pattern'], value):
                        return False
        
        return True
    
    @classmethod
    def validate_stream_data(
        cls,
        data: Dict[str, Any],
        stream_type: str
    ) -> Dict[str, Union[bool, str]]:
        """
        Validate data based on stream type.
        
        Args:
            data: Data to validate
            stream_type: Type of stream
            
        Returns:
            Dictionary with 'valid' boolean and 'error' message if invalid
        """
        errors = []
        
        # Common validations
        if 'timestamp' in data:
            if not cls.validate_timestamp(data['timestamp']):
                errors.append("Invalid timestamp")
        
        # Stream-specific validations
        if stream_type == 'location':
            required = ['timestamp', 'latitude', 'longitude']
            if not cls.validate_required_fields(data, required):
                errors.append(f"Missing required fields: {required}")
            
            if 'latitude' in data and 'longitude' in data:
                if not cls.validate_coordinates(data['latitude'], data['longitude']):
                    errors.append("Invalid coordinates")
            
            if 'altitude' in data:
                if not cls.validate_numeric_range(data['altitude'], -500, 10000):
                    errors.append("Invalid altitude")
            
            if 'speed' in data:
                if not cls.validate_numeric_range(data['speed'], 0, 500):
                    errors.append("Invalid speed")
        
        elif stream_type == 'health':
            required = ['timestamp']
            if not cls.validate_required_fields(data, required):
                errors.append(f"Missing required fields: {required}")
            
            if 'heart_rate' in data:
                if not cls.validate_numeric_range(data['heart_rate'], 30, 250):
                    errors.append("Invalid heart rate")
            
            if 'steps' in data:
                if not cls.validate_numeric_range(data['steps'], 0, 100000):
                    errors.append("Invalid step count")
        
        if errors:
            return {'valid': False, 'error': '; '.join(errors)}
        
        return {'valid': True, 'error': None}
    
    @staticmethod
    def create_custom_validator(
        rules: Dict[str, Any]
    ) -> Callable[[Dict[str, Any]], bool]:
        """
        Create a custom validator function from rules.
        
        Args:
            rules: Validation rules dictionary
            
        Returns:
            Validator function
        """
        def validator(data: Dict[str, Any]) -> bool:
            return DataValidator.validate_json_schema(data, rules)
        
        return validator