"""Sync implementation for Apple Mac apps data."""

from typing import Dict, Any, List, Optional
from datetime import datetime

# from .normalizer import MacAppsNormalizer  # Removed - using stream processors
from sources.base.generated_models.signals import Signals


class MacAppsSync:
    """
    Handles syncing Mac apps data from devices.
    
    This is a push-based source, so the sync method is minimal.
    The actual data processing happens via the ingestion endpoint.
    """
    
    requires_credentials = False  # This source uses device tokens
    
    def __init__(self, signal: Signals = None):
        # This is a push-based source, signal details come from the signal
        self.signal = signal
        # Normalizer removed - using stream processors
        # self.normalizer = MacAppsNormalizer(
        #     fidelity_score=signal.fidelity_score if signal else 0.95,
        #     insider_tip=signal.description if signal else None
        # )
    
    async def sync(self) -> Dict[str, Any]:
        """
        Sync method for Mac apps data.
        
        Since this is a push-based source (data comes from devices),
        this method doesn't actively pull data. It's here for consistency
        with the sync interface.
        
        Returns:
            Status dictionary
        """
        return {
            "status": "success",
            "message": "Mac apps is a push-based source. Data is received via the ingestion endpoint.",
            "records_synced": 0,
            "source": "mac",
            "signal_id": str(self.signal.id) if self.signal and hasattr(self.signal, 'id') else None,
            "is_push_based": True
        }
    
    async def test_connection(self) -> Dict[str, Any]:
        """
        Test the connection for this source.
        
        For device-based sources, this checks if the device token is valid.
        
        Returns:
            Test result dictionary
        """
        # For push-based sources, we don't have device tokens anymore
        # Just check if signal exists
        if not self.signal:
            return {
                "success": False,
                "error": "No signal configured"
            }
        
        # Check if we've received data recently
        last_ingestion = self.signal.last_successful_ingestion_at if self.signal else None
        if last_ingestion:
            time_since = datetime.utcnow() - last_ingestion
            hours_since = time_since.total_seconds() / 3600
            
            if hours_since < 24:
                status = "healthy"
                message = f"Last received data {hours_since:.1f} hours ago"
            elif hours_since < 72:
                status = "warning"
                message = f"No data received in {hours_since:.1f} hours"
            else:
                status = "inactive"
                message = f"No data received in {time_since.days} days"
        else:
            status = "new"
            message = "No data received yet"
        
        return {
            "success": True,
            "status": status,
            "message": message,
            "signal_name": self.signal.name if self.signal else None
        }