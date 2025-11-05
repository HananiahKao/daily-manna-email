import datetime as dt

import pytest

import schedule_manager as sm
import schedule_reply as sr
import schedule_reply_processor as proc


def _setup_schedule(monkeypatch):
    entries = [
        sm.ScheduleEntry(date=dt.date(2025, 6, 2), selector="4-1-1"),
        sm.ScheduleEntry(date=dt.date(2025, 6, 3), selector="4-1-2"),
    ]
    schedule = sm.Schedule(entries=entries)
    seq = iter(["AAA111", "BBB222"])
    monkeypatch.setattr(sr, "_generate_token", lambda existing: next(seq))
    issued_at = dt.datetime(2025, 6, 1, 8, tzinfo=sm.TAIWAN_TZ)
    tokens = sr.issue_reply_tokens(schedule, schedule.entries, "2025-W23", issued_at=issued_at)
    return schedule, tokens, issued_at


def test_apply_instructions_skip(monkeypatch):
    schedule, tokens, issued_at = _setup_schedule(monkeypatch)
    instruction = sr.ReplyInstruction(token=tokens[0].token, verb="skip", arguments={"reason": "vacation"})

    result = proc.apply_instructions(schedule, [instruction], now=issued_at)

    assert result.changed is True
    assert result.outcomes[0].status == "applied"
    entry = schedule.get_entry(tokens[0].date)
    assert entry.status == "skipped"
    assert "vacation" in entry.notes
    with pytest.raises(sr.TokenError):
        sr.get_reply_token(schedule, tokens[0].token, now=issued_at)


def test_apply_instructions_move_conflict(monkeypatch):
    schedule, tokens, issued_at = _setup_schedule(monkeypatch)
    instruction = sr.ReplyInstruction(token=tokens[0].token, verb="move", arguments={"date": schedule.entries[1].date})

    result = proc.apply_instructions(schedule, [instruction], now=issued_at)

    assert result.changed is False
    assert result.outcomes[0].status == "error"
    assert "already assigned" in result.outcomes[0].message
    # Token should remain for retry
    sr.get_reply_token(schedule, tokens[0].token, now=issued_at)


def test_apply_instructions_keep_removes_token(monkeypatch):
    schedule, tokens, issued_at = _setup_schedule(monkeypatch)
    instruction = sr.ReplyInstruction(token=tokens[0].token, verb="keep")

    result = proc.apply_instructions(schedule, [instruction], now=issued_at)

    assert result.changed is False
    assert result.outcomes[0].status == "noop"
    with pytest.raises(sr.TokenError):
        sr.get_reply_token(schedule, tokens[0].token, now=issued_at)


def test_process_email_updates_selector_and_note(monkeypatch):
    schedule, tokens, issued_at = _setup_schedule(monkeypatch)
    body = (
        f"[{tokens[0].token}] selector 5-2-3\n"
        f"[{tokens[1].token}] note Confirm scripture draft"
    )

    result = proc.process_email(schedule, body, now=issued_at)

    assert result.changed is True
    sel_entry = schedule.get_entry(dt.date(2025, 6, 2))
    assert sel_entry.selector == "5-2-3"
    note_entry = schedule.get_entry(dt.date(2025, 6, 3))
    assert "Confirm scripture" in note_entry.notes
    with pytest.raises(sr.TokenError):
        sr.get_reply_token(schedule, tokens[0].token, now=issued_at)
    with pytest.raises(sr.TokenError):
        sr.get_reply_token(schedule, tokens[1].token, now=issued_at)
