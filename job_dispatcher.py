#!/usr/bin/env python3
"""
Job dispatcher that fans out to cron-friendly scripts based on Taiwan time.

Usage:
    python job_dispatcher.py                 # run normally
    python job_dispatcher.py --dry-run       # log actions without executing
    python job_dispatcher.py --show-config   # print the active config (JSON)

The dispatcher can read custom rules from a JSON file (default:
`state/dispatch_rules.json`). When no file exists it falls back to defaults that
cover the daily send and weekly summary jobs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import schedule_manager as sm


DEFAULT_CONFIG_PATH = Path(os.getenv("DISPATCH_CONFIG", "state/dispatch_rules.json"))
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
        print(f"[dry-run] {display}")
        return
    print(f"[dispatcher] running: {display}")
    subprocess.run(cmd, check=True)


def dispatch(
    rules: Sequence[DispatchRule],
    now: dt.datetime,
    state: Dict[str, str],
    max_delay: dt.timedelta,
    dry_run: bool = False,
    runner=_run_command,
) -> List[str]:
    executed: List[str] = []
    for rule in rules:
        last_run = _parse_iso_datetime(state.get(rule.name))
        if not _should_run(rule, now, last_run, max_delay):
            continue
        for cmd in rule.commands:
            runner(cmd, dry_run)
        state[rule.name] = now.astimezone(sm.TAIWAN_TZ).isoformat()
        executed.append(rule.name)
    return executed


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


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dispatch scheduled jobs based on Taiwan time.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to JSON config.")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_PATH, help="Where to track last runs.")
    parser.add_argument(
        "--max-delay-minutes",
        type=int,
        default=180,
        help="Skip jobs that are older than this delay window.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Log actions without executing commands.")
    parser.add_argument("--show-config", action="store_true", help="Print the active rules and exit.")
    parser.add_argument("--now", type=str, help="Override the current time (ISO 8601 in Taiwan time).")
    return parser.parse_args(argv)


def _resolve_now(now_arg: Optional[str]) -> dt.datetime:
    if now_arg:
        parsed = dt.datetime.fromisoformat(now_arg)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=sm.TAIWAN_TZ)
        return parsed.astimezone(sm.TAIWAN_TZ)
    return dt.datetime.now(tz=sm.TAIWAN_TZ)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    now = _resolve_now(args.now)
    rules = load_rules(args.config)
    if args.show_config:
        print(_format_rules_for_print(rules))
        return 0

    state = load_state(args.state_file)
    max_delay = dt.timedelta(minutes=args.max_delay_minutes)
    try:
        executed = dispatch(rules, now, state, max_delay, dry_run=args.dry_run)
    except subprocess.CalledProcessError as exc:
        print(f"[dispatcher] command failed: {exc}", file=sys.stderr)
        return exc.returncode or 1

    if executed:
        save_state(args.state_file, state)
        print(f"[dispatcher] executed: {', '.join(executed)}")
    else:
        print("[dispatcher] no jobs due")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
