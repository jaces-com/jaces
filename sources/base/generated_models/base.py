"""Shared SQLAlchemy Base for all models."""
from sqlalchemy.ext.declarative import declarative_base

# Single shared Base instance for all models
Base = declarative_base()