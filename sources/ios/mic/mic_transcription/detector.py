"""Placeholder detector for iOS mic transcription signal."""

from typing import List, Dict, Any, Optional
from datetime import datetime


class MicTranscriptionTransitionDetector:
    """
    Placeholder transition detector for mic transcription.
    
    This is a stub implementation for future transcription analysis.
    When implemented, this could detect:
    - Topic changes in conversation
    - Sentiment shifts
    - Speaker changes
    - Silence/speech boundaries
    """
    
    def __init__(self):
        self.signal_name = "ios_mic_transcription"
        self.enabled = False  # Disabled until transcription is implemented
    
    def detect_transitions(
        self, 
        signals: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Placeholder for transition detection.
        
        Args:
            signals: List of transcription signals
            
        Returns:
            Empty list (no transitions detected)
        """
        # TODO: Implement when transcription service is available
        return []
    
    def analyze_text(
        self,
        text: str,
        timestamp: datetime,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Placeholder for text analysis.
        
        Future implementation could include:
        - Topic extraction
        - Sentiment analysis
        - Entity recognition
        - Language detection
        
        Args:
            text: Transcribed text
            timestamp: When the audio was recorded
            metadata: Additional context
            
        Returns:
            Analysis results (currently empty)
        """
        return {
            "status": "not_implemented",
            "message": "Transcription analysis pending implementation"
        }