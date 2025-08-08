"""Sync implementation for iOS mic transcription data."""

from typing import Dict, Any
from sources.base.generated_models.signals import Signals
# from .normalizer import IosMicTranscriptionNormalizer  # Removed - using stream processors


class IosMicTranscriptionSync:
    """
    Handles syncing iOS mic transcription data from devices.
    
    This is a push-based source, so the sync method is minimal.
    The actual data processing happens via the ingestion endpoint.
    """
    
    requires_credentials = False  # This source uses device tokens
    
    def __init__(self, signal: Signals):
        self.signal = signal
        # Normalizer removed - using stream processors
        # self.normalizer = IosMicTranscriptionNormalizer()
    
    async def run(self) -> Dict[str, Any]:
        """
        Sync method for mic transcription data.
        
        Since this is a push-based source where data comes from the device,
        there's nothing to actively sync. Data is processed via the ingestion endpoint.
        """
        return {
            "status": "success",
            "message": "iOS mic transcription is a push-based source. Data is received via ingestion endpoint.",
            "records_processed": 0
        }