"""Generated from Drizzle schema - DO NOT EDIT MANUALLY"""
from datetime import datetime
from enum import Enum
from sources.base.models.base import Base
from sqlalchemy import Column, String, Boolean, Integer, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from typing import Dict, Any, Optional
from uuid import uuid4


class IngestionStatus(str, Enum):
    """ingestion_status enum values."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"



class IngestionRuns(Base):
    """Auto-generated from Drizzle schema."""
    
    __tablename__ = "ingestion_runs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    signal_id = Column(UUID(as_uuid=True), ForeignKey('signals.id', ondelete='CASCADE'), nullable=False, index=True)
    status = Column(PGEnum(IngestionStatus, name='ingestion_status'), nullable=False, default=IngestionStatus.PENDING)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    records_added = Column(Integer, nullable=False, default=0)
    minio_path = Column(String)
    error_message = Column(String)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)
