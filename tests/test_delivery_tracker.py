"""Tests for delivery tracking system."""

import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import delivery_tracker


@pytest.fixture
def temp_deliveries_file(tmp_path):
    """Fixture providing a temporary deliveries file path."""
    deliveries_file = tmp_path / "deliveries.json"
    return deliveries_file


def test_check_delivery_not_found(temp_deliveries_file):
    """Test checking delivery when file doesn't exist."""
    result = delivery_tracker.check_delivery("user@example.com", dt.date(2026, 6, 29), temp_deliveries_file)
    assert result is None


def test_check_delivery_date_not_found(temp_deliveries_file):
    """Test checking delivery when date has no records."""
    # Create file with different date
    deliveries = {
        "2026-06-28": {
            "user@example.com": {
                "message_id": "msg_123",
                "sent_at": "2026-06-28T06:00:00+08:00"
            }
        }
    }
    temp_deliveries_file.parent.mkdir(parents=True, exist_ok=True)
    temp_deliveries_file.write_text(json.dumps(deliveries))

    result = delivery_tracker.check_delivery("user@example.com", dt.date(2026, 6, 29), temp_deliveries_file)
    assert result is None


def test_check_delivery_recipient_not_found(temp_deliveries_file):
    """Test checking delivery when recipient has no record for that date."""
    deliveries = {
        "2026-06-29": {
            "other@example.com": {
                "message_id": "msg_123",
                "sent_at": "2026-06-29T06:00:00+08:00"
            }
        }
    }
    temp_deliveries_file.parent.mkdir(parents=True, exist_ok=True)
    temp_deliveries_file.write_text(json.dumps(deliveries))

    result = delivery_tracker.check_delivery("user@example.com", dt.date(2026, 6, 29), temp_deliveries_file)
    assert result is None


def test_check_delivery_found(temp_deliveries_file):
    """Test checking delivery when record exists."""
    deliveries = {
        "2026-06-29": {
            "user@example.com": {
                "message_id": "msg_abc123",
                "sent_at": "2026-06-29T06:00:15+08:00"
            }
        }
    }
    temp_deliveries_file.parent.mkdir(parents=True, exist_ok=True)
    temp_deliveries_file.write_text(json.dumps(deliveries))

    result = delivery_tracker.check_delivery("user@example.com", dt.date(2026, 6, 29), temp_deliveries_file)
    assert result == "msg_abc123"


def test_record_delivery_creates_file(temp_deliveries_file):
    """Test recording delivery creates file and structure."""
    sent_at = dt.datetime(2026, 6, 29, 6, 0, 15, tzinfo=dt.timezone.utc)

    delivery_tracker.record_delivery(
        "user@example.com",
        dt.date(2026, 6, 29),
        "msg_xyz789",
        sent_at=sent_at,
        path=temp_deliveries_file
    )

    assert temp_deliveries_file.exists()
    data = json.loads(temp_deliveries_file.read_text())

    assert "2026-06-29" in data
    assert "user@example.com" in data["2026-06-29"]
    assert data["2026-06-29"]["user@example.com"]["message_id"] == "msg_xyz789"
    assert data["2026-06-29"]["user@example.com"]["sent_at"] == "2026-06-29T06:00:15+00:00"


def test_record_delivery_idempotent(temp_deliveries_file):
    """Test recording same delivery twice is idempotent."""
    sent_at = dt.datetime(2026, 6, 29, 6, 0, 15, tzinfo=dt.timezone.utc)

    # Record once
    delivery_tracker.record_delivery(
        "user@example.com",
        dt.date(2026, 6, 29),
        "msg_xyz789",
        sent_at=sent_at,
        path=temp_deliveries_file
    )

    # Record again with same values
    delivery_tracker.record_delivery(
        "user@example.com",
        dt.date(2026, 6, 29),
        "msg_xyz789",
        sent_at=sent_at,
        path=temp_deliveries_file
    )

    # Should still have exactly one entry
    data = json.loads(temp_deliveries_file.read_text())
    assert len(data["2026-06-29"]) == 1
    assert data["2026-06-29"]["user@example.com"]["message_id"] == "msg_xyz789"


