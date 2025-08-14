"""Generated from Drizzle schema - DO NOT EDIT MANUALLY"""
from datetime import datetime
from sources.base.models.base import Base
from sqlalchemy import Column, String, Boolean, Integer, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from typing import Dict, Any, Optional
from uuid import uuid4


class Signals(Base):
    """Auto-generated from Drizzle schema."""
    
    __tablename__ = "signals"
    
    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    signal_id = Column(UUID(as_uuid=True), ForeignKey('signalConfigs.id', ondelete='CASCADE'), nullable=False, index=True)
    source_name = Column(String, ForeignKey('sourceConfigs.name', ondelete='RESTRICT'), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False)
    confidence = Column(Float, nullable=False)
    signal_name = Column(String, nullable=False)
    signal_value = Column(String, nullable=False)
    coordinates = Column(JSON)
    idempotency_key = Column(String, nullable=False)
    source_metadata = Column(JSON)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)
