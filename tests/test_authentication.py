import datetime as dt
import pytest
from fastapi.testclient import TestClient

import schedule_manager as sm

from app.config import get_config
from app.main import create_app


@pytest.fixture(autouse=True)
def reset_config_cache():
    get_config.cache_clear()  # type: ignore[attr-defined]
    yield
    get_config.cache_clear()  # type: ignore[attr-defined]


@pytest.fixture
def auth_client(monkeypatch, tmp_path):
    """Test client with authentication setup."""
    schedule_path = tmp_path / "ezoe_schedule.json"
    monkeypatch.setenv("SCHEDULE_FILE", str(schedule_path))
    monkeypatch.setenv("ADMIN_DASHBOARD_PASSWORD", "test_password")
    monkeypatch.setenv("ADMIN_DASHBOARD_USER", "test_admin")

    base_date = dt.date(2025, 1, 6)  # Monday
    monkeypatch.setattr(sm, "taipei_today", lambda now=None: base_date)

    schedule = sm.Schedule(entries=[sm.ScheduleEntry(date=base_date, selector="2-10-1")])
    sm.save_schedule(schedule, schedule_path)

    app = create_app()
    client = TestClient(app)
    return client, schedule_path, base_date


class TestAuthentication:
    """Test authentication functionality including login/logout and session management."""

    def test_root_shows_home_page(self, auth_client):
        """Root route should show home page for any users."""
        client, *_ = auth_client
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 200
        assert "Daily Manna Email" in response.text
        assert "Admin Login" in response.text

    def test_authenticated_can_access_dashboard_directly(self, auth_client):
        """Authenticated users can access dashboard directly."""
        client, *_ = auth_client

        # First login to establish session
        login_response = client.post("/login", data={
            "username": "test_admin",
            "password": "test_password"
        }, follow_redirects=False)
        assert login_response.status_code == 302
        assert login_response.headers["location"] == "/dashboard"

        # Dashboard should be accessible
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "Calendar" in response.text

    def test_login_page_renders(self, auth_client):
        """Login page should render correctly."""
        client, *_ = auth_client
        response = client.get("/login-form")
        assert response.status_code == 200
        assert "Sign In" in response.text
        assert "username" in response.text
        assert "password" in response.text
        assert '<form method="post" action="/login"' in response.text

    def test_login_success_redirects_to_dashboard(self, auth_client):
        """Successful login should redirect to dashboard."""
        client, *_ = auth_client
        response = client.post("/login", data={
            "username": "test_admin",
            "password": "test_password"
        }, follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/dashboard"

    def test_login_failure_shows_error(self, auth_client):
        """Failed login should show error message."""
        client, *_ = auth_client
        response = client.post("/login", data={
            "username": "test_admin",
            "password": "wrong_password"
        })
        assert response.status_code == 401
        assert "Invalid credentials" in response.text

    def test_logout_clears_session(self, auth_client):
        """Logout should clear session and redirect to login."""
        client, *_ = auth_client

        # First login
        client.post("/login", data={
            "username": "test_admin",
            "password": "test_password"
        })

        # Then logout
        response = client.post("/logout", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/"

        # Root should still show home page
        root_response = client.get("/", follow_redirects=False)
        assert root_response.status_code == 200
        assert "Daily Manna Email" in root_response.text

    def test_dashboard_requires_authentication(self, auth_client):
        """Dashboard route should require authentication."""
        client, *_ = auth_client
        response = client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 401

    def test_dashboard_accessible_when_authenticated(self, auth_client):
        """Dashboard should be accessible when authenticated."""
        client, *_ = auth_client

        # Login first
        client.post("/login", data={
            "username": "test_admin",
            "password": "test_password"
        })

        # Now dashboard should work
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "Calendar" in response.text
        assert "Logout" in response.text

    def test_api_routes_require_authentication(self, auth_client):
        """API routes should require authentication."""
        client, *_ = auth_client

        # Test various API endpoints with appropriate methods
        test_cases = [
            ("GET", "/api/month"),
            ("GET", "/api/week"),
            ("DELETE", "/api/entry/2025-01-06"),
            ("POST", "/api/entries/batch"),
            ("GET", "/api/batch-edit/config")
        ]

        for method, endpoint in test_cases:
            if method == "GET":
                response = client.get(endpoint, follow_redirects=False)
            elif method == "POST":
                response = client.post(endpoint, follow_redirects=False)
            elif method == "DELETE":
                response = client.delete(endpoint, follow_redirects=False)
            else:
                raise ValueError(f"Unsupported method: {method}")

            assert response.status_code == 401, f"Endpoint {endpoint} with {method} should require auth"

    def test_api_routes_work_when_authenticated(self, auth_client):
        """API routes should work when authenticated."""
        client, schedule_path, base_date = auth_client

        # Login first
        client.post("/login", data={
            "username": "test_admin",
            "password": "test_password"
        })

        # Test month API
        response = client.get(f"/api/month?year={base_date.year}&month={base_date.month}")
        assert response.status_code == 200
        data = response.json()
        assert "entries" in data
        assert data["year"] == base_date.year
        assert data["month"] == base_date.month

    def test_google_verification_meta_tag_present(self, auth_client):
        """Google Search Console verification meta tag should be present."""
        client, *_ = auth_client
        response = client.get("/")
        assert response.status_code == 200
        assert 'name="google-site-verification"' in response.text
        assert 'content="7DYeWbjxsZFrKp2FPjZ7Fe1ETBmMlxcrrhfmEym_qjg"' in response.text

    def test_session_persistence_across_requests(self, auth_client):
        """Session should persist across multiple requests."""
        client, *_ = auth_client

        # Login
        client.post("/login", data={
            "username": "test_admin",
            "password": "test_password"
        })

        # Multiple requests should maintain session
        for _ in range(3):
            response = client.get("/dashboard")
            assert response.status_code == 200
            assert "Logout" in response.text

    def test_logout_button_present_in_dashboard(self, auth_client):
        """Logout button should be present in dashboard."""
        client, *_ = auth_client

        # Login first
        client.post("/login", data={
            "username": "test_admin",
            "password": "test_password"
        })

        # Check dashboard has logout button
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert 'action="/logout"' in response.text
        assert 'Logout' in response.text

    def test_privacy_policy_still_accessible(self, auth_client):
        """Privacy policy should still be accessible without authentication."""
        client, *_ = auth_client
        response = client.get("/privacy-policy")
        assert response.status_code == 200
        assert "Privacy Policy" in response.text

    def test_terms_of_service_still_accessible(self, auth_client):
        """Terms of service should still be accessible without authentication."""
        client, *_ = auth_client
        response = client.get("/terms-of-service")
        assert response.status_code == 200
        assert "Terms of Service" in response.text

    def test_health_check_still_accessible(self, auth_client):
        """Health check should still be accessible without authentication."""
        client, *_ = auth_client
        response = client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert data == {"status": "ok"}
