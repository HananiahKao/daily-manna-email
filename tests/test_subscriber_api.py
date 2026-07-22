"""Tests for subscriber management API endpoints."""
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import get_config


@pytest.fixture
def client():
    """Create test client."""
    get_config.cache_clear()
    app = create_app()
    return TestClient(app)


def test_subscriber_endpoints_exist(client):
    """Test that all subscriber management endpoints exist."""
    endpoints = [
        ("POST", "/api/subscribers"),
        ("GET", "/api/subscribers"),
        ("PATCH", "/api/subscribers/1"),
        ("DELETE", "/api/subscribers/1"),
    ]

    for method, path in endpoints:
        if method == "POST":
            response = client.post(path, json={})
        elif method == "GET":
            response = client.get(path)
        elif method == "PATCH":
            response = client.patch(path, json={})
        elif method == "DELETE":
            response = client.delete(path)

        # Endpoint should exist (not 404)
        assert response.status_code != 404, f"{method} {path} returned 404"
