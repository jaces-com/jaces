"""Generated from Drizzle schema - DO NOT EDIT MANUALLY"""
from datetime import datetime
from sources.base.models.base import Base
from sqlalchemy import Column, String, Boolean, Integer, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from typing import Dict, Any, Optional
from uuid import uuid4


class SignalConfigs(Base):
    """Auto-generated from Drizzle schema."""
    
    __tablename__ = "signal_configs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, nullable=False)
    signal_name = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    unit_ucum = Column(String, nullable=False)
    computation = Column(JSON, nullable=False)
    fidelity_score = Column(Float, nullable=False)
    macro_weight = Column(Float, default=0.5)
    min_transition_gap = Column(Float, default=300)
    source_name = Column(String, ForeignKey('sourceConfigs.name', ondelete='RESTRICT'), nullable=False, index=True)
    stream_name = Column(String, nullable=False)
    description = Column(String)
    settings = Column(JSON)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now)
