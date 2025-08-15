"""Strava API client wrapper."""

import httpx
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from urllib.parse import urlencode


class StravaClient:
    """Client for interacting with Strava API v3."""
    
    BASE_URL = "https://www.strava.com/api/v3"
    
    def __init__(self, access_token: str, token_refresher: Optional[Callable] = None):
        self.access_token = access_token
        self.token_refresher = token_refresher
        self._update_headers()
    
    def _update_headers(self):
        """Update authorization headers with current token."""
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json"
        }
    
    async def _make_request(
        self, 
        method: str, 
        url: str, 
        retry_on_401: bool = True,
        **kwargs
    ) -> httpx.Response:
        """Make an HTTP request with automatic token refresh on 401."""
        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, headers=self.headers, **kwargs)
            
            # If we get a 401 and have a token refresher, try to refresh
            if response.status_code == 401 and retry_on_401 and self.token_refresher:
                try:
                    # Call the token refresher
                    new_access_token = await self.token_refresher()
                    
                    if new_access_token:
                        # Update our token and headers
                        self.access_token = new_access_token
                        self._update_headers()
                        
                        # Retry the request once
                        response = await client.request(method, url, headers=self.headers, **kwargs)
                except Exception as e:
                    # If refresh fails, return the original 401 response
                    import sys
                    print(f"Token refresh failed: {str(e)}", file=sys.stderr)
                    pass
            
            return response
    
    async def get_athlete(self) -> Dict[str, Any]:
        """Get the authenticated athlete's profile."""
        response = await self._make_request(
            "GET",
            f"{self.BASE_URL}/athlete"
        )
        response.raise_for_status()
        return response.json()
    
    async def list_activities(
        self,
        before: Optional[int] = None,  # Unix timestamp
        after: Optional[int] = None,   # Unix timestamp  
        page: int = 1,
        per_page: int = 30  # Strava recommends 30
    ) -> List[Dict[str, Any]]:
        """
        List athlete activities.
        
        Args:
            before: Activities before this Unix timestamp
            after: Activities after this Unix timestamp
            page: Page number
            per_page: Number of items per page (max 200)
            
        Returns:
            List of activity summaries
        """
        params = {
            "page": page,
            "per_page": min(per_page, 200)  # Strava max is 200
        }
        
        if before is not None:
            params["before"] = before
        if after is not None:
            params["after"] = after
        
        response = await self._make_request(
            "GET",
            f"{self.BASE_URL}/athlete/activities",
            params=params
        )
        response.raise_for_status()
        return response.json()
    
    async def get_activity(self, activity_id: int, include_all_efforts: bool = False) -> Dict[str, Any]:
        """
        Get detailed information about a specific activity.
        
        Args:
            activity_id: The activity ID
            include_all_efforts: Include all segment efforts
            
        Returns:
            Detailed activity data
        """
        params = {}
        if include_all_efforts:
            params["include_all_efforts"] = "true"
        
        response = await self._make_request(
            "GET",
            f"{self.BASE_URL}/activities/{activity_id}",
            params=params if params else None
        )
        response.raise_for_status()
        return response.json()
    
    async def get_activity_streams(
        self, 
        activity_id: int,
        keys: Optional[List[str]] = None,
        key_by_type: bool = True
    ) -> Dict[str, Any]:
        """
        Get activity streams (time series data).
        
        Args:
            activity_id: The activity ID
            keys: List of stream types to retrieve (e.g., ['time', 'distance', 'altitude', 'heartrate'])
            key_by_type: Return dict keyed by stream type
            
        Returns:
            Stream data
        """
        # Default streams to retrieve
        if keys is None:
            keys = ['time', 'distance', 'altitude', 'velocity_smooth', 'heartrate', 
                   'cadence', 'watts', 'temp', 'moving', 'grade_smooth']
        
        params = {
            "keys": ",".join(keys),
            "key_by_type": "true" if key_by_type else "false"
        }
        
        response = await self._make_request(
            "GET",
            f"{self.BASE_URL}/activities/{activity_id}/streams",
            params=params
        )
        
        # Streams endpoint returns 404 if activity has no streams
        if response.status_code == 404:
            return {}
        
        response.raise_for_status()
        return response.json()
    
    async def get_activity_zones(self, activity_id: int) -> List[Dict[str, Any]]:
        """
        Get activity zones (heart rate/power zones).
        
        Args:
            activity_id: The activity ID
            
        Returns:
            Zone data
        """
        response = await self._make_request(
            "GET",
            f"{self.BASE_URL}/activities/{activity_id}/zones"
        )
        
        # Zones endpoint returns 404 if activity has no zones
        if response.status_code == 404:
            return []
        
        response.raise_for_status()
        return response.json()
    
    async def get_activity_laps(self, activity_id: int) -> List[Dict[str, Any]]:
        """
        Get activity laps.
        
        Args:
            activity_id: The activity ID
            
        Returns:
            List of laps
        """
        response = await self._make_request(
            "GET",
            f"{self.BASE_URL}/activities/{activity_id}/laps"
        )
        response.raise_for_status()
        return response.json()
    
    async def get_stats(self, athlete_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get athlete statistics.
        
        Args:
            athlete_id: Athlete ID (uses authenticated athlete if None)
            
        Returns:
            Athlete statistics
        """
        if athlete_id is None:
            # Get authenticated athlete's ID
            athlete = await self.get_athlete()
            athlete_id = athlete["id"]
        
        response = await self._make_request(
            "GET",
            f"{self.BASE_URL}/athletes/{athlete_id}/stats"
        )
        response.raise_for_status()
        return response.json()