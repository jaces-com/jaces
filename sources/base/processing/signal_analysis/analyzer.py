"""
Main signal analysis orchestrator for transition detection
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID
import logging

from sqlalchemy.orm import Session

from sources.base.generated_models.signals import Signals
from sources.base.generated_models.signal_transitions import SignalTransitions
from .strategies.ambient import AmbientBoundaryDetector

logger = logging.getLogger(__name__)


class SignalAnalyzer:
    """
    Main signal analysis class for transition detection
    """
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.ambient_detector = AmbientBoundaryDetector(db_session)
        
    def detect_transitions(
        self, 
        user_id: UUID, 
        start_time: datetime, 
        end_time: datetime,
        signal_name: Optional[str] = None
    ) -> List[SignalTransitions]:
        """
        Main entry point for transition detection
        
        Args:
            user_id: User ID to process
            start_time: Start of time window
            end_time: End of time window
            signal_name: Optional specific signal to analyze
            
        Returns:
            List of detected transitions
        """
        logger.info(f"Starting transition detection for user {user_id}")
        
        try:
            # Use ambient detector for transition detection
            transitions = self.ambient_detector.detect(
                user_id, start_time, end_time, signal_name
            )
            logger.info(f"Found {len(transitions)} transitions")
            
            return transitions
            
        except Exception as e:
            logger.error(f"Transition detection failed: {e}", exc_info=True)
            raise