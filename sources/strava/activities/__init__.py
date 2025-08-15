"""Strava Activities stream module."""

# Note: Import sync and client only when needed to avoid httpx dependency issues
# from .sync import StravaActivitiesSync
# from .client import StravaClient

__all__ = ["StravaActivitiesSync", "StravaClient"]