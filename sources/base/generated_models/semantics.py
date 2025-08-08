"""Generated from Drizzle schema - DO NOT EDIT MANUALLY"""
from datetime import datetime
from sources.base.models.base import Base
from sqlalchemy import Column, String, Boolean, Integer, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from typing import Dict, Any, Optional
from uuid import uuid4


class Semantics(Base):
    """Auto-generated from Drizzle schema."""
    
    __tablename__ = "semantics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    source_name = Column(String, ForeignKey('sourceConfigs.name', ondelete='RESTRICT'), nullable=False, index=True)
    stream_name = Column(String, nullable=False)
    semantic_id = Column(String, nullable=False)
    semantic_type = Column(String, nullable=False)
    title = Column(String)
    summary = Column(String)
    minio_path = Column(String, nullable=False)
    content_hash = Column(String)
    version = Column(Integer, default=1)
    is_latest = Column(Boolean, default=True)
    author_id = Column(String)
    author_name = Column(String)
    parent_id = Column(String)
    source_created_at = Column(DateTime)
    source_updated_at = Column(DateTime)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)
    extra_metadata = Column(JSON)
