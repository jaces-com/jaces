"""Notion pages sync logic with three sync modes."""

import json
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List, Tuple
from uuid import uuid4

from .client import NotionClient
from sources.base.storage.minio import store_raw_data
from sources.base.storage.database import AsyncSessionLocal
from sources.base.interfaces.sync import BaseSync


class NotionPagesSync(BaseSync):
    """Handles sync of Notion pages with three modes: initial, incremental, full_refresh."""
    
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # seconds
    requires_credentials = True  # This source requires OAuth credentials
    
    # Sync time windows
    INCREMENTAL_LOOKBACK_MINUTES = 35  # Slight overlap with 30-min schedule
    
    def __init__(self, stream, access_token: str, token_refresher=None):
        """
        Initialize Notion sync.
        
        Args:
            stream: Stream configuration from database
            access_token: Notion API access token
            token_refresher: Optional function to refresh token (not used for Notion)
        """
        super().__init__(stream, access_token, token_refresher)
        self.client = NotionClient(access_token)
        # For backward compatibility, allow both 'stream' and 'signal' attribute names
        self.signal = stream
        # Store the source_id (connection_id) from oauth_credentials if available
        # Convert UUID to string if necessary
        connection_id = getattr(stream, '_oauth_credentials', {}).get('source_id') if hasattr(stream, '_oauth_credentials') else None
        self.connection_id = str(connection_id) if connection_id else None
    
    def get_full_sync_range(self) -> Tuple[datetime, datetime]:
        """
        Define the date range for a full initial sync.
        For Notion, this is 2 years past (no future dates for pages).
        """
        now = datetime.now(timezone.utc)
        return (
            now - timedelta(days=365 * 2),  # 2 years past
            now  # Current time (pages don't have future dates)
        )
    
    def get_incremental_sync_range(self) -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        Define the date range for incremental syncs.
        Returns None, None if using cursors instead of date ranges.
        """
        # Notion can use cursors for incremental sync
        if hasattr(self.stream, 'sync_token') and self.stream.sync_token:
            return (None, None)  # Using cursor
        
        # Fallback to date-based sync
        now = datetime.now(timezone.utc)
        last_sync = self.stream.last_successful_ingestion_at if hasattr(self.stream, 'last_successful_ingestion_at') else None
        
        if last_sync:
            # Use last sync time with overlap
            return (last_sync - timedelta(minutes=self.INCREMENTAL_LOOKBACK_MINUTES), now)
        else:
            # Fallback: 90 days past
            return (now - timedelta(days=90), now)
    
    async def fetch_data(self, start_date: Optional[datetime], end_date: Optional[datetime]) -> Dict[str, Any]:
        """
        Fetch data for the given date range.
        If dates are None, uses cursors for incremental sync.
        """
        # Determine sync mode based on whether this is initial sync
        if self.is_initial_sync():
            sync_mode = "initial"
        else:
            sync_mode = "incremental"
        
        return await self.run(sync_mode=sync_mode, start_date=start_date, end_date=end_date)
    
    async def run(self, sync_mode: str = "incremental", start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Execute sync for Notion pages.
        
        Args:
            sync_mode: One of 'initial', 'incremental', or 'full_refresh'
            start_date: Optional start date for sync
            end_date: Optional end date for sync
        
        Returns:
            Dict with sync statistics
        """
        stats = {
            "sync_mode": sync_mode,
            "pages_processed": 0,
            "databases_processed": 0,
            "errors": [],
            "sync_token": None,
            "started_at": datetime.now(timezone.utc).isoformat()
        }
        
        try:
            if sync_mode == "initial":
                await self._initial_sync(stats)
            elif sync_mode == "incremental":
                await self._incremental_sync(stats, start_date)
            elif sync_mode == "full_refresh":
                await self._full_refresh_sync(stats)
            else:
                raise ValueError(f"Invalid sync mode: {sync_mode}")
            
            stats["completed_at"] = datetime.now(timezone.utc).isoformat()
            stats["status"] = "success"
            
        except Exception as e:
            stats["status"] = "error"
            stats["error"] = str(e)
            stats["errors"].append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            })
        
        return stats
    
    async def _initial_sync(self, stats: Dict[str, Any]) -> None:
        """
        Initial sync: Fetch all accessible pages in workspace.
        
        Args:
            stats: Stats dict to update
        """
        print(f"Starting initial sync for Notion pages...")
        
        # Fetch all pages
        all_pages = await self.client.get_all_pages(
            progress_callback=lambda total, batch: print(f"Fetched {total} pages...")
        )
        
        # Process and store pages
        for page in all_pages:
            await self._process_and_store_page(page, stats)
        
        print(f"Initial sync complete: {stats['pages_processed']} pages, {stats['databases_processed']} databases")
    
    async def _incremental_sync(self, stats: Dict[str, Any], start_date: Optional[datetime] = None) -> None:
        """
        Incremental sync: Fetch only changed pages since last sync.
        
        Args:
            stats: Stats dict to update
            start_date: Optional start date override
        """
        print(f"Starting incremental sync for Notion pages...")
        
        # Use date range from parent class logic or parameter
        if start_date:
            since = start_date
        else:
            date_range = self.get_sync_date_range()
            since = date_range[0] if date_range[0] else datetime.now(timezone.utc) - timedelta(days=90)
        
        print(f"Fetching pages modified since {since.isoformat()}")
        
        # Fetch pages modified since last sync
        cursor = self.stream.sync_token if hasattr(self.stream, 'sync_token') else None  # Get stored cursor if available
        has_more = True
        
        while has_more:
            result = await self.client.search_pages(
                cursor=cursor,
                sort_by="last_edited_time",
                sort_direction="descending"
            )
            
            pages = result.get("results", [])
            
            # Process pages until we hit our time boundary
            for page in pages:
                last_edited_str = page.get("last_edited_time", "")
                if last_edited_str:
                    last_edited = datetime.fromisoformat(
                        last_edited_str.replace("Z", "+00:00")
                    )
                    
                    if last_edited < since:
                        has_more = False
                        break
                
                await self._process_and_store_page(page, stats)
            
            # Check for more pages
            if not has_more or not result.get("has_more"):
                break
            
            cursor = result.get("next_cursor")
            stats["sync_token"] = cursor  # Store for next sync
        
        print(f"Incremental sync complete: {stats['pages_processed']} pages, {stats['databases_processed']} databases")
    
    async def _full_refresh_sync(self, stats: Dict[str, Any]) -> None:
        """
        Full refresh: Re-fetch all pages and compare for changes.
        
        Args:
            stats: Stats dict to update
        """
        print(f"Starting full refresh sync for Notion pages...")
        
        # Fetch all pages
        all_pages = await self.client.get_all_pages(
            progress_callback=lambda total, batch: print(f"Fetched {total} pages...")
        )
        
        # Process pages with change detection
        for page in all_pages:
            # Calculate content hash for comparison
            content_hash = self._calculate_content_hash(page)
            
            # Check if content has changed (would query semantics table here)
            # For now, process all pages
            await self._process_and_store_page(page, stats, content_hash=content_hash)
        
        print(f"Full refresh complete: {stats['pages_processed']} pages, {stats['databases_processed']} databases")
    
    async def _process_and_store_page(
        self,
        page: Dict[str, Any],
        stats: Dict[str, Any],
        content_hash: Optional[str] = None
    ) -> None:
        """
        Process a single page and store in MinIO.
        
        Args:
            page: Notion page object
            stats: Stats dict to update
            content_hash: Optional pre-calculated content hash
        """
        try:
            page_id = page.get("id")
            page_type = page.get("object")  # 'page' or 'database'
            
            # Fetch full content for pages
            if page_type == "page":
                try:
                    # Get page content blocks
                    content_text = await self.client.extract_page_text(page_id)
                    page["extracted_text"] = content_text
                except Exception as e:
                    print(f"Error extracting text for page {page_id}: {e}")
                    page["extracted_text"] = ""
                
                stats["pages_processed"] += 1
            else:
                stats["databases_processed"] += 1
            
            # Calculate content hash if not provided
            if not content_hash:
                content_hash = self._calculate_content_hash(page)
            
            # Prepare data for storage
            stream_data = {
                "stream_name": self.stream.stream_name if hasattr(self.stream, 'stream_name') else 'notion_pages',
                "source_name": self.stream.source_name if hasattr(self.stream, 'source_name') else 'notion',
                "data": page,
                "metadata": {
                    "page_id": page_id,
                    "page_type": page_type,
                    "content_hash": content_hash,
                    "synced_at": datetime.now(timezone.utc).isoformat()
                }
            }
            
            # Store raw data in MinIO
            if not self.connection_id:
                print(f"Warning: No connection_id available for page {page_id}, skipping storage")
                return
                
            await store_raw_data(
                stream_name=self.stream.stream_name if hasattr(self.stream, 'stream_name') else 'notion_pages',
                connection_id=self.connection_id,
                data=stream_data,
                timestamp=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            error_msg = f"Error processing page {page.get('id', 'unknown')}: {e}"
            print(error_msg)
            stats["errors"].append({
                "page_id": page.get("id"),
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
    
    def _calculate_content_hash(self, page: Dict[str, Any]) -> str:
        """
        Calculate a hash of page content for deduplication.
        
        Args:
            page: Notion page object
        
        Returns:
            SHA256 hash of content
        """
        import hashlib
        
        # Include key fields in hash calculation
        content_parts = [
            page.get("id", ""),
            page.get("last_edited_time", ""),
            json.dumps(page.get("properties", {}), sort_keys=True),
            page.get("extracted_text", "")
        ]
        
        content_str = "|".join(str(p) for p in content_parts)
        return hashlib.sha256(content_str.encode()).hexdigest()
    
    async def test_connection(self) -> bool:
        """
        Test if the Notion connection is working.
        
        Returns:
            True if connection is successful
        """
        try:
            # Try to fetch a small number of pages
            result = await self.client.search_pages(page_size=1)
            return "results" in result
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False