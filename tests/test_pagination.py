import os
import tempfile
import pytest
import base64
from datetime import datetime, timedelta
import schedule_manager as sm
from app.main import create_app
from app.job_tracker import JobTracker, get_job_tracker, JobExecutionResult
from fastapi.testclient import TestClient
from app.config import get_config


def _auth_header(user: str = "admin", password: str = "secret") -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("utf-8")
    return {"Authorization": f"Basic {token}"}


@pytest.fixture(autouse=True)
def reset_config_cache():
    get_config.cache_clear()  # type: ignore[attr-defined]
    yield
    get_config.cache_clear()  # type: ignore[attr-defined]


@pytest.fixture
def temp_db_file():
    """Create a temporary file for job tracker storage"""
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
        f.write('{"executions": []}')
    yield f.name
    os.unlink(f.name)


@pytest.fixture
def test_client(temp_db_file, monkeypatch):
    """Create a test client with temporary job tracker storage"""
    # Set required environment variables
    monkeypatch.setenv("ADMIN_DASHBOARD_PASSWORD", "secret")
    monkeypatch.setenv("ADMIN_DASHBOARD_USER", "admin")
    
    # Configure job tracker to use temporary storage
    from pathlib import Path
    temp_path = Path(temp_db_file)
    
    # Import job_tracker module and configure global instance BEFORE creating app
    import app.job_tracker
    app.job_tracker._job_tracker = app.job_tracker.JobTracker(storage_path=temp_path)
    app.job_tracker._job_tracker._current_jobs.clear()
    
    # Create test client
    app = create_app()
    return TestClient(app)


@pytest.fixture
def sample_jobs(test_client):
    """Add sample jobs to the temporary job tracker"""
    job_tracker = get_job_tracker()
    
    # Add 15 jobs
    base_time = datetime.now(tz=sm.TAIWAN_TZ)
    for i in range(15):
        job = JobExecutionResult(
            job_name=f"job_{i}",
            start_time=base_time - timedelta(minutes=i * 10),
            end_time=base_time - timedelta(minutes=i * 10) + timedelta(seconds=30),
            status="success",
        )
        key = f"{job.job_name}_{job.start_time.isoformat()}"
        job_tracker._current_jobs[key] = job
    
    job_tracker._save_history()
    return job_tracker


def test_pagination_basic(test_client, sample_jobs):
    """Test basic pagination functionality"""
    response = test_client.get("/api/jobs/recent?limit=5", headers=_auth_header())
    assert response.status_code == 200
    
    data = response.json()
    assert data["pagination"]["total"] == 15
    assert len(data["executions"]) == 5
    assert data["pagination"]["has_more"] is True
    
    # Verify job order (latest first)
    job_names = [job["job_name"] for job in data["executions"]]
    assert job_names == ["job_0", "job_1", "job_2", "job_3", "job_4"]


def test_pagination_with_offset(test_client, sample_jobs):
    """Test pagination with offset"""
    response = test_client.get("/api/jobs/recent?limit=5&offset=5", headers=_auth_header())
    assert response.status_code == 200
    
    data = response.json()
    assert len(data["executions"]) == 5
    assert data["pagination"]["has_more"] is True
    
    job_names = [job["job_name"] for job in data["executions"]]
    assert job_names == ["job_5", "job_6", "job_7", "job_8", "job_9"]


def test_pagination_last_page(test_client, sample_jobs):
    """Test pagination on last page"""
    response = test_client.get("/api/jobs/recent?limit=5&offset=10", headers=_auth_header())
    assert response.status_code == 200
    
    data = response.json()
    assert len(data["executions"]) == 5
    assert data["pagination"]["has_more"] is False
    
    job_names = [job["job_name"] for job in data["executions"]]
    assert job_names == ["job_10", "job_11", "job_12", "job_13", "job_14"]


def test_pagination_exceeding_total(test_client, sample_jobs):
    """Test offset larger than total jobs"""
    response = test_client.get("/api/jobs/recent?limit=5&offset=20", headers=_auth_header())
    assert response.status_code == 200
    
    data = response.json()
    assert data["pagination"]["total"] == 15
    assert len(data["executions"]) == 0
    assert data["pagination"]["has_more"] is False


def test_pagination_custom_limit(test_client, sample_jobs):
    """Test custom limit values"""
    # Test limit=10
    response = test_client.get("/api/jobs/recent?limit=10", headers=_auth_header())
    assert response.status_code == 200
    assert len(response.json()["executions"]) == 10
    assert response.json()["pagination"]["has_more"] is True
    
    # Test limit=1
    response = test_client.get("/api/jobs/recent?limit=1", headers=_auth_header())
    assert response.status_code == 200
    assert len(response.json()["executions"]) == 1
    assert response.json()["pagination"]["has_more"] is True


def test_pagination_invalid_limit(test_client, sample_jobs):
    """Test invalid limit parameter values"""
    # The API actually clamps invalid limits instead of returning 422
    response = test_client.get("/api/jobs/recent?limit=-5", headers=_auth_header())
    assert response.status_code == 200
    assert response.json()["pagination"]["limit"] == 20  # Default value
    
    response = test_client.get("/api/jobs/recent?limit=0", headers=_auth_header())
    assert response.status_code == 200
    assert response.json()["pagination"]["limit"] == 20
    
    response = test_client.get("/api/jobs/recent?limit=1000", headers=_auth_header())
    assert response.status_code == 200
    assert response.json()["pagination"]["limit"] == 20


def test_pagination_invalid_offset(test_client, sample_jobs):
    """Test invalid offset parameter values"""
    # The API clamps invalid offsets to 0
    response = test_client.get("/api/jobs/recent?limit=5&offset=-5", headers=_auth_header())
    assert response.status_code == 200
    assert response.json()["pagination"]["offset"] == 0


def test_pagination_job_name_filter(test_client, sample_jobs):
    """Test job name filter functionality"""
    response = test_client.get("/api/jobs/recent?limit=10&job_name=job_1", headers=_auth_header())
    assert response.status_code == 200
    
    data = response.json()
    
    # Check results contain only jobs with 'job_1' in name
    assert data["pagination"]["total"] > 0
    for job in data["executions"]:
        assert job["job_name"] == "job_1"


def test_pagination_dashboard_html(test_client, sample_jobs):
    """Test dashboard HTML renders without errors"""
    response = test_client.get("/")
    assert response.status_code == 200
    assert b"Daily Manna Email" in response.content  # Root route is home page


def test_notification_overlay(test_client, sample_jobs):
    """Test notification overlay structure in HTML"""
    response = test_client.get("/dashboard", headers=_auth_header())
    assert response.status_code == 200
    
    # Check basic notification structure exists
    assert b"notification-overlay" in response.content
    assert b"notification-list" in response.content
    assert b"notification-item" in response.content
    assert b"notification-content" in response.content
    assert b"notification-time" in response.content


def test_no_jobs_empty_state(test_client):
    """Test pagination behavior when there are no jobs"""
    response = test_client.get("/api/jobs/recent?limit=5", headers=_auth_header())
    assert response.status_code == 200
    
    data = response.json()
    assert data["pagination"]["total"] == 0
    assert len(data["executions"]) == 0
    assert data["pagination"]["has_more"] is False
