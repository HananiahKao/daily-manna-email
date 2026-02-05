#!/usr/bin/env python3
"""
Job dispatcher that fans out to cron-friendly scripts based on Taiwan time.

Usage:
    python job_dispatcher.py                 # run normally
    python job_dispatcher.py --dry-run       # log actions without executing
    python job_dispatcher.py --show-config   # print the active config (JSON)

The dispatcher can read custom rules from a JSON file (default:
`config/dispatch_rules.json`). When no file exists it falls back to defaults that
cover the daily send and weekly summary jobs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import schedule_manager as sm

logger = logging.getLogger(__name__)


DEFAULT_CONFIG_PATH = Path(os.getenv("DISPATCH_CONFIG", "config/dispatch_rules.json"))
DEFAULT_STATE_PATH = Path(os.getenv("DISPATCH_STATE_FILE", "state/dispatch_state.json"))
DEFAULT_DAILY_TIME = os.getenv("DISPATCH_DAILY_TIME", "06:00")
DEFAULT_SUMMARY_TIME = os.getenv("DISPATCH_SUMMARY_TIME", "21:00")

WEEKDAY_MAP = {
    "mon": 0,
    "monday": 0,
    "週一": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "週二": 1,
    "wed": 2,
    "wednesday": 2,
    "週三": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "週四": 3,
    "fri": 4,
    "friday": 4,
    "週五": 4,
    "sat": 5,
    "saturday": 5,
    "週六": 5,
    "sun": 6,
    "sunday": 6,
    "週日": 6,
    "主日": 6,
}


@dataclass(frozen=True)
class DispatchRule:
    name: str
    time: dt.time
    weekdays: Sequence[int]
    commands: Sequence[Sequence[str]]
    env: Optional[Dict[str, str]] = None

    @property
    def weekdays_label(self) -> str:
        if len(self.weekdays) == 7:
            return "daily"
        return ",".join(str(w) for w in self.weekdays)


def _parse_time(value: str) -> dt.time:
    try:
        hour, minute = value.split(":")
        return dt.time(hour=int(hour), minute=int(minute), tzinfo=sm.TAIWAN_TZ)
    except Exception as exc:  # pragma: no cover - defensive
        raise ValueError(f"Invalid HH:MM time string: {value!r}") from exc


def normalize_time_str(value: str) -> str:
    parsed = _parse_time(value.strip())
    return f"{parsed.hour:02d}:{parsed.minute:02d}"


def _parse_weekdays(values: Sequence[str | int]) -> Sequence[int]:
    resolved: List[int] = []
    for raw in values:
        if isinstance(raw, int):
            if not 0 <= raw <= 6:
                raise ValueError(f"Weekday index must be 0-6: {raw}")
            resolved.append(raw)
            continue
        lowered = raw.strip().lower()
        if lowered in ("daily", "all"):
            return tuple(range(7))
        if lowered not in WEEKDAY_MAP:
            raise ValueError(f"Unknown weekday label: {raw}")
        resolved.append(WEEKDAY_MAP[lowered])
    return tuple(sorted(set(resolved)))


def _coerce_command(command: Sequence[str] | str) -> List[str]:
    if isinstance(command, str):
        return ["bash", "-lc", command]
    return list(command)


def _default_rules() -> List[DispatchRule]:
    return [
        DispatchRule(
            name="daily-send",
            time=_parse_time(DEFAULT_DAILY_TIME),
            weekdays=tuple(range(7)),
            commands=(("bash", "scripts/run_daily_stateful_ezoe.sh"),),
        ),
        DispatchRule(
            name="weekly-summary",
            time=_parse_time(DEFAULT_SUMMARY_TIME),
            weekdays=(6,),  # Sunday
            commands=(("bash", "scripts/run_weekly_schedule_summary.sh"),),
        ),
    ]


def default_rules_config() -> List[Dict[str, object]]:
    return [
        {
            "name": "daily-send",
            "time": normalize_time_str(DEFAULT_DAILY_TIME),
            "days": ["daily"],
            "commands": [["bash", "scripts/run_daily_stateful_ezoe.sh"]],
        },
        {
            "name": "weekly-summary",
            "time": normalize_time_str(DEFAULT_SUMMARY_TIME),
            "days": [6],
            "commands": [["bash", "scripts/run_weekly_schedule_summary.sh"]],
        },
    ]


def load_rules(config_path: Path) -> List[DispatchRule]:
    if not config_path.exists():
        return _default_rules()

    with config_path.open("r", encoding="utf-8") as fh:
        raw_config = json.load(fh)

    rules: List[DispatchRule] = []
    for item in raw_config:
        name = item["name"]
        time_str = item["time"]
        days = item.get("days") or item.get("weekdays") or ["daily"]
        commands = item.get("commands") or []
        if not commands:
            raise ValueError(f"Rule {name} missing commands")
        rules.append(
            DispatchRule(
                name=name,
                time=_parse_time(time_str),
                weekdays=_parse_weekdays(days),
                commands=tuple(_coerce_command(cmd) for cmd in commands),
                env=item.get("env"),
            )
        )
    return rules


def load_state(state_path: Path) -> Dict[str, str]:
    if not state_path.exists():
        return {}
    with state_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_state(state_path: Path, data: Dict[str, str]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = state_path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    tmp_path.replace(state_path)


def _parse_iso_datetime(value: str) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=sm.TAIWAN_TZ)
    return parsed.astimezone(sm.TAIWAN_TZ)


def _scheduled_datetime(rule: DispatchRule, reference: dt.datetime) -> dt.datetime:
    return reference.astimezone(sm.TAIWAN_TZ).replace(
        hour=rule.time.hour,
        minute=rule.time.minute,
        second=rule.time.second,
        microsecond=0,
    )


def _should_run(
    rule: DispatchRule,
    now: dt.datetime,
    last_run_at: Optional[dt.datetime],
    max_delay: dt.timedelta,
) -> bool:
    if now.weekday() not in rule.weekdays:
        return False

    scheduled = _scheduled_datetime(rule, now)
    if now < scheduled:
        return False
    if now - scheduled > max_delay:
        return False
    if last_run_at and last_run_at >= scheduled:
        return False
    return True


def _run_command(cmd: Sequence[str], dry_run: bool) -> None:
    display = " ".join(cmd)
    if dry_run:
        logger.info(f"Dry-run: {display}")
        return
    logger.info(f"Running command: {display}")
    subprocess.run(cmd, check=True)


def get_jobs_to_run(
    rules: Sequence[DispatchRule],
    now: dt.datetime,
    state: Dict[str, str],
    max_delay: dt.timedelta,
) -> List[DispatchRule]:
    """Return jobs that should run based on schedule and state, without executing them.

    Args:
        rules: List of DispatchRule objects
        now: Current datetime
        state: Current dispatch state (last run times)
        max_delay: Maximum allowed delay for job execution

    Returns:
        List of DispatchRule objects that should be executed
    """
    jobs_to_run = []
    for rule in rules:
        last_run_str = state.get(rule.name)
        last_run = _parse_iso_datetime(last_run_str) if last_run_str else None
        if _should_run(rule, now, last_run, max_delay):
            jobs_to_run.append(rule)
    return jobs_to_run


def update_job_run_time(
    state: Dict[str, str],
    job_name: str,
    run_time: Optional[dt.datetime] = None
) -> Dict[str, str]:
    """Update the last run time for a job in the dispatch state.

    Args:
        state: Current dispatch state dictionary
        job_name: Name of the job to update
        run_time: Time of execution (defaults to current time)

    Returns:
        Updated state dictionary (modified in-place)
    """
    if run_time is None:
        run_time = dt.datetime.now(tz=sm.TAIWAN_TZ)
    state[job_name] = run_time.isoformat()
    return state




def _format_rules_for_print(rules: Sequence[DispatchRule]) -> str:
    payload = []
    for rule in rules:
        payload.append(
            {
                "name": rule.name,
                "time": rule.time.strftime("%H:%M"),
                "weekdays": rule.weekdays_label,
                "commands": [" ".join(cmd) for cmd in rule.commands],
            }
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)
