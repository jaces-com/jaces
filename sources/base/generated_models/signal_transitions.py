"""Generated from Drizzle schema - DO NOT EDIT MANUALLY"""
from datetime import datetime
from sources.base.models.base import Base
from sqlalchemy import Column, String, Boolean, Integer, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from typing import Dict, Any, Optional
from uuid import uuid4


class SignalTransitions(Base):
    """Auto-generated from Drizzle schema."""
    
    __tablename__ = "signal_transitions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    source_name = Column(String, nullable=False)
    signal_name = Column(String, nullable=False)
    transition_time = Column(DateTime, nullable=False)
    transition_type = Column(String, nullable=False)
    change_magnitude = Column(Float)
    change_direction = Column(String)
    before_mean = Column(Float)
    before_std = Column(Float)
    after_mean = Column(Float)
    after_std = Column(Float)
    confidence = Column(Float, nullable=False)
    detection_method = Column(String, nullable=False)
    transition_metadata = Column(JSON)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
