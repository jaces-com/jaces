"""Generated from Drizzle schema - DO NOT EDIT MANUALLY"""
from datetime import datetime
from sources.base.models.base import Base
from sqlalchemy import Column, String, Boolean, Integer, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from typing import Dict, Any, Optional
from uuid import uuid4


class Events(Base):
    """Auto-generated from Drizzle schema."""
    
    __tablename__ = "events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    date = Column(JSON, nullable=False)
    cluster_id = Column(Integer, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    core_density = Column(Float, nullable=False)
    cluster_size = Column(Integer, nullable=False)
    persistence = Column(Float)
    transition_ids = Column(ARRAY(UUID(as_uuid=True)))
    signal_contributions = Column(JSON)
    event_metadata = Column(JSON)
    event_type = Column(String, default='activity')
    created_at = Column(DateTime, nullable=False, default=datetime.now)
