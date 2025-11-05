"""Authentication utilities for the dashboard."""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .config import get_config


security = HTTPBasic()


def require_user(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    settings = get_config()
    valid_user = secrets.compare_digest(credentials.username or "", settings.admin_user)
    valid_password = secrets.compare_digest(credentials.password or "", settings.admin_password)
    if not (valid_user and valid_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return settings.admin_user

