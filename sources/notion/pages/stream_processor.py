"""Stream processor for Notion pages - converts to semantic data."""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import uuid4
from sqlalchemy import text


class NotionPagesStreamProcessor:
    """Process Notion pages stream data into semantics."""
    
    def __init__(self):
        self.source_name = "notion"
        self.stream_name = "notion_pages"
    
    def process(
        self,
        stream_data: Dict[str, Any],
        db
    ) -> Dict[str, Any]:
        """
        Process Notion stream data into semantic records.
        
        Args:
            stream_data: Raw stream data from MinIO
            db: Database session
            
        Returns:
            Processing result with semantic counts
        """
        # Extract page data
        page_data = stream_data.get('data', {})
        metadata = stream_data.get('metadata', {})
        
        # Track processing results
        semantics_created = 0
        semantics_updated = 0
        errors = []
        
        try:
            # Process the page into semantic record
            semantic_record = self._create_semantic_record(page_data, metadata)
            
            if semantic_record:
                # Check if this semantic already exists
                existing = db.execute(
                    text("""
                        SELECT id, content_hash, version 
                        FROM semantics 
                        WHERE source_name = :source_name 
                        AND semantic_id = :semantic_id 
                        AND is_latest = true
                    """),
                    {
                        "source_name": self.source_name,
                        "semantic_id": semantic_record["semantic_id"]
                    }
                ).fetchone()
                
                if existing:
                    # Check if content has changed
                    if existing.content_hash != semantic_record["content_hash"]:
                        # Mark old version as not latest
                        db.execute(
                            text("""
                                UPDATE semantics 
                                SET is_latest = false, updated_at = :updated_at
                                WHERE id = :id
                            """),
                            {
                                "id": existing.id,
                                "updated_at": datetime.utcnow()
                            }
                        )
                        
                        # Insert new version
                        semantic_record["version"] = existing.version + 1
                        self._insert_semantic(db, semantic_record)
                        semantics_updated += 1
                    # else: content unchanged, skip
                else:
                    # New semantic, insert it
                    self._insert_semantic(db, semantic_record)
                    semantics_created += 1
                
                # Commit the transaction
                db.commit()
            
        except Exception as e:
            db.rollback()
            error_msg = f"Error processing page {page_data.get('id', 'unknown')}: {e}"
            errors.append(error_msg)
            print(error_msg)
        
        return {
            "status": "success" if not errors else "partial",
            "stream_name": self.stream_name,
            "semantics_created": semantics_created,
            "semantics_updated": semantics_updated,
            "errors": errors,
            "processed_at": datetime.utcnow().isoformat()
        }
    
    def _create_semantic_record(
        self,
        page_data: Dict[str, Any],
        metadata: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Create a semantic record from Notion page data.
        
        Args:
            page_data: Raw Notion page data
            metadata: Processing metadata
        
        Returns:
            Semantic record dict or None if invalid
        """
        if not page_data.get("id"):
            return None
        
        # Extract basic info
        page_id = page_data.get("id")
        page_type = page_data.get("object", "page")  # 'page' or 'database'
        
        # Extract title from properties
        title = self._extract_title(page_data)
        
        # Get text content (extracted during sync)
        content_text = page_data.get("extracted_text", "")
        
        # Create summary (first 500 chars of content)
        summary = content_text[:500] if content_text else ""
        
        # Extract metadata
        created_by = page_data.get("created_by", {})
        last_edited_by = page_data.get("last_edited_by", {})
        parent = page_data.get("parent", {})
        
        # Build semantic metadata
        semantic_metadata = {
            "url": page_data.get("url"),
            "archived": page_data.get("archived", False),
            "properties": page_data.get("properties", {}),
            "cover": page_data.get("cover"),
            "icon": page_data.get("icon"),
            "created_by": created_by,
            "last_edited_by": last_edited_by,
            "parent": parent
        }
        
        # Clean up None values
        semantic_metadata = {k: v for k, v in semantic_metadata.items() if v is not None}
        
        # Build the semantic record
        semantic_record = {
            "id": str(uuid4()),
            "source_name": self.source_name,
            "stream_name": self.stream_name,
            "semantic_id": page_id,
            "semantic_type": page_type,
            "title": title,
            "summary": summary,
            "minio_path": f"streams/{self.stream_name}/{datetime.utcnow().strftime('%Y/%m/%d')}/{page_id}.json",
            "content_hash": metadata.get("content_hash", ""),
            "version": 1,
            "is_latest": True,
            "author_id": created_by.get("id") if created_by else None,
            "author_name": self._get_user_name(created_by),
            "parent_id": self._extract_parent_id(parent),
            "source_created_at": self._parse_timestamp(page_data.get("created_time")),
            "source_updated_at": self._parse_timestamp(page_data.get("last_edited_time")),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "metadata": json.dumps(semantic_metadata)
        }
        
        # Store full content in MinIO (reference path already in minio_path)
        # The actual storage happens in the sync process
        
        return semantic_record
    
    def _insert_semantic(self, db, semantic_record: Dict[str, Any]) -> None:
        """
        Insert a semantic record into the database.
        
        Args:
            db: Database session
            semantic_record: Semantic record to insert
        """
        db.execute(
            text("""
                INSERT INTO semantics 
                (id, source_name, stream_name, semantic_id, semantic_type,
                 title, summary, minio_path, content_hash, version, is_latest,
                 author_id, author_name, parent_id,
                 source_created_at, source_updated_at,
                 created_at, updated_at, metadata)
                VALUES 
                (:id, :source_name, :stream_name, :semantic_id, :semantic_type,
                 :title, :summary, :minio_path, :content_hash, :version, :is_latest,
                 :author_id, :author_name, :parent_id,
                 :source_created_at, :source_updated_at,
                 :created_at, :updated_at, :metadata)
            """),
            semantic_record
        )
    
    def _extract_title(self, page_data: Dict[str, Any]) -> str:
        """
        Extract title from Notion page properties.
        
        Args:
            page_data: Notion page data
        
        Returns:
            Page title or 'Untitled'
        """
        properties = page_data.get("properties", {})
        
        # Look for common title fields
        for prop_name in ["title", "Title", "Name", "name"]:
            if prop_name in properties:
                prop = properties[prop_name]
                if prop.get("type") == "title" and prop.get("title"):
                    # Extract text from title array
                    title_parts = []
                    for text_obj in prop["title"]:
                        if text_obj.get("type") == "text":
                            title_parts.append(text_obj.get("text", {}).get("content", ""))
                    if title_parts:
                        return " ".join(title_parts)
        
        # Fallback for databases
        if page_data.get("object") == "database":
            db_title = page_data.get("title", [])
            if db_title:
                title_parts = []
                for text_obj in db_title:
                    if text_obj.get("type") == "text":
                        title_parts.append(text_obj.get("text", {}).get("content", ""))
                if title_parts:
                    return " ".join(title_parts)
        
        return "Untitled"
    
    def _get_user_name(self, user_obj: Optional[Dict]) -> Optional[str]:
        """Extract user name from Notion user object."""
        if not user_obj:
            return None
        
        # Try to get name, fallback to email
        return user_obj.get("name") or user_obj.get("person", {}).get("email")
    
    def _extract_parent_id(self, parent: Dict[str, Any]) -> Optional[str]:
        """Extract parent ID from Notion parent object."""
        if not parent:
            return None
        
        parent_type = parent.get("type")
        if parent_type == "page_id":
            return parent.get("page_id")
        elif parent_type == "database_id":
            return parent.get("database_id")
        elif parent_type == "workspace":
            return "workspace"
        
        return None
    
    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """Parse Notion timestamp to datetime object."""
        if not timestamp_str:
            return None
        
        try:
            # Remove Z and add +00:00 for proper timezone handling
            return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None