#!/usr/bin/env python3
"""Command-line helpers for managing the EZOe send schedule."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import schedule_manager as sm
import schedule_reply as sr
import schedule_reply_processor as srp

try:
    import sjzl_daily_email as sjzl
except Exception:  # pragma: no cover - only needed for email summary
    sjzl = None


SUMMARY_ARCHIVE = Path("state/last_schedule_summary.html")
SKIP_STATUSES = {"sent", "skipped"}


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return value not in ("", "0", "false", "False", "no", "No")


def _next_monday(today: dt.date) -> dt.date:
    delta = (7 - today.weekday()) % 7
    if delta == 0:
        delta = 7
    return today + dt.timedelta(days=delta)


def _entries_for_range(schedule: sm.Schedule, start: dt.date, end: dt.date) -> List[sm.ScheduleEntry]:
    days = (end - start).days + 1
    return [schedule.get_entry(start + dt.timedelta(days=i)) for i in range(days)]


def _render_plain(
    entries: Sequence[sm.ScheduleEntry],
    schedule_path: Path,
    tokens: Optional[Dict[str, str]] = None,
) -> str:
    lines: List[str] = []
    lines.append(f"Schedule file: {schedule_path}")
    lines.append("Edit selectors or notes directly in the JSON as needed before send.")
    if tokens:
        lines.append("Reply with commands like '[TOKEN] move 2025-06-03' to update entries (beta).")
    lines.append("")
    token_map = tokens or {}
    for entry in entries:
        if entry is None:
            continue
        weekday = sm.WEEKDAY_TW[entry.date.weekday()]
        status = entry.status
        notes = f" notes={entry.notes}" if entry.notes else ""
        override = f" override={entry.override}" if entry.override else ""
        sent = f" sent_at={entry.sent_at}" if entry.sent_at else ""
        token_display = ""
        token = token_map.get(entry.date.isoformat())
        if token:
            token_display = f" token={token}"
        lines.append(
            f"{entry.date.isoformat()} ({weekday}) selector={entry.selector} status={status}{sent}{notes}{override}{token_display}"
        )
    return "\n".join(lines)


def _render_html(
    entries: Sequence[sm.ScheduleEntry],
    schedule_path: Path,
    tokens: Optional[Dict[str, str]] = None,
) -> str:
    def esc(value: Optional[str]) -> str:
        return html.escape(value or "", quote=False)

    rows = []
    token_map = tokens or {}
    for entry in entries:
        if entry is None:
            continue
        weekday = sm.WEEKDAY_TW[entry.date.weekday()]
        notes = esc(entry.notes)
        override = esc(entry.override)
        token = esc(token_map.get(entry.date.isoformat()))
        rows.append(
            "<tr>"
            f"<td>{esc(entry.date.isoformat())}</td>"
            f"<td>{esc(weekday)}</td>"
            f"<td>{esc(entry.selector)}</td>"
            f"<td>{esc(entry.status)}</td>"
            f"<td>{esc(entry.sent_at)}</td>"
            f"<td>{notes}</td>"
            f"<td>{override}</td>"
            f"<td>{token}</td>"
            "</tr>"
        )
    rows_html = "\n".join(rows)
    schedule_display = esc(str(schedule_path))
    return (
        "<!doctype html>\n"
        "<html><head><meta charset='utf-8'>"
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:16px;}"
        "table{border-collapse:collapse;width:100%;}" \
        "th,td{border:1px solid #ddd;padding:8px;text-align:left;}" \
        "th{background:#f4f4f4;}" \
        "code{font-size:0.95em;}</style></head><body>"
        f"<h2>Upcoming Week Schedule</h2><p>Edit <code>{schedule_display}</code> if adjustments are needed before sends.</p>"
        "<p><strong>Reply editing (beta):</strong> Reply with lines like <code>[TOKEN] move 2025-06-03</code> to adjust entries.</p>"
        "<table><thead><tr><th>Date</th><th>Weekday</th><th>Selector</th><th>Status</th><th>Sent At</th><th>Notes</th><th>Override</th><th>Token</th>" \
        "</tr></thead><tbody>"
        f"{rows_html}" "</tbody></table></body></html>"
    )


def _send_summary_email(subject: str, text_body: str, html_body: str) -> None:
    if sjzl is None:
        raise RuntimeError("sjzl_daily_email import failed; cannot send summary email")

    admin_to = os.getenv("ADMIN_SUMMARY_TO")
    if not admin_to:
        raise RuntimeError("ADMIN_SUMMARY_TO is not set; cannot send summary email")

    original_email_to = os.environ.get("EMAIL_TO")
    original_email_from = os.environ.get("EMAIL_FROM")

    admin_from = os.getenv("ADMIN_SUMMARY_FROM")

    try:
        os.environ["EMAIL_TO"] = admin_to
        if admin_from:
            os.environ["EMAIL_FROM"] = admin_from
        sjzl.send_email(subject, text_body, html_body=html_body)
    finally:
        if original_email_to is None:
            os.environ.pop("EMAIL_TO", None)
        else:
            os.environ["EMAIL_TO"] = original_email_to

        if admin_from:
            if original_email_from is None:
                os.environ.pop("EMAIL_FROM", None)
            else:
                os.environ["EMAIL_FROM"] = original_email_from


def _handle_next_entry(args: argparse.Namespace) -> int:
    schedule_path = sm.get_schedule_path()
    schedule = sm.load_schedule(schedule_path)

    descriptor = args.date or os.getenv("EZOE_SEND_DATE") or os.getenv("EZOE_SEND_WEEKDAY")
    today = sm.taipei_today()
    target_date = sm.parse_date_descriptor(descriptor, today=today) if descriptor else today

    changed = sm.ensure_date_range(schedule, target_date, target_date)
    if changed:
        sm.save_schedule(schedule, schedule_path)

    entry = schedule.get_entry(target_date)
    if entry is None:
        print(json.dumps({"error": "failed_to_create_entry", "date": target_date.isoformat()}))
        return 1

    force = _truthy(os.getenv("RUN_FORCE"))
    include_sent = force or args.include_sent
    if entry.status in SKIP_STATUSES and not include_sent:
        payload = {
            "skip": True,
            "reason": "already_sent" if entry.status == "sent" else entry.status,
            "date": entry.date.isoformat(),
            "selector": entry.selector,
            "status": entry.status,
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    # Adapt selector to active content source if needed
    selector = entry.selector
    content_source = os.getenv("CONTENT_SOURCE", "ezoe").lower()
    if content_source == "wix":
        # Convert entry.date to Chinese weekday selector
        weekday = entry.date.weekday()  # 0=Monday, 7=Sunday
        chinese_weekday_map = ["週一", "週二", "週三", "週四", "週五", "週六", "主日"]
        selector = f"【{chinese_weekday_map[weekday]}】"

    payload = {
        "date": entry.date.isoformat(),
        "weekday": sm.WEEKDAY_TW[entry.date.weekday()],
        "selector": selector,
        "schedule_file": str(schedule_path),
        "status": entry.status,
        "resend": entry.status == "sent",
        "content_source": content_source,
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def _handle_mark_sent(args: argparse.Namespace) -> int:
    schedule_path = sm.get_schedule_path()
    schedule = sm.load_schedule(schedule_path)

    today = sm.taipei_today()
    target_date = sm.parse_date_descriptor(args.date, today=today)
    sm.mark_sent(schedule, target_date)
    sm.save_schedule(schedule, schedule_path)
    payload = {
        "date": target_date.isoformat(),
        "status": "sent",
        "schedule_file": str(schedule_path),
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def _handle_ensure_week(args: argparse.Namespace) -> int:
    schedule_path = sm.get_schedule_path()
    schedule = sm.load_schedule(schedule_path)

    today = sm.taipei_today()
    if args.start:
        start_candidate = sm.parse_date_descriptor(args.start, today=today)
        start = start_candidate - dt.timedelta(days=start_candidate.weekday())
    else:
        start = _next_monday(today)
    end = start + dt.timedelta(days=6)

    changed = sm.ensure_date_range(schedule, start, end)

    entries = [entry for entry in _entries_for_range(schedule, start, end) if entry]

    meta_changed = False
    removed = sr.purge_expired_tokens(schedule)
    if removed:
        meta_changed = True

    token_records = []
    token_map: Dict[str, str] = {}
    if entries:
        summary_id = f"{start.isoformat()}_{end.isoformat()}"
        token_records = sr.issue_reply_tokens(schedule, entries, summary_id=summary_id)
        if token_records:
            meta_changed = True
            token_map = {record.date.isoformat(): record.token for record in token_records}

    if changed or meta_changed:
        sm.save_schedule(schedule, schedule_path)

    text_body = _render_plain(entries, schedule_path, tokens=token_map)
    html_body = _render_html(entries, schedule_path, tokens=token_map)

    SUMMARY_ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_ARCHIVE.write_text(html_body, encoding="utf-8")

    prefix = os.getenv("ADMIN_SUMMARY_SUBJECT_PREFIX", "[DailyManna]")
    subject = f"{prefix} Weekly Schedule {start.isoformat()} – {end.isoformat()}"

    emailed = False
    if args.email:
        try:
            _send_summary_email(subject, text_body, html_body)
            emailed = True
        except RuntimeError as exc:
            print(f"WARNING: {exc}", file=sys.stderr)
        except Exception as exc:
            print(f"ERROR: failed to send summary email: {exc}", file=sys.stderr)

    payload = {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "changed": changed,
        "schedule_file": str(schedule_path),
        "emailed": emailed,
        "token_count": len(token_records),
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def _handle_apply_reply(args: argparse.Namespace) -> int:
    schedule_path = sm.get_schedule_path()
    schedule = sm.load_schedule(schedule_path)

    if args.input:
        body = Path(args.input).read_text(encoding="utf-8")
    else:
        body = sys.stdin.read()

    if not body.strip():
        print(json.dumps({"error": "empty_input", "schedule_file": str(schedule_path)}))
        return 1

    result = srp.process_email(schedule, body)
    if result.changed:
        sm.save_schedule(schedule, schedule_path)

    payload = result.to_dict()
    payload["schedule_file"] = str(schedule_path)
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if not result.errors else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Schedule management commands")
    sub = parser.add_subparsers(dest="command", required=True)

    next_cmd = sub.add_parser("next-entry", help="Determine selector for a given date")
    next_cmd.add_argument("--date", help="ISO date or weekday descriptor (e.g., 周三, Tue)")
    next_cmd.add_argument("--include-sent", action="store_true", help="Return entry even if already sent")
    next_cmd.set_defaults(func=_handle_next_entry)

    mark_cmd = sub.add_parser("mark-sent", help="Mark a given date as sent")
    mark_cmd.add_argument("--date", required=True, help="ISO date or weekday descriptor")
    mark_cmd.set_defaults(func=_handle_mark_sent)

    ensure_cmd = sub.add_parser("ensure-week", help="Ensure upcoming week entries and optionally email summary")
    ensure_cmd.add_argument("--start", help="Start date override (ISO or descriptor); Monday of that week is used")
    ensure_cmd.add_argument("--email", action="store_true", help="Send admin summary email")
    ensure_cmd.set_defaults(func=_handle_ensure_week)

    apply_cmd = sub.add_parser("apply-reply", help="Apply admin reply commands from an email body")
    apply_cmd.add_argument("--input", help="Path to file containing the email body (defaults to stdin)")
    apply_cmd.set_defaults(func=_handle_apply_reply)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
