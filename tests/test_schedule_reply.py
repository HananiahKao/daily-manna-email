import datetime as dt

import pytest

import schedule_manager as sm
import schedule_reply as sr


def _make_schedule() -> sm.Schedule:
    entries = [
        sm.ScheduleEntry(date=dt.date(2025, 1, 5), selector="3-4-1"),
        sm.ScheduleEntry(date=dt.date(2025, 1, 6), selector="3-4-2"),
    ]
    return sm.Schedule(entries=entries)


def test_issue_reply_tokens_records_meta(monkeypatch):
    schedule = _make_schedule()
    token_seq = iter(["AAA111", "BBB222"])

    monkeypatch.setattr(sr, "_generate_token", lambda existing: next(token_seq))

    issued_at = dt.datetime(2025, 1, 1, 9, tzinfo=sm.TAIWAN_TZ)
    issued = sr.issue_reply_tokens(schedule, schedule.entries, "2025-W01", issued_at=issued_at, ttl_days=3)

    assert [item.token for item in issued] == ["AAA111", "BBB222"]
    store = schedule.meta[sr.META_KEY]["tokens"]
    assert store["AAA111"]["date"] == "2025-01-05"

    fetched = sr.get_reply_token(schedule, "AAA111", now=issued_at + dt.timedelta(days=1))
    assert fetched.date == dt.date(2025, 1, 5)
    assert fetched.summary_id == "2025-W01"


def test_get_reply_token_expired(monkeypatch):
    schedule = _make_schedule()
    monkeypatch.setattr(sr, "_generate_token", lambda existing: "CCC333")

    issued_at = dt.datetime(2025, 2, 1, 8, tzinfo=sm.TAIWAN_TZ)
    sr.issue_reply_tokens(schedule, [schedule.entries[0]], "2025-W05", issued_at=issued_at, ttl_days=1)

    with pytest.raises(sr.TokenExpiredError):
        sr.get_reply_token(schedule, "CCC333", now=issued_at + dt.timedelta(days=2))


def test_purge_expired_tokens(monkeypatch):
    schedule = _make_schedule()
    monkeypatch.setattr(sr, "_generate_token", lambda existing: "DDD444")

    issued_at = dt.datetime(2025, 3, 1, 8, tzinfo=sm.TAIWAN_TZ)
    sr.issue_reply_tokens(schedule, [schedule.entries[0]], "2025-W09", issued_at=issued_at, ttl_days=1)

    removed = sr.purge_expired_tokens(schedule, now=issued_at + dt.timedelta(days=3))
    assert removed == 1
    assert "DDD444" not in schedule.meta[sr.META_KEY]["tokens"]


def test_list_active_tokens(monkeypatch):
    schedule = _make_schedule()
    seq = iter(["EEE555", "FFF666"])
    monkeypatch.setattr(sr, "_generate_token", lambda existing: next(seq))

    issued_at = dt.datetime(2025, 4, 1, 8, tzinfo=sm.TAIWAN_TZ)
    sr.issue_reply_tokens(schedule, schedule.entries, "2025-W14", issued_at=issued_at, ttl_days=4)

    active = sr.list_active_tokens(schedule, now=issued_at + dt.timedelta(days=2))
    assert {item.token for item in active} == {"EEE555", "FFF666"}


def test_parse_reply_body_extracts_commands():
    body = """
    Quick notes

    [AAA111] skip traveling
    [BBB222] move 2025-05-04
    [CCC333] note Need volunteer reader
    > [SHOULDNOT] skip
    On Mon, someone wrote:
    [DDD444] skip later text
    """

    commands = sr.parse_reply_body(body)
    assert [(cmd.token, cmd.verb) for cmd in commands] == [
        ("AAA111", "skip"),
        ("BBB222", "move"),
        ("CCC333", "note"),
    ]
    assert commands[0].arguments["reason"] == "traveling"
    assert commands[1].arguments["date"] == dt.date(2025, 5, 4)
    assert commands[2].arguments["note"].startswith("Need volunteer")


def test_parse_reply_body_validates_move_date():
    with pytest.raises(sr.ParseError):
        sr.parse_reply_body("[AAA111] move notadate")


def test_parse_reply_body_rejects_keep_extra_text():
    with pytest.raises(sr.ParseError):
        sr.parse_reply_body("[AAA111] keep please")


def test_parse_reply_body_validates_selector():
    with pytest.raises(sr.ParseError):
        sr.parse_reply_body("[AAA111] selector bad-value")


def test_parse_reply_body_override_requires_text():
    with pytest.raises(sr.ParseError):
        sr.parse_reply_body("[AAA111] override ")


def test_remove_reply_token(monkeypatch):
    schedule = _make_schedule()
    monkeypatch.setattr(sr, "_generate_token", lambda existing: "REM123")

    issued_at = dt.datetime(2025, 5, 1, 8, tzinfo=sm.TAIWAN_TZ)
    sr.issue_reply_tokens(schedule, [schedule.entries[0]], "2025-W18", issued_at=issued_at)

    sr.remove_reply_token(schedule, "REM123")
    with pytest.raises(sr.TokenError):
        sr.get_reply_token(schedule, "REM123", now=issued_at)
