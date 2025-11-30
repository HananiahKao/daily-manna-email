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
    response = client.get("/")
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers


def test_dashboard_renders_schedule(dashboard_client):
    client, schedule_path, base_date = dashboard_client
    response = client.get("/", headers=_auth_header())
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
