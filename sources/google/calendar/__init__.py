"""Google Calendar source integration for Jaces."""

# Note: Import sync and client only when needed to avoid httpx dependency issues
# from .sync import GoogleCalendarSync
# from .client import GoogleCalendarClient

__all__ = ["GoogleCalendarSync", "GoogleCalendarClient"]