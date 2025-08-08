"""
Utility functions for boundary detection
"""
from collections import namedtuple
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Any
import heapq


Event = namedtuple('Event', ['timestamp', 'type', 'source', 'confidence'])


def merge_intervals_sweep_line(
    boundary_signals: Dict[str, List[Dict[str, Any]]], 
    min_duration_minutes: int = 10,
    merge_threshold_minutes: int = 5
) -> List[Dict[str, Any]]:
    """
    Convert source-specific boundaries into consolidated daily events using sweep-line algorithm
    
    Args:
        boundary_signals: Dict mapping source names to lists of boundary dicts
            Each boundary dict should have: {'start': datetime, 'end': datetime, 'confidence': float}
        min_duration_minutes: Minimum event duration in minutes
        merge_threshold_minutes: Gap threshold for merging nearby events
        
    Returns:
        List of merged boundary dicts with structure:
            {'start': datetime, 'end': datetime, 'confidence': float, 'sources': List[str]}
    """
    events = []
    
    # Convert all boundary signals to start/end events
    for source, boundaries in boundary_signals.items():
        for boundary in boundaries:
            confidence = boundary.get('confidence', 0.5)
            events.append(Event(boundary['start'], 'start', source, confidence))
            events.append(Event(boundary['end'], 'end', source, confidence))
    
    # Sort by timestamp
    events.sort(key=lambda x: x.timestamp)
    
    # Sweep line algorithm
    active_sources = {}  # source -> confidence mapping
    consolidated_events = []
    current_start = None
    max_confidence = 0
    
    for event in events:
        if event.type == 'start':
            if not active_sources:  # First source starts new event
                current_start = event.timestamp
                max_confidence = event.confidence
            active_sources[event.source] = event.confidence
            max_confidence = max(max_confidence, event.confidence)
            
        else:  # event.type == 'end'
            if event.source in active_sources:
                del active_sources[event.source]
            
            if not active_sources and current_start:  # Last source ends event
                duration = (event.timestamp - current_start).total_seconds() / 60
                
                # Only keep events longer than minimum duration
                if duration >= min_duration_minutes:
                    consolidated_events.append({
                        'start': current_start,
                        'end': event.timestamp,
                        'confidence': max_confidence,
                        'sources': [event.source]  # Will be updated in post-processing
                    })
                current_start = None
                max_confidence = 0
    
    # Post-process to merge nearby events and update source lists
    merged_events = []
    for event in consolidated_events:
        if merged_events and (event['start'] - merged_events[-1]['end']).total_seconds() / 60 <= merge_threshold_minutes:
            # Merge with previous event
            merged_events[-1]['end'] = event['end']
            merged_events[-1]['confidence'] = max(merged_events[-1]['confidence'], event['confidence'])
            # Update sources list by checking which sources contributed
            merged_events[-1]['sources'] = _get_contributing_sources(
                boundary_signals, 
                merged_events[-1]['start'], 
                merged_events[-1]['end']
            )
        else:
            # Update sources list for standalone event
            event['sources'] = _get_contributing_sources(
                boundary_signals, 
                event['start'], 
                event['end']
            )
            merged_events.append(event)
    
    return merged_events


def _get_contributing_sources(
    boundary_signals: Dict[str, List[Dict[str, Any]]], 
    start: datetime, 
    end: datetime
) -> List[str]:
    """
    Determine which sources contributed to a time range
    """
    sources = []
    for source, boundaries in boundary_signals.items():
        for boundary in boundaries:
            # Check if boundary overlaps with the time range
            if boundary['start'] < end and boundary['end'] > start:
                sources.append(source)
                break
    return sources


def scale_parameters(window_hours: float) -> Dict[str, int]:
    """
    Scale boundary detection parameters based on time window size
    
    Args:
        window_hours: Duration of the time window in hours
        
    Returns:
        Dict with scaled parameters
    """
    if window_hours <= 4:
        return {
            'min_duration': 10,      # 10 minutes minimum
            'max_duration': 90,      # 90 minutes maximum
            'merge_threshold': 5     # 5 minutes gap threshold
        }
    elif window_hours <= 12:
        return {
            'min_duration': 15,      # 15 minutes minimum
            'max_duration': 120,     # 2 hours maximum
            'merge_threshold': 10    # 10 minutes gap threshold
        }
    else:  # Full day or more
        return {
            'min_duration': 20,      # 20 minutes minimum
            'max_duration': 180,     # 3 hours maximum
            'merge_threshold': 15    # 15 minutes gap threshold
        }


def confidence_weighted_merge(
    boundaries: List[Dict[str, Any]], 
    source_weights: Dict[str, float]
) -> List[Dict[str, Any]]:
    """
    Alternative merging strategy that uses source confidence weights
    
    Args:
        boundaries: List of boundary dicts
        source_weights: Dict mapping source names to weight values
        
    Returns:
        List of merged boundaries with weighted confidence
    """
    if not boundaries:
        return []
    
    # Sort by start time
    sorted_boundaries = sorted(boundaries, key=lambda x: x['start'])
    
    merged = []
    for boundary in sorted_boundaries:
        weight = source_weights.get(boundary.get('source', ''), 0.5)
        
        if merged and boundary['start'] <= merged[-1]['end']:
            # Overlap detected - extend and update confidence
            merged[-1]['end'] = max(boundary['end'], merged[-1]['end'])
            merged[-1]['confidence'] = max(weight, merged[-1]['confidence'])
            if 'sources' in merged[-1]:
                merged[-1]['sources'].append(boundary.get('source', 'unknown'))
            else:
                merged[-1]['sources'] = [boundary.get('source', 'unknown')]
        else:
            # No overlap - add as new boundary
            boundary['confidence'] = weight
            boundary['sources'] = [boundary.get('source', 'unknown')]
            merged.append(boundary)
    
    return merged