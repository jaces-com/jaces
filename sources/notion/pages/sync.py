"""Notion pages sync logic with three sync modes."""

import json
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from uuid import uuid4

from .client import NotionClient
from sources.base.storage.minio import store_raw_data
from sources.base.storage.database import async_session
from sources.base.generated_models.signal_configs import SignalConfigs


class NotionPagesSync:
    """Handles sync of Notion pages with three modes: initial, incremental, full_refresh."""
    
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # seconds
    requires_credentials = True  # This source requires OAuth credentials
    
    # Sync time windows
    INCREMENTAL_LOOKBACK_MINUTES = 35  # Slight overlap with 30-min schedule
    
    def __init__(self, signal: SignalConfigs, access_token: str, token_refresher=None):
        """
        Initialize Notion sync.
        
        Args:
            signal: Signal configuration from database
            access_token: Notion API access token
            token_refresher: Optional function to refresh token (not used for Notion)
        """
        self.signal = signal
        self.client = NotionClient(access_token)
        self.source_name = "notion"
        self.stream_name = "notion_pages"
    
    async def run(self, sync_mode: str = "incremental") -> Dict[str, Any]:
        """
        Execute sync for Notion pages.
        
        Args:
            sync_mode: One of 'initial', 'incremental', or 'full_refresh'
        
        Returns:
            Dict with sync statistics
        """
        stats = {
            "sync_mode": sync_mode,
            "pages_processed": 0,
            "databases_processed": 0,
            "errors": [],
            "sync_token": None,
            "started_at": datetime.utcnow().isoformat()
        }
        
        try:
            if sync_mode == "initial":
                await self._initial_sync(stats)
            elif sync_mode == "incremental":
                await self._incremental_sync(stats)
            elif sync_mode == "full_refresh":
                await self._full_refresh_sync(stats)
            else:
                raise ValueError(f"Invalid sync mode: {sync_mode}")
            
            stats["completed_at"] = datetime.utcnow().isoformat()
            stats["status"] = "success"
            
        except Exception as e:
            stats["status"] = "error"
            stats["error"] = str(e)
            stats["errors"].append({
                "timestamp": datetime.utcnow().isoformat(),
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
    
    async def _incremental_sync(self, stats: Dict[str, Any]) -> None:
        """
        Incremental sync: Fetch only changed pages since last sync.
        
        Args:
            stats: Stats dict to update
        """
        print(f"Starting incremental sync for Notion pages...")
        
        # Get last sync time from signal config
        last_sync = self.signal.last_successful_ingestion_at
        
        if last_sync:
            # Add some overlap to avoid missing updates
            since = last_sync - timedelta(minutes=self.INCREMENTAL_LOOKBACK_MINUTES)
        else:
            # No previous sync, fallback to last 90 days
            since = datetime.utcnow() - timedelta(days=90)
        
        print(f"Fetching pages modified since {since.isoformat()}")
        
        # Fetch pages modified since last sync
        cursor = self.signal.sync_token  # Get stored cursor if available
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
                last_edited = datetime.fromisoformat(
                    page.get("last_edited_time", "").replace("Z", "+00:00")
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
                "stream_name": self.stream_name,
                "source_name": self.source_name,
                "data": page,
                "metadata": {
                    "page_id": page_id,
                    "page_type": page_type,
                    "content_hash": content_hash,
                    "synced_at": datetime.utcnow().isoformat()
                }
            }
            
            # Store raw data in MinIO
            await store_raw_data(
                stream_name=self.stream_name,
                data=stream_data,
                timestamp=datetime.utcnow()
            )
            
        except Exception as e:
            error_msg = f"Error processing page {page.get('id', 'unknown')}: {e}"
            print(error_msg)
            stats["errors"].append({
                "page_id": page.get("id"),
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
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