def test_record_delivery_multiple_recipients(temp_deliveries_file):
    """Test recording deliveries for multiple recipients on same date."""
    sent_at1 = dt.datetime(2026, 6, 29, 6, 0, 15, tzinfo=dt.timezone.utc)
    sent_at2 = dt.datetime(2026, 6, 29, 6, 0, 16, tzinfo=dt.timezone.utc)

    delivery_tracker.record_delivery(
        "user1@example.com",
        dt.date(2026, 6, 29),
        "msg_123",
        sent_at=sent_at1,
        path=temp_deliveries_file
    )

    delivery_tracker.record_delivery(
        "user2@example.com",
        dt.date(2026, 6, 29),
        "msg_456",
        sent_at=sent_at2,
        path=temp_deliveries_file
    )

    data = json.loads(temp_deliveries_file.read_text())
    assert len(data["2026-06-29"]) == 2
    assert data["2026-06-29"]["user1@example.com"]["message_id"] == "msg_123"
    assert data["2026-06-29"]["user2@example.com"]["message_id"] == "msg_456"


def test_get_date_deliveries_empty(temp_deliveries_file):
    """Test getting deliveries for date with no records."""
    result = delivery_tracker.get_date_deliveries(dt.date(2026, 6, 29), temp_deliveries_file)
    assert result == {}


def test_get_date_deliveries_with_records(temp_deliveries_file):
    """Test getting deliveries for date with records."""
    deliveries = {
        "2026-06-29": {
            "user1@example.com": {
                "message_id": "msg_123",
                "sent_at": "2026-06-29T06:00:15+08:00"
            },
            "user2@example.com": {
                "message_id": "msg_456",
                "sent_at": "2026-06-29T06:00:16+08:00"
            }
        }
    }
    temp_deliveries_file.parent.mkdir(parents=True, exist_ok=True)
    temp_deliveries_file.write_text(json.dumps(deliveries))

    result = delivery_tracker.get_date_deliveries(dt.date(2026, 6, 29), temp_deliveries_file)
    assert result == {
        "user1@example.com": "msg_123",
        "user2@example.com": "msg_456"
    }


def test_get_missing_recipients_all_missing(temp_deliveries_file):
    """Test getting missing recipients when none have been sent to."""
    all_recipients = ["user1@example.com", "user2@example.com", "user3@example.com"]

    result = delivery_tracker.get_missing_recipients(
        all_recipients,
        dt.date(2026, 6, 29),
        temp_deliveries_file
    )

    assert result == all_recipients


def test_get_missing_recipients_some_delivered(temp_deliveries_file):
    """Test getting missing recipients when some have been delivered."""
    deliveries = {
        "2026-06-29": {
            "user1@example.com": {
                "message_id": "msg_123",
                "sent_at": "2026-06-29T06:00:15+08:00"
            }
        }
    }
    temp_deliveries_file.parent.mkdir(parents=True, exist_ok=True)
    temp_deliveries_file.write_text(json.dumps(deliveries))

    all_recipients = ["user1@example.com", "user2@example.com", "user3@example.com"]

    result = delivery_tracker.get_missing_recipients(
        all_recipients,
        dt.date(2026, 6, 29),
        temp_deliveries_file
    )

    assert set(result) == {"user2@example.com", "user3@example.com"}


def test_get_missing_recipients_all_delivered(temp_deliveries_file):
    """Test getting missing recipients when all have been delivered."""
    deliveries = {
        "2026-06-29": {
            "user1@example.com": {"message_id": "msg_123", "sent_at": "2026-06-29T06:00:15+08:00"},
            "user2@example.com": {"message_id": "msg_456", "sent_at": "2026-06-29T06:00:16+08:00"},
            "user3@example.com": {"message_id": "msg_789", "sent_at": "2026-06-29T06:00:17+08:00"}
        }
    }
    temp_deliveries_file.parent.mkdir(parents=True, exist_ok=True)
    temp_deliveries_file.write_text(json.dumps(deliveries))

    all_recipients = ["user1@example.com", "user2@example.com", "user3@example.com"]

    result = delivery_tracker.get_missing_recipients(
        all_recipients,
        dt.date(2026, 6, 29),
        temp_deliveries_file
    )

    assert result == []


def test_load_deliveries_missing_file():
    """Test loading deliveries when file doesn't exist."""
    result = delivery_tracker.load_deliveries(Path("/nonexistent/path/deliveries.json"))
    assert result == {}


def test_save_and_load_roundtrip(temp_deliveries_file):
    """Test saving and loading deliveries preserves data."""
    original = {
        "2026-06-29": {
            "user@example.com": {
                "message_id": "msg_123",
                "sent_at": "2026-06-29T06:00:15+08:00"
            }
        }
    }

    delivery_tracker.save_deliveries(original, temp_deliveries_file)
    loaded = delivery_tracker.load_deliveries(temp_deliveries_file)

    assert loaded == original
