"""Fetch admin reply emails via IMAP and apply schedule updates."""

from __future__ import annotations

import datetime as dt
import imaplib
import json
import os
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import schedule_manager as sm
import schedule_reply as sr
import schedule_reply_processor as srp

try:  # pragma: no cover - only used when sending emails
    import sjzl_daily_email as sjzl
except Exception:  # pragma: no cover - optional dependency for confirmation mail
    sjzl = None


DEFAULT_IMAP_HOST = "imap.gmail.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_SUBJECT_KEYWORD = "Weekly Schedule"
RESULTS_ARCHIVE = Path("state/last_reply_results.json")


def _parse_address_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    addresses = []
    for _name, addr in getaddresses([value]):
        addr = (addr or "").strip().lower()
        if addr:
            addresses.append(addr)
    return addresses


def _html_escape(value: Optional[str]) -> str:
    if value is None:
        return ""
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def extract_text_body(message: EmailMessage) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() != "text/plain":
                continue
            if "attachment" in (part.get("Content-Disposition", "").lower()):
                continue
            try:
                return part.get_content()
            except Exception:  # pragma: no cover - defensive fallback
                continue
        try:
            return message.get_body(preferencelist=("plain", "html")).get_content()
        except Exception:  # pragma: no cover - defensive fallback
            pass
    try:
        return message.get_content()
    except Exception:  # pragma: no cover - defensive fallback
        return ""


@dataclass
class ImapConfig:
    host: str
    port: int
    username: str
    password: str
    mailbox: str
    allowed_senders: List[str]
    confirmation_recipients: List[str]
    subject_keyword: str
    subject_prefix: str

    @classmethod
    def from_env(cls) -> "ImapConfig":
        username = os.getenv("IMAP_USER") or os.getenv("SMTP_USER")
        password = os.getenv("IMAP_PASSWORD") or os.getenv("SMTP_PASSWORD")
        if not username or not password:
            raise RuntimeError("IMAP credentials are required (IMAP_USER/IMAP_PASSWORD or SMTP_USER/SMTP_PASSWORD)")
        host = os.getenv("IMAP_HOST", DEFAULT_IMAP_HOST)
        port_raw = os.getenv("IMAP_PORT")
        try:
            port = int(port_raw) if port_raw else DEFAULT_IMAP_PORT
        except ValueError as exc:
            raise RuntimeError("IMAP_PORT must be an integer") from exc
        mailbox = os.getenv("IMAP_MAILBOX", "INBOX")
        prefix = os.getenv("ADMIN_SUMMARY_SUBJECT_PREFIX", "[DailyManna]")
        keyword = os.getenv("ADMIN_REPLY_SUBJECT_KEYWORD", DEFAULT_SUBJECT_KEYWORD)
        allowed = _parse_address_list(os.getenv("ADMIN_REPLY_FROM"))
        if not allowed:
            allowed = _parse_address_list(os.getenv("ADMIN_SUMMARY_TO"))
        if not allowed:
            raise RuntimeError("ADMIN_REPLY_FROM or ADMIN_SUMMARY_TO must provide at least one allowed sender")
        recipients = _parse_address_list(os.getenv("ADMIN_REPLY_CONFIRMATION_TO"))
        if not recipients:
            recipients = _parse_address_list(os.getenv("ADMIN_SUMMARY_TO"))
        if not recipients:
            raise RuntimeError("ADMIN_REPLY_CONFIRMATION_TO or ADMIN_SUMMARY_TO must provide recipients")
        return cls(
            host=host,
            port=port,
            username=username,
            password=password,
            mailbox=mailbox,
            allowed_senders=allowed,
            confirmation_recipients=recipients,
            subject_keyword=keyword,
            subject_prefix=prefix,
        )


@dataclass
class ReplyProcessingRecord:
    uid: str
    subject: str
    from_address: str
    message_id: str
    received_at: Optional[dt.datetime]
    instruction_count: int
    applied_count: int
    error_count: int
    schedule_changed: bool
    confirmation_sent: bool
    outcomes: List[srp.InstructionOutcome] = field(default_factory=list)
    note: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "subject": self.subject,
            "from": self.from_address,
            "message_id": self.message_id,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "instruction_count": self.instruction_count,
            "applied_count": self.applied_count,
            "error_count": self.error_count,
            "schedule_changed": self.schedule_changed,
            "confirmation_sent": self.confirmation_sent,
            "note": self.note,
            "outcomes": [
                {
                    "token": item.token,
                    "verb": item.verb,
                    "status": item.status,
                    "message": item.message,
                    "date": item.date.isoformat() if item.date else None,
                }
                for item in self.outcomes
            ],
        }

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0 or (self.note is not None and self.note.strip())


