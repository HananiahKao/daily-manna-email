"""Application configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    admin_user: str
    admin_password: str
    schedule_file: Path | None
    timezone: str = "Asia/Taipei"
    oauth_encryption_key: str | None = None


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    admin_password = os.getenv("ADMIN_DASHBOARD_PASSWORD")
    if not admin_password:
        raise RuntimeError("ADMIN_DASHBOARD_PASSWORD must be set for the dashboard")
    admin_user = os.getenv("ADMIN_DASHBOARD_USER", "admin")
    schedule_file_raw = os.getenv("SCHEDULE_FILE")
    schedule_file = Path(schedule_file_raw).expanduser() if schedule_file_raw else None
    timezone = os.getenv("ADMIN_DASHBOARD_TIMEZONE", "Asia/Taipei")
    oauth_encryption_key = os.getenv("OAUTH_ENCRYPTION_KEY")
    return AppConfig(
        admin_user=admin_user,
        admin_password=admin_password,
        schedule_file=schedule_file,
        timezone=timezone,
        oauth_encryption_key=oauth_encryption_key,
    )
