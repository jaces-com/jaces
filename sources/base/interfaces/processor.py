"""Abstract base class for stream processors."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime


class BaseStreamProcessor(ABC):
    """
    Abstract base class for all stream processing implementations.
    
    Stream processors handle the transformation of raw data into
    structured signals.
    """
    
    def __init__(self, stream_config: Dict[str, Any]):
        """
        Initialize the stream processor.
        
        Args:
            stream_config: Stream-specific configuration
        """
        self.stream_config = stream_config
        self.stream_name = stream_config.get('stream_name')
    
    @abstractmethod
    async def process_batch(
        self,
        raw_data: List[Dict[str, Any]],
        source_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Process a batch of raw data into signals.
        
        Args:
            raw_data: List of raw data items to process
            source_id: ID of the source that generated the data
            user_id: ID of the user who owns the data
            
        Returns:
            Dict containing processed signals and metadata
        """
        pass
    
    @abstractmethod
    def validate_data(self, data: Dict[str, Any]) -> bool:
        """
        Validate a single data item.
        
        Args:
            data: Data item to validate
            
        Returns:
            True if valid, False otherwise
        """
        pass
    
    @abstractmethod
    def normalize_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize a single data item.
        
        Args:
            data: Data item to normalize
            
        Returns:
            Normalized data dictionary
        """
        pass
    
    @abstractmethod
    def extract_timestamp(self, data: Dict[str, Any]) -> datetime:
        """
        Extract timestamp from a data item.
        
        Args:
            data: Data item
            
        Returns:
            Datetime object representing the data timestamp
        """
        pass
    
    @abstractmethod
    def get_signal_types(self) -> List[str]:
        """
        Get list of signal types this processor produces.
        
        Returns:
            List of signal type names
        """
        pass
    
    def deduplicate(
        self,
        data: List[Dict[str, Any]],
        existing_data: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Remove duplicate data items.
        
        Args:
            data: New data items
            existing_data: Optional existing data for comparison
            
        Returns:
            Deduplicated list of data items
        """
        # Default implementation - can be overridden
        if not existing_data:
            # Simple dedup based on all fields
            seen = set()
            unique = []
            for item in data:
                item_tuple = tuple(sorted(item.items()))
                if item_tuple not in seen:
                    seen.add(item_tuple)
                    unique.append(item)
            return unique
        
        # Dedup against existing data
        existing_tuples = {
            tuple(sorted(item.items())) for item in existing_data
        }
        return [
            item for item in data 
            if tuple(sorted(item.items())) not in existing_tuples
        ]