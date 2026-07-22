#!/usr/bin/env python3
"""
Database models for the daily-manna-email application.

Uses SQLAlchemy ORM with support for SQLite (development) and PostgreSQL (production).
"""

from datetime import datetime
from typing import Optional, Union

from sqlalchemy import Boolean, Column, DateTime, Integer, String, create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class Subscriber(Base):
    """Subscriber model for managing email recipients per content source."""

    __tablename__ = "subscribers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email_encrypted = Column(String, nullable=False, index=True)  # AES-256-GCM encrypted
    content_source = Column(String, nullable=False, index=True)   # 'ezoe' or 'wix'
    subscribed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    active = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        {"sqlite_autoincrement": True},  # Ensure autoincrement works with SQLite
    )

    def __repr__(self) -> str:
        return f"<Subscriber(id={self.id}, content_source='{self.content_source}', active={self.active})>"

    @classmethod
    def create_table_if_not_exists(cls, engine):
        """Create the subscribers table if it doesn't exist."""
        Base.metadata.create_all(engine, tables=[cls.__table__])  # type: ignore


# Database session management
SessionLocal: Optional[sessionmaker] = None


def init_database(database_url: str) -> None:
    """Initialize the database engine and session factory."""
    global SessionLocal

    # Configure engine based on database type
    if database_url.startswith("sqlite"):
        # SQLite specific configurations
        connect_args = {"check_same_thread": False}
        engine = create_engine(
            database_url,
            connect_args=connect_args,
            pool_pre_ping=True,
        )
    else:
        # PostgreSQL and other databases
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            pool_recycle=300,
        )

    # Create tables - Handle case where tables already exist
    import logging
    logger = logging.getLogger(__name__)
    try:
        Base.metadata.create_all(bind=engine)  # type: ignore
    except Exception as e:
        # Log the error but continue initialization
        logger.warning("Table creation skipped: %s", str(e))

    # Create session factory
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db_session():
    """Get a database session. Must be used within a context manager."""
    if SessionLocal is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    return SessionLocal()