@dataclass
class ProcessingSummary:
    run_at: dt.datetime
    records: List[ReplyProcessingRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_at": self.run_at.isoformat(),
            "processed": len(self.records),
            "applied": sum(rec.applied_count for rec in self.records),
            "errors": sum(rec.error_count for rec in self.records),
            "records": [rec.to_dict() for rec in self.records],
        }

    @property
    def error_count(self) -> int:
        return sum(1 for rec in self.records if rec.has_errors)


def _message_from_address(message: EmailMessage) -> str:
    addresses = _parse_address_list(message.get("From"))
    return addresses[0] if addresses else ""


def _message_date(message: EmailMessage) -> Optional[dt.datetime]:
    raw = message.get("Date")
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except Exception:  # pragma: no cover - fallback for malformed headers
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=sm.TAIWAN_TZ)
    return parsed


def _should_accept(message: EmailMessage, allowed_senders: Sequence[str], subject_keyword: str) -> bool:
    sender = _message_from_address(message)
    if sender and sender not in allowed_senders:
        return False
    subject = (message.get("Subject") or "").lower()
    if subject_keyword.lower() not in subject:
        return False
    return True


def _build_search_criteria(config: ImapConfig) -> Tuple[str, ...]:
    criteria: List[str] = ["UNSEEN"]
    if config.allowed_senders:
        sender = config.allowed_senders[0]
        criteria.append(f'FROM "{sender}"')
    if config.subject_keyword:
        criteria.append(f'SUBJECT "{config.subject_keyword}"')
    return tuple(criteria)


def build_confirmation_email(
    record: ReplyProcessingRecord,
    subject_prefix: str,
    schedule_path: Path,
) -> Tuple[str, str, str]:
    subject_core = record.subject or "Weekly schedule reply"
    subject = f"{subject_prefix} Reply Outcome - {subject_core}"
    lines: List[str] = []
    lines.append(f"Processed reply from {record.from_address or 'unknown'}")
    lines.append(f"Subject: {record.subject or '(no subject)'}")
    lines.append(f"Message-ID: {record.message_id or '(missing)'}")
    lines.append(f"Schedule file: {schedule_path}")
    lines.append("")
    if record.outcomes:
        lines.append("Results:")
        for outcome in record.outcomes:
            date_info = f" @ {outcome.date.isoformat()}" if outcome.date else ""
            lines.append(
                f"- [{outcome.token}] {outcome.verb}: {outcome.status}{date_info} -> {outcome.message}"
            )
    else:
        lines.append("No commands detected in the reply body.")
    if record.note:
        lines.append("")
        lines.append(f"Note: {record.note}")
    lines.append("")
    if record.schedule_changed:
        lines.append("Schedule file updated.")
    else:
        lines.append("No schedule changes were required.")
    text_body = "\n".join(lines)

    escaped_subject = _html_escape(record.subject or "(no subject)")
    escaped_from = _html_escape(record.from_address or "unknown")
    escaped_schedule = _html_escape(str(schedule_path))
    rows = []
    for outcome in record.outcomes:
        rows.append(
            "<tr>"
            f"<td>{_html_escape(outcome.token)}</td>"
            f"<td>{_html_escape(outcome.verb)}</td>"
            f"<td>{_html_escape(outcome.status)}</td>"
            f"<td>{_html_escape(outcome.message)}</td>"
            f"<td>{_html_escape(outcome.date.isoformat() if outcome.date else '')}</td>"
            "</tr>"
        )
    rows_html = "\n".join(rows) if rows else "<tr><td colspan='5'>No commands detected.</td></tr>"
    note_html = f"<p><strong>Note:</strong> {_html_escape(record.note)}</p>" if record.note else ""
    change_html = "<p>Schedule file updated.</p>" if record.schedule_changed else "<p>No schedule changes were required.</p>"
    html_body = (
        "<!doctype html>\n"
        "<html><head><meta charset='utf-8'>"
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;padding:16px;}"
        "table{border-collapse:collapse;width:100%;}" \
        "th,td{border:1px solid #ddd;padding:8px;text-align:left;}" \
        "th{background:#f4f4f4;}</style></head><body>"
        f"<h2>Reply Outcome</h2><p><strong>From:</strong> {escaped_from}<br><strong>Subject:</strong> {escaped_subject}</p>"
        f"<p><strong>Schedule file:</strong> <code>{escaped_schedule}</code></p>"
        "<table><thead><tr><th>Token</th><th>Verb</th><th>Status</th><th>Message</th><th>Date</th></tr></thead><tbody>"
        f"{rows_html}</tbody></table>"
        f"{note_html}{change_html}"
        "</body></html>"
    )
    return subject, text_body, html_body


def _send_admin_email(recipients: Sequence[str], subject: str, text_body: str, html_body: str) -> None:
    if not recipients:
        return
    if sjzl is None:
        raise RuntimeError("sjzl_daily_email import failed; cannot send confirmation email")
    original_email_to = os.environ.get("EMAIL_TO")
    original_email_from = os.environ.get("EMAIL_FROM")
    admin_from = os.getenv("ADMIN_SUMMARY_FROM")
    try:
        os.environ["EMAIL_TO"] = ",".join(recipients)
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


