"""Abstract base class for all source syncs."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from datetime import datetime


class BaseSync(ABC):
    """
    Abstract base class for all source sync implementations.
    
    Each source must implement this interface to handle data fetching
    and synchronization with the platform.
    """
    
    def __init__(self, source_id: str, config: Dict[str, Any]):
        """
        Initialize the sync handler.
        
        Args:
            source_id: Unique identifier for the source instance
            config: Source-specific configuration from database
        """
        self.source_id = source_id
        self.config = config
    
    @abstractmethod
    async def authenticate(self) -> bool:
        """
        Authenticate with the source.
        
        Returns:
            True if authentication successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def sync(
        self, 
        since: Optional[datetime] = None,
        until: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Perform a sync operation.
        
        Args:
            since: Optional start time for incremental sync
            until: Optional end time for sync window
            
        Returns:
            Dict containing sync results and metadata
        """
        pass
    
    @abstractmethod
    async def test_connection(self) -> bool:
        """
        Test the connection to the source.
        
        Returns:
            True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    def get_sync_schedule(self) -> Optional[str]:
        """
        Get the cron schedule for this sync.
        
        Returns:
            Cron schedule string or None for push-based sources
        """
        pass
    
    @abstractmethod
    def get_required_config_fields(self) -> List[str]:
        """
        Get list of required configuration fields.
        
        Returns:
            List of field names required for this sync
        """
        pass