"""
Generic deduplication utilities for stream to signal processing.

Provides deterministic source_event_id generation based on signal computation type.
"""

import hashlib
from datetime import datetime
from typing import Dict, Any


def generate_source_event_id(value_type: str, timestamp: datetime, data: Dict[str, Any]) -> str:
    """
    Generate deterministic source_event_id based on signal computation value_type.
    
    For time-series value types (continuous, binary, categorical, spatial, count):
    - Uses timestamp only, enforcing one value per timestamp
    
    For event value type:
    - Includes unique content identifier to allow multiple concurrent values
    
    Args:
        value_type: Signal computation value_type ('continuous', 'binary', 'categorical', 'spatial', 'count', 'event')
        timestamp: Timestamp of the signal
        data: Signal data dict containing value and metadata
        
    Returns:
        Deterministic source_event_id string
    """
    
    if value_type == 'event':
        # For event data, include unique content to allow overlaps
        # Try to find a unique identifier in the data
        content_key = (
            data.get('event_id') or 
            data.get('id') or
            data.get('uuid') or
            # If no ID, create hash of key content
            hashlib.md5(
                f"{data.get('title', '')}:{data.get('summary', '')}:{data.get('value', '')}".encode()
            ).hexdigest()[:8]
        )
        return f"{timestamp.isoformat()}:{content_key}"
    else:
        # Time-series data: one value per timestamp
        # This enforces that signals can only have one value at any given time
        return timestamp.isoformat()


def should_deduplicate_by_timestamp_only(value_type: str) -> bool:
    """
    Determine if a signal value_type should deduplicate by timestamp only.
    
    Args:
        value_type: Signal computation value_type
        
    Returns:
        True if deduplication should be by timestamp only, False if content matters
    """
    return value_type != 'event'