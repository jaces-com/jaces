"""Generated from Drizzle schema - DO NOT EDIT MANUALLY"""
from datetime import datetime
from sources.base.models.base import Base
from sqlalchemy import Column, String, Boolean, Integer, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from typing import Dict, Any, Optional
from uuid import uuid4


class EpisodicSignals(Base):
    """Auto-generated from Drizzle schema."""
    
    __tablename__ = "episodic_signals"
    
    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    signal_id = Column(UUID(as_uuid=True), ForeignKey('signals.id', ondelete='CASCADE'), nullable=False, index=True)
    source_name = Column(String, ForeignKey('sources.name', ondelete='RESTRICT'), nullable=False, index=True)
    start_timestamp = Column(DateTime, nullable=False)
    end_timestamp = Column(DateTime, nullable=False)
    summary = Column(String)
    what_ids = Column(ARRAY(UUID(as_uuid=True)))
    where_ids = Column(ARRAY(UUID(as_uuid=True)))
    who_ids = Column(ARRAY(UUID(as_uuid=True)))
    when_ids = Column(ARRAY(UUID(as_uuid=True)))
    how_ids = Column(ARRAY(UUID(as_uuid=True)))
    why_ids = Column(ARRAY(UUID(as_uuid=True)))
    target_ids = Column(ARRAY(UUID(as_uuid=True)))
    what_text = Column(ARRAY(Text))
    where_text = Column(ARRAY(Text))
    who_text = Column(ARRAY(Text))
    when_text = Column(ARRAY(Text))
    how_text = Column(ARRAY(Text))
    why_text = Column(ARRAY(Text))
    target_text = Column(ARRAY(Text))
    confidence = Column(Float, nullable=False)
    source_metadata = Column(JSON)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)