def _mark_seen(imap: imaplib.IMAP4_SSL, uid: bytes, dry_run: bool) -> None:
    if dry_run:
        return
    try:
        imap.uid("STORE", uid, "+FLAGS", "(\\Seen)")
    except Exception:  # pragma: no cover - IMAP errors are logged but not fatal
        pass


def _fetch_message(imap: imaplib.IMAP4_SSL, uid: bytes) -> Optional[EmailMessage]:
    try:
        status, payload = imap.uid("FETCH", uid, "(RFC822)")
    except Exception:
        return None
    if status != "OK" or not payload:
        return None
    for part in payload:
        if isinstance(part, tuple) and part[1]:
            parser = BytesParser(policy=policy.default)
            try:
                return parser.parsebytes(part[1])
            except Exception:
                return None
    return None


def process_mailbox(
    config: ImapConfig,
    *,
    limit: int = 20,
    dry_run: bool = False,
    schedule_path: Optional[Path] = None,
    now: Optional[dt.datetime] = None,
) -> ProcessingSummary:
    schedule_path = schedule_path or sm.get_schedule_path()
    schedule = sm.load_schedule(schedule_path)
    summary = ProcessingSummary(run_at=now or dt.datetime.now(tz=sm.TAIWAN_TZ))
    imap = imaplib.IMAP4_SSL(config.host, config.port)
    imap.login(config.username, config.password)
    try:
        imap.select(config.mailbox)
        criteria = _build_search_criteria(config)
        status, data = imap.uid("SEARCH", None, *criteria)
        if status != "OK":
            return summary
        uids = [uid for uid in (data[0].split() if data else []) if uid]
        schedule_dirty = False
        for uid in uids[: max(0, limit)]:
            message = _fetch_message(imap, uid)
            if message is None:
                _mark_seen(imap, uid, dry_run)
                continue
            if not _should_accept(message, config.allowed_senders, config.subject_keyword):
                _mark_seen(imap, uid, dry_run)
                continue
            body = extract_text_body(message)
            subject = message.get("Subject") or ""
            from_address = _message_from_address(message)
            message_id = message.get("Message-ID", "")
            received_at = _message_date(message)
            record = ReplyProcessingRecord(
                uid=uid.decode("utf-8", errors="ignore"),
                subject=subject,
                from_address=from_address,
                message_id=message_id,
                received_at=received_at,
                instruction_count=0,
                applied_count=0,
                error_count=0,
                schedule_changed=False,
                confirmation_sent=False,
            )
            if not body.strip():
                record.note = "Email body was empty; nothing to process."
                summary.records.append(record)
                _mark_seen(imap, uid, dry_run)
                continue
            try:
                instructions = sr.parse_reply_body(body)
            except sr.ParseError as exc:
                record.note = str(exc)
                record.error_count = 1
                summary.records.append(record)
                _mark_seen(imap, uid, dry_run)
                _send_confirmation(config, record, schedule_path, dry_run)
                continue
            result = srp.apply_instructions(schedule, instructions, now=now)
            record.outcomes = result.outcomes
            record.instruction_count = len(instructions)
            record.applied_count = sum(1 for item in result.outcomes if item.status == "applied")
            record.error_count = sum(1 for item in result.outcomes if item.status == "error")
            if result.outcomes:
                schedule_dirty = True
            record.schedule_changed = result.changed or bool(result.outcomes)
            summary.records.append(record)
            _mark_seen(imap, uid, dry_run)
            _send_confirmation(config, record, schedule_path, dry_run)
        if schedule_dirty and not dry_run:
            sm.save_schedule(schedule, schedule_path)
        if summary.records and not dry_run:
            RESULTS_ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
            RESULTS_ARCHIVE.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finally:
        try:
            imap.logout()
        except Exception:  # pragma: no cover - safe shutdown
            pass
    return summary


def _send_confirmation(config: ImapConfig, record: ReplyProcessingRecord, schedule_path: Path, dry_run: bool) -> None:
    if dry_run:
        record.confirmation_sent = False
        return
    try:
        subject, text_body, html_body = build_confirmation_email(record, config.subject_prefix, schedule_path)
        _send_admin_email(config.confirmation_recipients, subject, text_body, html_body)
        record.confirmation_sent = True
    except Exception as exc:  # pragma: no cover - send failures should not crash the run
        record.confirmation_sent = False
        record.note = (record.note or "") + f" Confirmation email failed: {exc}"


__all__ = [
    "ImapConfig",
    "ProcessingSummary",
    "ReplyProcessingRecord",
    "build_confirmation_email",
    "extract_text_body",
    "process_mailbox",
]

