"""
Generic deduplication utilities for stream to signal processing.

Provides deterministic idempotency key generation based on signal computation type.
"""

import hashlib
from datetime import datetime
from typing import Dict, Any


def generate_idempotency_key(dedup_strategy: str, timestamp: datetime, data: Dict[str, Any]) -> str:
    """
    Generate deterministic idempotency key based on deduplication strategy.
    
    Deduplication strategies:
    - 'single': One value per timestamp (time-series data like heart rate, temperature)
    - 'multiple': Multiple values allowed at same timestamp (events like calendar, workouts)
    
    Args:
        dedup_strategy: Deduplication strategy ('single' or 'multiple')
        timestamp: Timestamp of the signal
        data: Signal data dict containing value and metadata
        
    Returns:
        Deterministic idempotency key string
    """
    
    if dedup_strategy == 'multiple':
        # Multiple events can exist at the same timestamp
        # Include unique content identifier to distinguish them
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
    elif dedup_strategy == 'single':
        # Only one value allowed per timestamp
        # This enforces that signals can only have one value at any given time
        return timestamp.isoformat()
    else:
        raise ValueError(f"Invalid dedup_strategy: {dedup_strategy}. Must be 'single' or 'multiple'")


def should_deduplicate_by_timestamp_only(dedup_strategy: str) -> bool:
    """
    Determine if a signal should deduplicate by timestamp only.
    
    Args:
        dedup_strategy: Deduplication strategy ('single' or 'multiple')
        
    Returns:
        True if deduplication should be by timestamp only, False if content matters
    """
    return dedup_strategy == 'single'