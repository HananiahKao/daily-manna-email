import base64
import datetime as dt

import pytest
from fastapi.testclient import TestClient

import schedule_manager as sm

from app.config import get_config
from app.main import create_app


def _auth_header(user: str = "admin", password: str = "secret") -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("utf-8")
    return {"Authorization": f"Basic {token}"}


@pytest.fixture(autouse=True)
def reset_config_cache():
    get_config.cache_clear()  # type: ignore[attr-defined]
    yield
    get_config.cache_clear()  # type: ignore[attr-defined]


@pytest.fixture
def dashboard_client(monkeypatch, tmp_path):
    schedule_path = tmp_path / "ezoe_schedule.json"
    monkeypatch.setenv("SCHEDULE_FILE", str(schedule_path))
    monkeypatch.setenv("ADMIN_DASHBOARD_PASSWORD", "secret")
    monkeypatch.setenv("ADMIN_DASHBOARD_USER", "admin")

    base_date = dt.date(2025, 1, 6)  # Monday
    monkeypatch.setattr(sm, "taipei_today", lambda now=None: base_date)

    schedule = sm.Schedule(entries=[sm.ScheduleEntry(date=base_date, selector="2-10-1")])
    sm.save_schedule(schedule, schedule_path)

    app = create_app()
    client = TestClient(app)
    return client, schedule_path, base_date


def test_dashboard_requires_auth(dashboard_client):
    client, _path, _date = dashboard_client
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 302
    assert "login-form" in response.headers["location"]


def test_dashboard_renders_schedule(dashboard_client):
    client, schedule_path, base_date = dashboard_client
    response = client.get("/dashboard", headers=_auth_header())
    assert response.status_code == 200
    
    # Check that the calendar data is available via API
    api_response = client.get(
        f"/api/month?year={base_date.year}&month={base_date.month}",
        headers=_auth_header()
    )
    assert api_response.status_code == 200
    data = api_response.json()
    
    # Find the entry for base_date in the API response
    entry_found = False
    for entry in data["entries"]:
        if entry["date"] == base_date.isoformat():
            assert entry["selector"] == "2-10-1"
            entry_found = True
            break
    assert entry_found, f"Entry for {base_date} not found in API response"

    schedule = sm.load_schedule(schedule_path)
    assert schedule.get_entry(base_date) is not None


