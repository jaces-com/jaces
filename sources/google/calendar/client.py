"""Google Calendar API client wrapper."""

import httpx
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from urllib.parse import urlencode


class GoogleCalendarClient:
    """Client for interacting with Google Calendar API v3."""
    
    BASE_URL = "https://www.googleapis.com/calendar/v3"
    
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
                    
                    # Update our token and headers
                    self.access_token = new_access_token
                    self._update_headers()
                    
                    # Retry the request once
                    response = await client.request(method, url, headers=self.headers, **kwargs)
                except Exception:
                    # If refresh fails, return the original 401 response
                    pass
            
            return response
    
    async def list_calendars(self) -> List[Dict[str, Any]]:
        """List all calendars accessible by the user."""
        response = await self._make_request(
            "GET",
            f"{self.BASE_URL}/users/me/calendarList"
        )
        response.raise_for_status()
        return response.json().get("items", [])
    
    async def list_events(
        self,
        calendar_id: str = "primary",
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        page_token: Optional[str] = None,
        sync_token: Optional[str] = None,
        max_results: int = 250,
        single_events: bool = True,
        order_by: str = "startTime",
        show_deleted: bool = False
    ) -> Dict[str, Any]:
        """
        List events from a calendar.
        
        Args:
            calendar_id: Calendar identifier (default: "primary")
            time_min: Lower bound for event's end time (ignored if sync_token provided)
            time_max: Upper bound for event's start time (ignored if sync_token provided)
            page_token: Token for pagination
            sync_token: Sync token for incremental sync (overrides time_min/time_max)
            max_results: Maximum events per page (max 2500)
            single_events: Expand recurring events into instances
            order_by: Order results by startTime or updated
            show_deleted: Whether to include deleted events (useful for sync)
        
        Returns:
            Dict containing events, nextPageToken, and nextSyncToken if available
        
        Raises:
            HTTPStatusError: If sync token is invalid (410 Gone), caller should retry with full sync
        """
        params = {
            "maxResults": min(max_results, 2500),
        }
        
        # Sync token takes precedence over all other parameters
        if sync_token:
            params["syncToken"] = sync_token
            # When using sync token, these params are not allowed
            params["showDeleted"] = True  # Always show deleted with sync token
        else:
            # Regular listing parameters
            params["singleEvents"] = single_events
            params["orderBy"] = order_by
            params["showDeleted"] = show_deleted
            
            if time_min:
                params["timeMin"] = time_min.isoformat() + "Z"
            if time_max:
                params["timeMax"] = time_max.isoformat() + "Z"
                
        if page_token:
            params["pageToken"] = page_token
        
        url = f"{self.BASE_URL}/calendars/{calendar_id}/events?{urlencode(params)}"
        
        response = await self._make_request("GET", url)
        response.raise_for_status()
        return response.json()
    
    async def get_event(self, calendar_id: str, event_id: str) -> Dict[str, Any]:
        """Get a single event by ID."""
        response = await self._make_request(
            "GET",
            f"{self.BASE_URL}/calendars/{calendar_id}/events/{event_id}"
        )
        response.raise_for_status()
        return response.json()