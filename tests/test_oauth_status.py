#!/usr/bin/env python3
"""Test script for the new tokeninfo-based oauth_status endpoint."""

import base64
import json
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from app.main import create_app

def _auth_header(user: str = "admin", password: str = "secret") -> dict[str, str]:
    """Generate HTTP Basic auth header for testing."""
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("utf-8")
    return {"Authorization": f"Basic {token}"}

def test_oauth_status_no_token_file():
    """Test oauth_status when token.json doesn't exist."""
    # Set up test environment
    os.environ["ADMIN_DASHBOARD_USER"] = "admin"
    os.environ["ADMIN_DASHBOARD_PASSWORD"] = "secret"

    # Temporarily move existing token.json if it exists
    token_path = PROJECT_ROOT / "token.json"
    backup_path = PROJECT_ROOT / "token.json.backup"
    token_existed = token_path.exists()

    if token_existed:
        token_path.rename(backup_path)

    try:
        app = create_app()
        client = TestClient(app)

        # Make request with auth
        response = client.get("/oauth/status", headers=_auth_header())

        assert response.status_code == 200
        data = response.json()
        assert data["authorized"] == False
        assert data["status"] == "unauthorized"
        assert data["scope_status"] == "none"
        print("✓ Test passed: No token file")
    finally:
        # Restore original token.json if it existed
        if token_existed and backup_path.exists():
            backup_path.rename(token_path)

def test_oauth_status_invalid_token():
    """Test oauth_status with invalid token (simulated tokeninfo response)."""
    # Set up test environment
    os.environ["ADMIN_DASHBOARD_USER"] = "admin"
    os.environ["ADMIN_DASHBOARD_PASSWORD"] = "secret"

    app = create_app()

    # Create a fake token.json file
    fake_token_path = PROJECT_ROOT / "token.json"
    fake_creds = {
        "token": "invalid_token",
        "refresh_token": "refresh_token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "client_id",
        "client_secret": "client_secret",
        "scopes": ["https://www.googleapis.com/auth/gmail.send"]
    }

    try:
        with open(fake_token_path, 'w') as f:
            json.dump(fake_creds, f)

        with patch('requests.get') as mock_get:
            # Mock tokeninfo response for invalid token
            mock_response = Mock()
            mock_response.status_code = 400
            mock_response.json.return_value = {"error": "invalid_token"}
            mock_get.return_value = mock_response

            client = TestClient(app)
            response = client.get("/oauth/status", headers=_auth_header())

            assert response.status_code == 200
            data = response.json()
            assert data["authorized"] == False
            assert data["status"] == "revoked"
            assert data["scope_status"] == "none"
            print("✓ Test passed: Invalid token detection")

    finally:
        # Clean up
        if fake_token_path.exists():
            fake_token_path.unlink()

def test_oauth_status_valid_token():
    """Test oauth_status with valid token (simulated tokeninfo response)."""
    # Set up test environment
    os.environ["ADMIN_DASHBOARD_USER"] = "admin"
    os.environ["ADMIN_DASHBOARD_PASSWORD"] = "secret"

    app = create_app()

    # Create a fake token.json file
    fake_token_path = PROJECT_ROOT / "token.json"
    fake_creds = {
        "token": "valid_token",
        "refresh_token": "refresh_token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "client_id",
        "client_secret": "client_secret",
        "scopes": ["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.readonly"]
    }

    try:
        with open(fake_token_path, 'w') as f:
            json.dump(fake_creds, f)

        with patch('requests.get') as mock_get:
            # Mock tokeninfo response for valid token
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "scope": "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly",
                "expires_in": 3600,
                "aud": "client_id"
            }
            mock_get.return_value = mock_response

            client = TestClient(app)
            response = client.get("/oauth/status", headers=_auth_header())

            assert response.status_code == 200
            data = response.json()
            assert data["authorized"] == True
            assert data["status"] == "authorized"
            assert data["scope_status"] == "exact"
            print("✓ Test passed: Valid token with exact scopes")

    finally:
        # Clean up
        if fake_token_path.exists():
            fake_token_path.unlink()

def test_oauth_status_over_authorized():
    """Test oauth_status with over-authorized token (extra scopes)."""
    # Set up test environment
    os.environ["ADMIN_DASHBOARD_USER"] = "admin"
    os.environ["ADMIN_DASHBOARD_PASSWORD"] = "secret"

    app = create_app()

    # Create a fake token.json file
    fake_token_path = PROJECT_ROOT / "token.json"
    fake_creds = {
        "token": "valid_token",
        "refresh_token": "refresh_token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "client_id",
        "client_secret": "client_secret",
        "scopes": ["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.readonly"]
    }

    try:
        with open(fake_token_path, 'w') as f:
            json.dump(fake_creds, f)

        with patch('requests.get') as mock_get:
            # Mock tokeninfo response with EXTRA scopes (over-authorized)
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "scope": "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/gmail.compose",
                "expires_in": 3600,
                "aud": "client_id"
            }
            mock_get.return_value = mock_response

            client = TestClient(app)
            response = client.get("/oauth/status", headers=_auth_header())

            assert response.status_code == 200
            data = response.json()
            assert data["authorized"] == True
            assert data["status"] == "authorized"
            assert data["scope_status"] == "over-authorized"
            assert "extra_scopes" in data
            assert "extra_scopes_descriptions" in data
            assert len(data["extra_scopes_descriptions"]) == 2  # gmail.modify + gmail.compose
            print("✓ Test passed: Over-authorized token with user-friendly descriptions")

    finally:
        # Clean up
        if fake_token_path.exists():
            fake_token_path.unlink()

def test_oauth_status_under_authorized():
    """Test oauth_status with under-authorized token (missing scopes)."""
    # Set up test environment
    os.environ["ADMIN_DASHBOARD_USER"] = "admin"
    os.environ["ADMIN_DASHBOARD_PASSWORD"] = "secret"

    app = create_app()

    # Create a fake token.json file
    fake_token_path = PROJECT_ROOT / "token.json"
    fake_creds = {
        "token": "valid_token",
        "refresh_token": "refresh_token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "client_id",
        "client_secret": "client_secret",
        "scopes": ["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.readonly"]
    }

    try:
        with open(fake_token_path, 'w') as f:
            json.dump(fake_creds, f)

        with patch('requests.get') as mock_get:
            # Mock tokeninfo response with MISSING scopes (under-authorized)
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "scope": "https://www.googleapis.com/auth/gmail.send",  # Missing gmail.readonly
                "expires_in": 3600,
                "aud": "client_id"
            }
            mock_get.return_value = mock_response

            client = TestClient(app)
            response = client.get("/oauth/status", headers=_auth_header())

            assert response.status_code == 200
            data = response.json()
            assert data["authorized"] == False
            assert data["status"] == "insufficient"
            assert data["scope_status"] == "under-authorized"
            assert "missing_scopes" in data
            assert "missing_scopes_descriptions" in data
            assert len(data["missing_scopes_descriptions"]) == 1  # Missing gmail.readonly
            assert "View your email messages and settings" in data["missing_scopes_descriptions"]
            print("✓ Test passed: Under-authorized token with user-friendly descriptions")

    finally:
        # Clean up
        if fake_token_path.exists():
            fake_token_path.unlink()

if __name__ == "__main__":
    print("Testing oauth_status endpoint with tokeninfo validation...")
    test_oauth_status_no_token_file()
    test_oauth_status_invalid_token()
    test_oauth_status_valid_token()
    test_oauth_status_over_authorized()
    test_oauth_status_under_authorized()
    print("All tests passed! ✅")
