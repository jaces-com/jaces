"""Base normalizer class with common functionality for all sources."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union
from uuid import uuid4
import os


class BaseNormalizer(ABC):
    """
    Abstract base class for all source normalizers.
    Provides common utilities and enforces consistent interface.
    """

    def __init__(self, fidelity_score: Optional[float] = None, insider_tip: Optional[str] = None):
        """
        Initialize the normalizer with common parameters.

        Args:
            fidelity_score: Confidence multiplier for this source (0.0 to 1.0).
                          If None, will use configured default for this source.
            insider_tip: Optional description/context from the user
        """
        self._provided_fidelity_score = fidelity_score
        self.insider_tip = insider_tip
        # Defer fidelity score calculation to a property since we need get_source_name()

    @property
    def fidelity_score(self) -> float:
        """Get the fidelity score, using default if not provided."""
        if hasattr(self, '_calculated_fidelity_score'):
            return self._calculated_fidelity_score

        if self._provided_fidelity_score is None:
            # Use a default fidelity score of 0.9 for all sources
            # (can be overridden by passing fidelity_score to constructor)
            score = 0.9
        else:
            score = self._provided_fidelity_score

        self._calculated_fidelity_score = max(0.0, min(1.0, score))
        return self._calculated_fidelity_score

    @abstractmethod
    def normalize(self, *args, **kwargs) -> List[Dict[str, Any]]:
        """
        Main normalization method that must be implemented by each source.
        Should return a list of signal dictionaries ready for database insertion.
        """
        pass

    def generate_signal_id(self) -> str:
        """Generate a unique UUID for a signal."""
        return str(uuid4())

    def parse_timestamp(self, timestamp: Union[str, datetime, None]) -> str:
        """
        Parse various timestamp formats to ISO format string.

        Args:
            timestamp: String, datetime object, or None

        Returns:
            ISO format timestamp string
        """
        if timestamp is None:
            return datetime.now(timezone.utc).isoformat()

        if isinstance(timestamp, datetime):
            # Ensure timezone aware
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            return timestamp.isoformat()

        if isinstance(timestamp, str):
            # Handle 'Z' suffix
            if timestamp.endswith('Z'):
                timestamp = timestamp[:-1] + '+00:00'

            try:
                # Parse and ensure timezone
                dt = datetime.fromisoformat(timestamp)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except ValueError:
                # Fallback to current time
                return datetime.now(timezone.utc).isoformat()

        # Default fallback
        return datetime.now(timezone.utc).isoformat()

    def calculate_confidence(self, base_confidence: float = 1.0, **factors) -> float:
        """
        Calculate adjusted confidence score based on various factors.

        Args:
            base_confidence: Starting confidence value
            **factors: Named factors that might reduce confidence

        Returns:
            Adjusted confidence score between 0.0 and 1.0
        """
        confidence = base_confidence * self.fidelity_score

        # Apply any additional factors
        for factor_name, factor_value in factors.items():
            if isinstance(factor_value, (int, float)):
                confidence *= factor_value

        return max(0.0, min(1.0, confidence))

    def clean_text(self, text: Optional[str]) -> Optional[str]:
        """Clean and normalize text values."""
        if not text:
            return None

        # Strip whitespace and normalize
        cleaned = text.strip()

        # Remove null bytes and other problematic characters
        cleaned = cleaned.replace('\x00', '').replace('\r\n', '\n')

        return cleaned if cleaned else None

    def ensure_list(self, value: Union[str, List[str], None]) -> Optional[List[str]]:
        """Ensure a value is a list of strings or None."""
        if value is None:
            return None

        if isinstance(value, str):
            return [value] if value else None

        if isinstance(value, list):
            # Filter out empty strings
            filtered = [str(v) for v in value if v]
            return filtered if filtered else None

        return None

    def create_signal(
        self,
        signal_name: str,
        signal_value: str,
        timestamp: Union[str, datetime],
        confidence: Optional[float] = None,
        source_event_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create an ambient signal dictionary in the correct format.

        Args:
            signal_name: Type of signal (e.g., 'location', 'sound_classification')
            signal_value: String representation of the value
            timestamp: When the signal occurred
            confidence: Confidence score (will use default if not provided)
            source_event_id: UUID linking related signals
            metadata: Additional metadata to store

        Returns:
            Dictionary ready for database insertion
        """
        return {
            "id": self.generate_signal_id(),
            "source_name": self.get_source_name(),
            "timestamp": self.parse_timestamp(timestamp),
            "confidence": confidence if confidence is not None else self.fidelity_score,
            "signal_name": signal_name,
            "signal_value": signal_value,
            "source_event_id": source_event_id or self.generate_signal_id(),
            "metadata": metadata
        }

    @abstractmethod
    def get_source_name(self) -> str:
        """Return the source name for this normalizer."""
        pass
