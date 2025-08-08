"""Notion API client for fetching pages and databases."""

import asyncio
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta


class NotionClient:
    """Client for interacting with Notion API."""
    
    BASE_URL = "https://api.notion.com/v1"
    API_VERSION = "2022-06-28"
    
    def __init__(self, access_token: str):
        """Initialize Notion client with access token."""
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Notion-Version": self.API_VERSION,
            "Content-Type": "application/json"
        }
        self.rate_limit_delay = 0.34  # ~3 requests per second
        self.last_request_time = 0
    
    async def _rate_limit(self):
        """Implement rate limiting to respect Notion's API limits."""
        current_time = asyncio.get_event_loop().time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.rate_limit_delay:
            await asyncio.sleep(self.rate_limit_delay - time_since_last)
        self.last_request_time = asyncio.get_event_loop().time()
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make an authenticated request to Notion API."""
        await self._rate_limit()
        
        url = f"{self.BASE_URL}{endpoint}"
        
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method,
                url=url,
                headers=self.headers,
                json=json_data,
                params=params,
                timeout=30.0
            )
            
            if response.status_code == 429:  # Rate limited
                retry_after = int(response.headers.get("Retry-After", "5"))
                await asyncio.sleep(retry_after)
                return await self._make_request(method, endpoint, json_data, params)
            
            response.raise_for_status()
            return response.json()
    
    async def search_pages(
        self,
        query: Optional[str] = None,
        filter_type: Optional[str] = None,  # 'page' or 'database'
        cursor: Optional[str] = None,
        page_size: int = 100,
        sort_by: str = "last_edited_time",
        sort_direction: str = "descending"
    ) -> Dict[str, Any]:
        """
        Search for pages and databases in the workspace.
        
        Args:
            query: Text query to search for
            filter_type: Filter by 'page' or 'database'
            cursor: Pagination cursor
            page_size: Number of results per page (max 100)
            sort_by: Sort field ('last_edited_time' or 'created_time')
            sort_direction: Sort direction ('ascending' or 'descending')
        
        Returns:
            Dict containing results and pagination info
        """
        payload = {
            "page_size": min(page_size, 100),
            "sort": {
                "timestamp": sort_by,
                "direction": sort_direction
            }
        }
        
        if query:
            payload["query"] = query
        
        if filter_type:
            payload["filter"] = {
                "property": "object",
                "value": filter_type
            }
        
        if cursor:
            payload["start_cursor"] = cursor
        
        return await self._make_request("POST", "/search", json_data=payload)
    
    async def get_page(self, page_id: str) -> Dict[str, Any]:
        """
        Get a specific page by ID.
        
        Args:
            page_id: The Notion page ID
        
        Returns:
            Page object with metadata
        """
        return await self._make_request("GET", f"/pages/{page_id}")
    
    async def get_page_content(self, page_id: str, cursor: Optional[str] = None) -> Dict[str, Any]:
        """
        Get the content blocks of a page.
        
        Args:
            page_id: The Notion page ID
            cursor: Pagination cursor for blocks
        
        Returns:
            Dict containing blocks and pagination info
        """
        params = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        
        return await self._make_request("GET", f"/blocks/{page_id}/children", params=params)
    
    async def get_database(self, database_id: str) -> Dict[str, Any]:
        """
        Get a specific database by ID.
        
        Args:
            database_id: The Notion database ID
        
        Returns:
            Database object with schema
        """
        return await self._make_request("GET", f"/databases/{database_id}")
    
    async def query_database(
        self,
        database_id: str,
        filter_obj: Optional[Dict] = None,
        sorts: Optional[List[Dict]] = None,
        cursor: Optional[str] = None,
        page_size: int = 100
    ) -> Dict[str, Any]:
        """
        Query a database for pages.
        
        Args:
            database_id: The Notion database ID
            filter_obj: Filter conditions
            sorts: Sort conditions
            cursor: Pagination cursor
            page_size: Number of results per page
        
        Returns:
            Dict containing database pages and pagination info
        """
        payload = {"page_size": min(page_size, 100)}
        
        if filter_obj:
            payload["filter"] = filter_obj
        
        if sorts:
            payload["sorts"] = sorts
        
        if cursor:
            payload["start_cursor"] = cursor
        
        return await self._make_request("POST", f"/databases/{database_id}/query", json_data=payload)
    
    async def get_user(self, user_id: str) -> Dict[str, Any]:
        """
        Get user information.
        
        Args:
            user_id: The Notion user ID
        
        Returns:
            User object
        """
        return await self._make_request("GET", f"/users/{user_id}")
    
    async def get_all_pages(
        self,
        filter_type: Optional[str] = None,
        since: Optional[datetime] = None,
        progress_callback=None
    ) -> List[Dict[str, Any]]:
        """
        Get all pages in the workspace with optional filtering.
        
        Args:
            filter_type: Filter by 'page' or 'database'
            since: Only get pages edited after this time
            progress_callback: Optional callback for progress updates
        
        Returns:
            List of all pages/databases
        """
        all_pages = []
        cursor = None
        page_count = 0
        
        # Build filter for last_edited_time if provided
        filter_obj = None
        if since:
            filter_obj = {
                "timestamp": "last_edited_time",
                "last_edited_time": {
                    "after": since.isoformat()
                }
            }
        
        while True:
            result = await self.search_pages(
                filter_type=filter_type,
                cursor=cursor,
                page_size=100
            )
            
            pages = result.get("results", [])
            all_pages.extend(pages)
            page_count += len(pages)
            
            if progress_callback:
                progress_callback(page_count, len(pages))
            
            # Check for more pages
            if not result.get("has_more"):
                break
            
            cursor = result.get("next_cursor")
        
        return all_pages
    
    async def extract_page_text(self, page_id: str) -> str:
        """
        Extract all text content from a page.
        
        Args:
            page_id: The Notion page ID
        
        Returns:
            Concatenated text content from all blocks
        """
        text_parts = []
        cursor = None
        
        while True:
            result = await self.get_page_content(page_id, cursor)
            blocks = result.get("results", [])
            
            for block in blocks:
                text = self._extract_text_from_block(block)
                if text:
                    text_parts.append(text)
            
            if not result.get("has_more"):
                break
            
            cursor = result.get("next_cursor")
        
        return "\n".join(text_parts)
    
    def _extract_text_from_block(self, block: Dict[str, Any]) -> str:
        """
        Extract text from a single block.
        
        Args:
            block: Notion block object
        
        Returns:
            Text content of the block
        """
        block_type = block.get("type")
        if not block_type:
            return ""
        
        # Handle different block types
        block_data = block.get(block_type, {})
        
        # Most text blocks have a rich_text field
        if "rich_text" in block_data:
            texts = []
            for text_obj in block_data["rich_text"]:
                if text_obj.get("type") == "text":
                    texts.append(text_obj.get("text", {}).get("content", ""))
            return " ".join(texts)
        
        # Handle special block types
        if block_type == "child_page":
            return f"[Child Page: {block_data.get('title', 'Untitled')}]"
        elif block_type == "child_database":
            return f"[Child Database: {block_data.get('title', 'Untitled')}]"
        elif block_type == "table":
            return "[Table]"
        elif block_type == "image":
            caption = block_data.get("caption", [])
            if caption:
                return f"[Image: {self._extract_text_from_rich_text(caption)}]"
            return "[Image]"
        
        return ""
    
    def _extract_text_from_rich_text(self, rich_text: List[Dict]) -> str:
        """Extract text from Notion rich text array."""
        texts = []
        for text_obj in rich_text:
            if text_obj.get("type") == "text":
                texts.append(text_obj.get("text", {}).get("content", ""))
        return " ".join(texts)