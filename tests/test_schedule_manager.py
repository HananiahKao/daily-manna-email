import datetime as dt

import pytest

import schedule_manager as sm
from ezoe_content_source import EzoeContentSource


def test_ensure_date_range_populates_week(monkeypatch):
    monkeypatch.setenv("EZOE_VOLUME", "3")
    monkeypatch.setenv("EZOE_LESSON", "10")
    monkeypatch.setenv("EZOE_DAY_START", "1")

    schedule = sm.Schedule()
    start = dt.date(2025, 1, 13)  # Monday
    end = start + dt.timedelta(days=6)
    source = EzoeContentSource()

    changed = sm.ensure_date_range(schedule, source, start, end)

    assert changed is True
    assert len(schedule.entries) == 7
    selectors = [entry.selector for entry in schedule.entries]
    assert selectors[0] == "3-10-1"
    assert selectors[-1] == "3-10-7"
    weekdays = [entry.to_json()["weekday"] for entry in schedule.entries]
    assert weekdays[0] == "週一"
    assert weekdays[-1] == "主日"


def test_ensure_date_range_respects_existing_sequence():
    start = dt.date(2025, 2, 3)  # Monday
    schedule = sm.Schedule(entries=[sm.ScheduleEntry(date=start, selector="2-5-1")])
    source = EzoeContentSource()

    changed = sm.ensure_date_range(schedule, source, start + dt.timedelta(days=1), start + dt.timedelta(days=2))

    assert changed is True
    selectors = [entry.selector for entry in schedule.entries]
    assert selectors == ["2-5-1", "2-5-2", "2-5-3"]


def test_mark_sent_updates_status_and_timestamp():
    target_date = dt.date(2025, 3, 5)
    schedule = sm.Schedule(entries=[sm.ScheduleEntry(date=target_date, selector="4-1-3")])
    ts = dt.datetime(2025, 3, 5, 7, 30, tzinfo=sm.TAIWAN_TZ)

    updated = sm.mark_sent(schedule, target_date, timestamp=ts)

    assert updated.status == "sent"
    assert updated.sent_at == ts.isoformat()
    # Should not duplicate entries
    assert len(schedule.entries) == 1


def test_next_for_date_pending_and_sent():
    target_date = dt.date(2025, 4, 10)
    entry = sm.ScheduleEntry(date=target_date, selector="1-2-4")
    schedule = sm.Schedule(entries=[entry])

    assert sm.next_for_date(schedule, target_date) is entry

    entry.status = "sent"
    assert sm.next_for_date(schedule, target_date) is None
    assert sm.next_for_date(schedule, target_date, include_sent=True) is entry


@pytest.mark.parametrize(
    "descriptor, expected",
    [
        ("2025-05-01", dt.date(2025, 5, 1)),
        ("Mon", dt.date(2025, 4, 21)),
        ("週五", dt.date(2025, 4, 18)),
        ("主日", dt.date(2025, 4, 20)),
        ("today", dt.date(2025, 4, 16)),
        ("tomorrow", dt.date(2025, 4, 17)),
    ],
)
def test_parse_date_descriptor(descriptor, expected):
    today = dt.date(2025, 4, 16)  # Wednesday
    assert sm.parse_date_descriptor(descriptor, today=today) == expected


def test_parse_date_descriptor_invalid():
    today = dt.date(2025, 4, 16)
    with pytest.raises(ValueError):
        sm.parse_date_descriptor("noday", today=today)


def test_determine_seed_selector_prefers_existing():
    schedule = sm.Schedule(entries=[
        sm.ScheduleEntry(date=dt.date(2025, 1, 1), selector="3-2-6"),
        sm.ScheduleEntry(date=dt.date(2025, 1, 2), selector="3-2-7"),
    ])
    source = EzoeContentSource()

    seed = sm.determine_seed_selector(schedule, source)
    assert seed == "3-3-1"

