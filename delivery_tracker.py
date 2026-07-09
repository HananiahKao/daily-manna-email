"""Delivery tracking system for per-recipient email sending with idempotent recovery.

This module manages delivery records in JSON format with structure:
  state/deliveries.json:
  {
    "2026-06-29": {
      "user@example.com": {
        "message_id": "18c...",
        "sent_at": "2026-06-29T06:00:15.123456+08:00"
      }
    }
  }

Provides:
- check_delivery(recipient, date) → returns message_id if already sent, None otherwise
- record_delivery(recipient, date, message_id, sent_at) → idempotent write
- get_date_deliveries(date) → all deliveries for a date
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_DELIVERIES_FILE = "state/deliveries.json"


def get_deliveries_path() -> Path:
    """Return path to the deliveries file, respecting env override."""
    base = os.environ.get("DELIVERIES_FILE", DEFAULT_DELIVERIES_FILE)
    return (Path(os.getcwd()) / base).resolve()


def load_deliveries(path: Optional[Path] = None) -> Dict[str, Dict[str, Dict]]:
    """Load deliveries JSON from disk, returning empty dict when missing."""
    path = path or get_deliveries_path()
    if not path.exists():
        return {}
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            logger.warning("Deliveries file root is not an object, treating as empty")
            return {}
        return data
    except Exception as e:
        logger.error("Failed to load deliveries: %s", e)
        return {}


def save_deliveries(deliveries: Dict[str, Dict[str, Dict]], path: Optional[Path] = None) -> None:
    """Persist deliveries to disk."""
    path = path or get_deliveries_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        payload = json.dumps(deliveries, ensure_ascii=False, indent=2)
        path.write_text(payload + "\n", encoding="utf-8")
    except Exception as e:
        logger.error("Failed to save deliveries: %s", e)
        raise


def check_delivery(recipient: str, date: dt.date, path: Optional[Path] = None) -> Optional[str]:
    """Check if an email was already sent to recipient on this date.

    Args:
        recipient: Email address of recipient
        date: Date of the send (as dt.date)
        path: Optional path override for testing

    Returns:
        Gmail message ID if already sent, None otherwise
    """
    date_str = date.isoformat()
    deliveries = load_deliveries(path)

    if date_str not in deliveries:
        return None

    if recipient not in deliveries[date_str]:
        return None

    record = deliveries[date_str][recipient]
    return record.get("message_id")


def record_delivery(
    recipient: str,
    date: dt.date,
    message_id: str,
    sent_at: Optional[dt.datetime] = None,
    path: Optional[Path] = None,
) -> None:
    """Record a successful email delivery for idempotent retry.

    Args:
        recipient: Email address of recipient
        date: Date of the send (as dt.date)
        message_id: Gmail message ID from API response
        sent_at: Timestamp of send (defaults to now)
        path: Optional path override for testing

    Note: Idempotent - safe to call multiple times with same values.
    """
    date_str = date.isoformat()
    sent_at = sent_at or dt.datetime.now(dt.timezone.utc)
    sent_at_iso = sent_at.isoformat()

    deliveries = load_deliveries(path)

    # Initialize date entry if missing
    if date_str not in deliveries:
        deliveries[date_str] = {}

    # Write record (idempotent - same message_id and sent_at)
    deliveries[date_str][recipient] = {
        "message_id": message_id,
        "sent_at": sent_at_iso
    }

    save_deliveries(deliveries, path)
    logger.info("Recorded delivery on %s, message_id=%s", date_str, message_id)


def get_date_deliveries(date: dt.date, path: Optional[Path] = None) -> Dict[str, str]:
    """Get all successfully delivered recipients for a date.

    Args:
        date: Target date (as dt.date)
        path: Optional path override for testing

    Returns:
        Dict of {recipient: message_id} for all deliveries on that date
    """
    date_str = date.isoformat()
    deliveries = load_deliveries(path)

    if date_str not in deliveries:
        return {}

    # Map recipients to their message IDs
    result = {}
    for recipient, record in deliveries[date_str].items():
        if "message_id" in record:
            result[recipient] = record["message_id"]

    return result


def get_missing_recipients(
    all_recipients: list[str],
    date: dt.date,
    path: Optional[Path] = None,
) -> list[str]:
    """Get recipients from list that have NOT been sent to on this date.

    Args:
        all_recipients: Full list of recipients to check
        date: Target date (as dt.date)
        path: Optional path override for testing

    Returns:
        List of recipients that need to be sent to (not yet delivered)
    """
    delivered = get_date_deliveries(date, path)
    return [r for r in all_recipients if r not in delivered]


def cleanup_old_deliveries(days: int = 7, path: Optional[Path] = None) -> int:
    """Remove delivery records older than specified days (default 7).

    Args:
        days: Number of days to retain (default 7)
        path: Optional path override for testing

    Returns:
        Number of dates removed
    """
    path = path or get_deliveries_path()
    deliveries = load_deliveries(path)

    cutoff_date = dt.date.today() - dt.timedelta(days=days)
    cutoff_str = cutoff_date.isoformat()

    dates_to_remove = [date_str for date_str in deliveries.keys() if date_str < cutoff_str]

    for date_str in dates_to_remove:
        del deliveries[date_str]
        logger.info("Cleaned up delivery records for %s", date_str)

    if dates_to_remove:
        save_deliveries(deliveries, path)

    return len(dates_to_remove)


__all__ = [
    "check_delivery",
    "record_delivery",
    "get_date_deliveries",
    "get_missing_recipients",
    "load_deliveries",
    "save_deliveries",
    "get_deliveries_path",
    "cleanup_old_deliveries",
]
