"""Helpers for managing the EZOe email schedule.

This module replaces the old one-off state file with a richer schedule model
that tracks upcoming send dates, selectors, and delivery status. The intent is
to support a Sunday pre-population workflow, optional weekday overrides, and
daily send bookkeeping.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from content_source import ContentSource

try:  # Python 3.9+
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - fallback for older runtimes
    from backports.zoneinfo import ZoneInfo  # type: ignore


VERSION = 1
TZ_NAME = "Asia/Taipei"
TAIWAN_TZ = ZoneInfo(TZ_NAME)

DEFAULT_SCHEDULE_FILENAME = "state/ezoe_schedule.json"


WEEKDAY_TW = {
    0: "週一",
    1: "週二",
    2: "週三",
    3: "週四",
    4: "週五",
    5: "週六",
    6: "主日",
}

WEEKDAY_ALIASES: Dict[str, int] = {
    "mon": 0,
    "monday": 0,
    "1": 0,
    "週一": 0,
    "周一": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "2": 1,
    "週二": 1,
    "周二": 1,
    "wed": 2,
    "weds": 2,
    "wednesday": 2,
    "3": 2,
    "週三": 2,
    "周三": 2,
    "thu": 3,
    "thurs": 3,
    "thursday": 3,
    "4": 3,
    "週四": 3,
    "周四": 3,
    "fri": 4,
    "friday": 4,
    "5": 4,
    "週五": 4,
    "周五": 4,
    "sat": 5,
    "saturday": 5,
    "6": 5,
    "週六": 5,
    "周六": 5,
    "sun": 6,
    "sunday": 6,
    "7": 6,
    "0": 6,
    "週日": 6,
    "周日": 6,
    "主日": 6,
}


@dataclass
class ScheduleEntry:
    """An individual scheduled send."""

    date: dt.date
    selector: str
    status: str = "pending"
    sent_at: Optional[str] = None
    notes: str = ""
    override: Optional[str] = None

    def to_json(self) -> Dict[str, object]:
        return {
            "date": self.date.isoformat(),
            "weekday": WEEKDAY_TW[self.date.weekday()],
            "selector": self.selector,
            "status": self.status,
            "sent_at": self.sent_at,
            "notes": self.notes or "",
            "override": self.override,
        }

    @classmethod
    def from_json(cls, data: Dict[str, object]) -> "ScheduleEntry":
        date_raw = data.get("date")
        if not isinstance(date_raw, str):
            raise ValueError("schedule entry missing ISO date string")
        date = dt.date.fromisoformat(date_raw)
        selector_raw = data.get("selector")
        if not isinstance(selector_raw, str):
            raise ValueError("schedule entry missing selector")
        status = str(data.get("status", "pending"))
        sent_at = data.get("sent_at")
        if sent_at is not None:
            sent_at = str(sent_at)
        notes = str(data.get("notes", ""))
        override = data.get("override")
        if override is not None:
            override = str(override)
        return cls(date=date, selector=selector_raw, status=status, sent_at=sent_at, notes=notes, override=override)


@dataclass
class Schedule:
    """Collection of scheduled entries with metadata."""

    entries: List[ScheduleEntry] = field(default_factory=list)
    version: int = VERSION
    timezone: str = TZ_NAME
    meta: Dict[str, object] = field(default_factory=dict)

    def to_json(self) -> Dict[str, object]:
        return {
            "version": self.version,
            "timezone": self.timezone,
            "meta": self.meta,
            "entries": [entry.to_json() for entry in sorted(self.entries, key=lambda e: e.date)],
        }

    @classmethod
    def from_json(cls, data: Dict[str, object]) -> "Schedule":
        version = int(data.get("version", VERSION))
        tz = str(data.get("timezone", TZ_NAME))
        raw_entries = data.get("entries", [])
        entries: List[ScheduleEntry] = []
        if isinstance(raw_entries, list):
            for item in raw_entries:
                if isinstance(item, dict):
                    entries.append(ScheduleEntry.from_json(item))
        meta = data.get("meta", {})
        if not isinstance(meta, dict):
            meta = {}
        entries.sort(key=lambda e: e.date)
        return cls(entries=entries, version=version, timezone=tz, meta=meta)

    def get_entry(self, date: dt.date) -> Optional[ScheduleEntry]:
        for entry in self.entries:
            if entry.date == date:
                return entry
        return None

    def latest_before(self, date: dt.date) -> Optional[ScheduleEntry]:
        prior = [e for e in self.entries if e.date < date]
        return prior[-1] if prior else None

    def upsert_entry(self, entry: ScheduleEntry) -> None:
        existing = self.get_entry(entry.date)
        if existing:
            existing.selector = entry.selector
            existing.status = entry.status
            existing.sent_at = entry.sent_at
            existing.notes = entry.notes
            existing.override = entry.override
        else:
            self.entries.append(entry)
            self.entries.sort(key=lambda e: e.date)


def get_schedule_path() -> Path:
    """Return path to the schedule file, respecting SCHEDULE_FILE env override."""

    base = os.environ.get("SCHEDULE_FILE")
    if base:
        return Path(base).expanduser().resolve()
    
    # Derive filename from content source
    source_name = os.getenv("CONTENT_SOURCE", "ezoe").lower()
    filename = f"state/{source_name}_schedule.json"
    return (Path(os.getcwd()) / filename).resolve()


def load_schedule(path: Optional[Path] = None) -> Schedule:
    """Load schedule JSON from disk, returning an empty schedule when missing."""

    path = path or get_schedule_path()
    if not path.exists():
        return Schedule()
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("schedule file root must be an object")
    schedule = Schedule.from_json(data)
    schedule.timezone = TZ_NAME
    return schedule


def save_schedule(schedule: Schedule, path: Optional[Path] = None) -> None:
    """Persist schedule to disk."""

    path = path or get_schedule_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(schedule.to_json(), ensure_ascii=False, indent=2)
    path.write_text(payload + "\n", encoding="utf-8")




def determine_seed_selector(schedule: Schedule, source: ContentSource, default: Optional[str] = None) -> str:
    if schedule.entries:
        last_selector = schedule.entries[-1].selector
        return source.advance_selector(last_selector)
    if default:
        source.parse_selector(default)
        return default
    return source.get_default_selector()


def ensure_date_range(
    schedule: Schedule,
    source: ContentSource,
    start_date: dt.date,
    end_date: dt.date,
    seed_selector: Optional[str] = None,
) -> bool:
    """Ensure entries exist for every date in [start_date, end_date].

    Returns True when new entries were added.
    """

    if end_date < start_date:
        raise ValueError("end_date must not be before start_date")

    new_entries_added = False
    seed = seed_selector or determine_seed_selector(schedule, source)

    pointer_entry = schedule.latest_before(start_date)
    cursor_selector = pointer_entry.selector if pointer_entry else None
    day_count = (end_date - start_date).days + 1
    for offset in range(day_count):
        date = start_date + dt.timedelta(days=offset)
        existing = schedule.get_entry(date)
        if existing:
            cursor_selector = existing.selector
            continue
        if cursor_selector is None:
            cursor_selector = seed
        else:
            cursor_selector = source.advance_selector(cursor_selector)
            
            # --- Validation Logic ---
            if hasattr(source, "validate_lesson_exists") and hasattr(source, "parse_selector") and hasattr(source, "format_selector"):
                try:
                    vol, les, day = source.parse_selector(cursor_selector)
                    # Only validate when we start a new lesson (day 1)
                    if day == 1:
                        is_valid = source.validate_lesson_exists(vol, les)
                        if not is_valid:
                            # If invalid, roll over to the next volume
                            new_vol = vol + 1
                            new_les = 1
                            new_day = 1
                            candidate = source.format_selector((new_vol, new_les, new_day))
                            print(f"DEBUG: Lesson {vol}-{les} invalid, rolling over to {candidate}")
                            cursor_selector = candidate
                except Exception as e:
                    print(f"WARNING: Validation failed for {cursor_selector}: {e}")
            # ------------------------

        entry = ScheduleEntry(date=date, selector=cursor_selector)
        schedule.upsert_entry(entry)
        new_entries_added = True
    return new_entries_added


def mark_sent(schedule: Schedule, target_date: dt.date, timestamp: Optional[dt.datetime] = None) -> ScheduleEntry:
    entry = schedule.get_entry(target_date)
    if not entry:
        raise KeyError(f"no schedule entry for {target_date.isoformat()}")
    entry.status = "sent"
    entry.sent_at = (timestamp or dt.datetime.now(tz=TAIWAN_TZ)).isoformat()
    return entry


def next_for_date(
    schedule: Schedule,
    target_date: dt.date,
    include_sent: bool = False,
) -> Optional[ScheduleEntry]:
    entry = schedule.get_entry(target_date)
    if not entry:
        return None
    if entry.status == "sent" and not include_sent:
        return None
    return entry


def taipei_today(now: Optional[dt.datetime] = None) -> dt.date:
    now = now or dt.datetime.now(tz=TAIWAN_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=TAIWAN_TZ)
    return now.astimezone(TAIWAN_TZ).date()


def parse_date_descriptor(descriptor: str, today: Optional[dt.date] = None) -> dt.date:
    descriptor = descriptor.strip()
    if not descriptor:
        raise ValueError("descriptor cannot be empty")
    today = today or taipei_today()
    try:
        return dt.date.fromisoformat(descriptor)
    except ValueError:
        pass

    lowered = descriptor.lower()
    if lowered in ("today", "現今", "今天"):
        return today
    if lowered in ("tomorrow", "明天"):
        return today + dt.timedelta(days=1)

    if lowered not in WEEKDAY_ALIASES:
        raise ValueError(f"unrecognized date descriptor: {descriptor}")
    weekday_target = WEEKDAY_ALIASES[lowered]
    today_weekday = today.weekday()
    delta = (weekday_target - today_weekday) % 7
    return today + dt.timedelta(days=delta)


def resolve_weekday_override(value: str, today: Optional[dt.date] = None) -> dt.date:
    if not value:
        raise ValueError("override value required")
    return parse_date_descriptor(value, today=today)


__all__ = [
    "Schedule",
    "ScheduleEntry",
    "taipei_today",
]