def test_mark_sent_action_updates_schedule(dashboard_client):
    client, schedule_path, base_date = dashboard_client
    response = client.post(
        f"/actions/{base_date.isoformat()}",
        headers=_auth_header(),
        data={"action": "mark_sent"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    schedule = sm.load_schedule(schedule_path)
    entry = schedule.get_entry(base_date)
    assert entry is not None
    assert entry.status == "sent"


def test_move_action_rejects_conflict(dashboard_client):
    client, schedule_path, base_date = dashboard_client
    conflict_date = base_date + dt.timedelta(days=1)
    schedule = sm.load_schedule(schedule_path)
    schedule.upsert_entry(sm.ScheduleEntry(date=conflict_date, selector="2-10-2"))
    sm.save_schedule(schedule, schedule_path)

    response = client.post(
        f"/actions/{base_date.isoformat()}",
        headers=_auth_header(),
        data={"action": "move", "move_date": conflict_date.isoformat()},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error" in response.headers.get("location", "")

    schedule = sm.load_schedule(schedule_path)
    entry = schedule.get_entry(base_date)
    assert entry is not None
    assert entry.date == base_date


def test_delete_entry_api(dashboard_client):
    client, schedule_path, base_date = dashboard_client

    # Verify entry exists before deletion
    schedule = sm.load_schedule(schedule_path)
    original_entry = schedule.get_entry(base_date)
    assert original_entry is not None

    # Delete the entry
    response = client.delete(f"/api/entry/{base_date.isoformat()}", headers=_auth_header())
    assert response.status_code == 200
    data = response.json()
    assert data == {"deleted": True, "date": base_date.isoformat()}

    # Verify entry is gone
    schedule = sm.load_schedule(schedule_path)
    assert schedule.get_entry(base_date) is None

    # Try to delete same entry again - should get 404
    response = client.delete(f"/api/entry/{base_date.isoformat()}", headers=_auth_header())
    assert response.status_code == 404


def test_batch_delete_entries_api(dashboard_client):
    client, schedule_path, base_date = dashboard_client

    # Add multiple entries to test batch delete
    additional_dates = [
        base_date + dt.timedelta(days=i) for i in range(1, 4)  # 3 more entries
    ]
    schedule = sm.load_schedule(schedule_path)
    for additional_date in additional_dates:
        schedule.upsert_entry(sm.ScheduleEntry(date=additional_date, selector="2-10-1"))
    sm.save_schedule(schedule, schedule_path)

    # Verify all entries exist
    schedule = sm.load_schedule(schedule_path)
    all_dates = [base_date] + additional_dates
    for date in all_dates:
        assert schedule.get_entry(date) is not None

    # Delete first 2 entries
    dates_to_delete = all_dates[:2]
    response = client.post(
        "/api/entries/batch-delete",
        headers=_auth_header(),
        json=[d.isoformat() for d in dates_to_delete]
    )
    assert response.status_code == 200
    data = response.json()
    assert data == {
        "deleted": sorted([d.isoformat() for d in dates_to_delete]),
        "count": len(dates_to_delete)
    }

    # Verify entries are gone
    schedule = sm.load_schedule(schedule_path)
    for date in dates_to_delete:
        assert schedule.get_entry(date) is None

    # Verify remaining entries still exist
    for date in all_dates[2:]:
        assert schedule.get_entry(date) is not None

    # Try to delete non-existent entries - should get 404
    response = client.post(
        "/api/entries/batch-delete",
        headers=_auth_header(),
        json=[d.isoformat() for d in dates_to_delete]  # These were already deleted
    )
    assert response.status_code == 404


def test_upsert_entry_api_create(dashboard_client):
    """Test creating a new entry via API."""
    client, schedule_path, base_date = dashboard_client
    new_date = base_date + dt.timedelta(days=7)  # Next Monday

    # Create new entry
    response = client.post(
        "/api/entry",
        headers=_auth_header(),
        json={
            "date": new_date.isoformat(),
            "selector": "2-10-2",
            "status": "pending",
            "notes": "Test entry"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["created"] == True
    assert data["entry"]["selector"] == "2-10-2"
    assert data["entry"]["status"] == "pending"
    assert data["entry"]["notes"] == "Test entry"

    # Verify entry was created in schedule
    schedule = sm.load_schedule(schedule_path)
    entry = schedule.get_entry(new_date)
    assert entry is not None
    assert entry.selector == "2-10-2"
    assert entry.status == "pending"
    assert entry.notes == "Test entry"


def test_upsert_entry_api_update(dashboard_client):
    """Test updating an existing entry via API."""
    client, schedule_path, base_date = dashboard_client

    # Update existing entry
    response = client.post(
        "/api/entry",
        headers=_auth_header(),
        json={
            "date": base_date.isoformat(),
            "selector": "2-10-3",
            "status": "sent",
            "notes": "Updated notes"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["created"] == False
    assert data["entry"]["selector"] == "2-10-3"
    assert data["entry"]["status"] == "sent"
    assert data["entry"]["notes"] == "Updated notes"

    # Verify entry was updated in schedule
    schedule = sm.load_schedule(schedule_path)
    entry = schedule.get_entry(base_date)
    assert entry is not None
    assert entry.selector == "2-10-3"
    assert entry.status == "sent"
    assert entry.notes == "Updated notes"


def test_upsert_entry_api_requires_selector_for_new(dashboard_client):
    """Test that creating a new entry requires a selector."""
    client, schedule_path, base_date = dashboard_client
    new_date = base_date + dt.timedelta(days=7)

    response = client.post(
        "/api/entry",
        headers=_auth_header(),
        json={"date": new_date.isoformat(), "status": "pending"}
    )
    assert response.status_code == 400
    assert "Selector required" in response.json()["detail"]


def test_move_single_entry_api(dashboard_client):
    """Test moving a single entry to a new date."""
    client, schedule_path, base_date = dashboard_client
    target_date = base_date + dt.timedelta(days=7)  # Next Monday

    # Move entry
    response = client.post(
        f"/api/entry/{base_date.isoformat()}/move",
        headers=_auth_header(),
        json={"new_date": target_date.isoformat()}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["entry"]["date"] == target_date.isoformat()

    # Verify entry moved in schedule
    schedule = sm.load_schedule(schedule_path)
    assert schedule.get_entry(base_date) is None
    entry = schedule.get_entry(target_date)
    assert entry is not None
    assert entry.selector == "2-10-1"


def test_move_single_entry_api_conflict(dashboard_client):
    """Test that moving to an occupied date fails."""
    client, schedule_path, base_date = dashboard_client
    conflict_date = base_date + dt.timedelta(days=1)

    # Create entry at conflict date
    schedule = sm.load_schedule(schedule_path)
    schedule.upsert_entry(sm.ScheduleEntry(date=conflict_date, selector="2-10-2"))
    sm.save_schedule(schedule, schedule_path)

    # Try to move to occupied date
    response = client.post(
        f"/api/entry/{base_date.isoformat()}/move",
        headers=_auth_header(),
        json={"new_date": conflict_date.isoformat()}
    )
    assert response.status_code == 400
    assert "already has an entry" in response.json()["detail"]


def test_move_multiple_entries_api(dashboard_client):
    """Test moving multiple entries by date offset."""
    client, schedule_path, base_date = dashboard_client

    # Add another entry
    second_date = base_date + dt.timedelta(days=1)
    schedule = sm.load_schedule(schedule_path)
    schedule.upsert_entry(sm.ScheduleEntry(date=second_date, selector="2-10-2"))
    sm.save_schedule(schedule, schedule_path)

    # Move both entries by 7 days
    target_date = base_date + dt.timedelta(days=7)
    response = client.post(
        "/api/entries/move",
        headers=_auth_header(),
        json={
            "source_dates": [base_date.isoformat(), second_date.isoformat()],
            "target_date": target_date.isoformat()
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["entries"]) == 2

    # Verify entries moved
    schedule = sm.load_schedule(schedule_path)
    assert schedule.get_entry(base_date) is None
    assert schedule.get_entry(second_date) is None
    assert schedule.get_entry(target_date) is not None
    assert schedule.get_entry(target_date + dt.timedelta(days=1)) is not None


def test_move_respects_content_source_header(monkeypatch, tmp_path):
    """Regression: move endpoints must use the schedule for the X-Content-Source header.

    Before the fix, both /api/entry/{date}/move and /api/entries/move ignored
    the X-Content-Source header and always operated on the default (EZOE)
    schedule. This caused a spurious "Target date already has an entry" 400
    error when dragging an entry in the Wix view, because the backend found a
    conflicting entry in EZOE's schedule even though the target cell appeared
    empty in the Wix calendar.
    """
    get_config.cache_clear()  # type: ignore[attr-defined]
    monkeypatch.setenv("ADMIN_DASHBOARD_PASSWORD", "secret")
    monkeypatch.setenv("ADMIN_DASHBOARD_USER", "admin")
    monkeypatch.delenv("SCHEDULE_FILE", raising=False)  # enable content-source routing

    # Redirect os.getcwd() so state/*.json resolves inside tmp_path
    monkeypatch.chdir(tmp_path)
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    tuesday = dt.date(2025, 1, 7)
    thursday = tuesday + dt.timedelta(days=2)

    # Wix schedule: only Tuesday
    wix_schedule = sm.Schedule(entries=[sm.ScheduleEntry(date=tuesday, selector="wix-entry")])
    sm.save_schedule(wix_schedule, state_dir / "wix_schedule.json")

    # EZOE schedule: both Tuesday AND Thursday — this is the false-conflict source
    ezoe_schedule = sm.Schedule(entries=[
        sm.ScheduleEntry(date=tuesday, selector="ezoe-tue"),
        sm.ScheduleEntry(date=thursday, selector="ezoe-thu"),
    ])
    sm.save_schedule(ezoe_schedule, state_dir / "ezoe_schedule.json")

    app = create_app()
    client = TestClient(app)

    # Moving Wix's Tuesday to Thursday must succeed (Wix has no Thursday entry)
    response = client.post(
        f"/api/entry/{tuesday.isoformat()}/move",
        headers={**_auth_header(), "X-Content-Source": "wix"},
        json={"new_date": thursday.isoformat()},
    )
    assert response.status_code == 200, response.json()

    # Wix schedule updated correctly
    updated_wix = sm.load_schedule(state_dir / "wix_schedule.json")
    assert updated_wix.get_entry(tuesday) is None
    assert updated_wix.get_entry(thursday) is not None
    assert updated_wix.get_entry(thursday).selector == "wix-entry"

    # EZOE schedule untouched
    unchanged_ezoe = sm.load_schedule(state_dir / "ezoe_schedule.json")
    assert unchanged_ezoe.get_entry(thursday).selector == "ezoe-thu"


def test_batch_update_entries_api(dashboard_client):
    """Test batch updating multiple entries."""
    client, schedule_path, base_date = dashboard_client

    # Add entries to update
    dates_to_update = [base_date + dt.timedelta(days=i) for i in range(1, 4)]
    schedule = sm.load_schedule(schedule_path)
    for date in dates_to_update:
        schedule.upsert_entry(sm.ScheduleEntry(date=date, selector="2-10-1"))
    sm.save_schedule(schedule, schedule_path)

    # Batch update entries
    updates = [
        {
            "date": base_date.isoformat(),
            "status": "sent",
            "notes": "Updated via batch"
        },
        {
            "date": dates_to_update[0].isoformat(),
            "selector": "2-10-3",
            "status": "pending"
        }
    ]

    response = client.post(
        "/api/entries/batch",
        headers=_auth_header(),
        json={"entries": updates}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["entries"]) == 2

    # Verify updates
    schedule = sm.load_schedule(schedule_path)
    entry1 = schedule.get_entry(base_date)
    assert entry1 is not None
    assert entry1.status == "sent"
    assert entry1.notes == "Updated via batch"

    entry2 = schedule.get_entry(dates_to_update[0])
    assert entry2 is not None
    assert entry2.selector == "2-10-3"
    assert entry2.status == "pending"


def test_batch_edit_config_api(dashboard_client):
    """Test getting batch edit configuration."""
    client, _schedule_path, _base_date = dashboard_client

    response = client.get("/api/batch-edit/config", headers=_auth_header())
    assert response.status_code == 200
    data = response.json()

    # Should return source configuration
    assert "source_name" in data
    assert "ui_config" in data


def test_parse_batch_selectors_api(dashboard_client):
    """Test parsing batch selectors."""
    client, _schedule_path, _base_date = dashboard_client

    # Test valid batch input
    response = client.post(
        "/api/batch-edit/parse-selectors",
        headers=_auth_header(),
        json={"input_text": "2-10-1\n2-10-2\n2-10-3"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True
    assert len(data["selectors"]) == 3
    assert data["count"] == 3


def test_parse_batch_selectors_api_invalid(dashboard_client):
    """Test parsing invalid batch selectors."""
    client, _schedule_path, _base_date = dashboard_client

    response = client.post(
        "/api/batch-edit/parse-selectors",
        headers=_auth_header(),
        json={"input_text": "invalid-selector"}
    )
    assert response.status_code == 400
    assert "detail" in response.json()


def test_week_api(dashboard_client):
    """Test the week API endpoint."""
    client, schedule_path, base_date = dashboard_client

    # Get the week containing base_date
    response = client.get("/api/week", headers=_auth_header())
    assert response.status_code == 200
    data = response.json()

    # Should return 7 days of entries
    assert len(data["entries"]) == 7
    assert data["start"] == (base_date - dt.timedelta(days=base_date.weekday())).isoformat()
    assert data["end"] == (base_date - dt.timedelta(days=base_date.weekday()) + dt.timedelta(days=6)).isoformat()

    # Check that our base_date entry is in the response
    entry_found = False
    for entry in data["entries"]:
        if entry["date"] == base_date.isoformat():
            assert entry["selector"] == "2-10-1"
            entry_found = True
            break
    assert entry_found


def test_healthz_endpoint(dashboard_client):
    """Test health check endpoint."""
    client, _schedule_path, _base_date = dashboard_client

    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "ok"}


def test_root_page(dashboard_client):
    """Test root page rendering."""
    client, _schedule_path, _base_date = dashboard_client

    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_login_form_page(dashboard_client):
    """Test login form page rendering."""
    client, _schedule_path, _base_date = dashboard_client

    response = client.get("/login-form")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_login_success(dashboard_client):
    """Test successful login."""
    client, _schedule_path, _base_date = dashboard_client

    response = client.post(
        "/login",
        data={"username": "admin", "password": "secret", "next": "/dashboard"},
        follow_redirects=False
    )
    assert response.status_code == 302
    assert "/dashboard" in response.headers["location"]


def test_login_failure(dashboard_client):
    """Test failed login."""
    client, _schedule_path, _base_date = dashboard_client

    response = client.post(
        "/login",
        data={"username": "admin", "password": "wrong", "next": "/dashboard"}
    )
    assert response.status_code == 401
    assert "Invalid credentials" in response.text


def test_logout(dashboard_client):
    """Test logout functionality."""
    client, _schedule_path, _base_date = dashboard_client

    # First login
    client.post("/login", data={"username": "admin", "password": "secret"})

    # Then logout
    response = client.post("/logout", follow_redirects=False)
    assert response.status_code == 302
    assert "/" in response.headers["location"]


def test_privacy_policy_page(dashboard_client):
    """Test privacy policy page."""
    client, _schedule_path, _base_date = dashboard_client

    response = client.get("/privacy-policy")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_terms_of_service_page(dashboard_client):
    """Test terms of service page."""
    client, _schedule_path, _base_date = dashboard_client

    response = client.get("/terms-of-service")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
