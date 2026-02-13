#!/usr/bin/env python3
"""
Database configuration and utilities for subscriber management.

Supports SQLite (development) and PostgreSQL (production) databases.
"""

import os
from pathlib import Path
from typing import Optional

from .models import init_database


def get_database_url() -> str:
    """Get database URL based on environment configuration."""
    database_mode = os.getenv("DATABASE_MODE", "sqlite").lower().strip()

    if database_mode == "postgres" or database_mode == "postgresql":
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError(
                "DATABASE_URL environment variable is required when DATABASE_MODE=postgres"
            )
        # Convert standard PostgreSQL URL to psycopg2cffi format if needed
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+psycopg2cffi://", 1)
        return database_url
    elif database_mode == "sqlite":
        # Default SQLite database location
        db_path = os.getenv("DATABASE_PATH", "state/subscribers.db")
        db_file = Path(db_path)

        # Ensure directory exists
        db_file.parent.mkdir(parents=True, exist_ok=True)

        # Convert to absolute path for SQLite
        return f"sqlite:///{db_file.resolve()}"
    else:
        raise ValueError(f"Unsupported DATABASE_MODE: {database_mode}. Use 'sqlite' or 'postgres'")


def initialize_database() -> None:
    """Initialize the database and create tables if needed."""
    database_url = get_database_url()
    init_database(database_url)


def get_database_mode() -> str:
    """Get the current database mode."""
    return os.getenv("DATABASE_MODE", "sqlite").lower().strip()


def is_production_database() -> bool:
    """Check if we're using a production database (PostgreSQL)."""
    return get_database_mode() in ("postgres", "postgresql")
