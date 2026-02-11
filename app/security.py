"""Authentication utilities for the dashboard."""

from __future__ import annotations

import secrets
from typing import Optional

from fastapi import Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .config import get_config


security = HTTPBasic()


def require_user(request: Request) -> str:
    """Check if user is authenticated via session or HTTP Basic auth (fallback)."""
    # Check session first
    user = request.session.get("user")
    if user:
        return user

    # Fallback to HTTP Basic for API compatibility
    try:
        # Extract credentials from Authorization header manually
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Basic "):
            import base64
            # Decode base64 credentials
            try:
                credentials = base64.b64decode(auth_header[len("Basic "):]).decode("utf-8")
                username, password = credentials.split(":", 1)
            except:
                pass
            else:
                settings = get_config()
                valid_user = secrets.compare_digest(username or "", settings.admin_user)
                valid_password = secrets.compare_digest(password or "", settings.admin_password)
                if valid_user and valid_password:
                    return settings.admin_user
    except:
        pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )


def authenticate_user(username: str, password: str) -> bool:
    """Verify user credentials."""
    settings = get_config()
    valid_user = secrets.compare_digest(username, settings.admin_user)
    valid_password = secrets.compare_digest(password, settings.admin_password)
    return valid_user and valid_password


def require_user_or_redirect(request: Request) -> str:
    """Check if user is authenticated, redirect to login on failure."""
    try:
        return require_user(request)
    except HTTPException as e:
        if e.status_code == 401:
            from urllib.parse import quote
            next_url = quote(str(request.url))
            raise HTTPException(
                status_code=302,
                detail="Authentication required",
                headers={"Location": f"/login-form?next={next_url}"}
            )
        raise


def login_required(request: Request) -> Optional[str]:
    """Check if user is authenticated, return username or None."""
    try:
        return require_user(request)
    except HTTPException:
        return None
