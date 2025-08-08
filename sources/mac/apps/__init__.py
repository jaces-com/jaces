"""Apple Mac apps tracking source."""

from .sync import MacAppsSync
from .stream_processor import MacAppActivityStreamProcessor

__all__ = ["MacAppsSync", "MacAppActivityStreamProcessor"]