"""Integration test for crash recovery workflow.

Tests the end-to-end scenario: backfill missing records from Gmail,
then filter and send only to undelivered recipients.
"""

import datetime as dt
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import delivery_tracker
import gmail_recovery


def test_crash_recovery_scenario():
    """
    End-to-end crash recovery test.

    Scenario:
    1. Alice delivered and recorded (normal send)
    2. Bob was sent but NOT recorded (crash before recording)
    3. Charlie never sent

    On restart:
    1. Backfill queries Gmail, finds Bob
    2. Filter shows only Charlie needs sending
    3. Verify idempotency: no duplicates
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        deliveries_file = Path(tmpdir) / "deliveries.json"
        today = dt.date(2026, 6, 30)

        # Pre-crash state: Alice recorded
        delivery_tracker.record_delivery(
            "alice@example.com", today, "msg_alice",
            path=deliveries_file
        )

        # Create mock Gmail service
        mock_service = MagicMock()

        # Create a side effect for .list() that returns mock with configured execute
        def list_side_effect(userId=None, q=None, maxResults=None):
            mock_result = MagicMock()
            if 'alice@example.com' in (q or ''):
                mock_result.execute = MagicMock(return_value={'messages': [{'id': 'msg_alice_gmail'}]})
            elif 'bob@example.com' in (q or ''):
                mock_result.execute = MagicMock(return_value={'messages': [{'id': 'msg_bob_gmail'}]})
            else:
                mock_result.execute = MagicMock(return_value={'messages': []})
            return mock_result

        mock_service.users.return_value.messages.return_value.list.side_effect = list_side_effect

        # Backfill phase
        recipients = ["alice@example.com", "bob@example.com", "charlie@example.com"]
        backfilled = gmail_recovery.backfill_missing_deliveries(
            mock_service, recipients, today, path=deliveries_file
        )

        # Bob should be backfilled
        assert "bob@example.com" in backfilled
        assert backfilled["bob@example.com"] == "msg_bob_gmail"

        # Verify final state
        final = delivery_tracker.get_date_deliveries(today, deliveries_file)
        assert len(final) == 2  # Alice (original) + Bob (backfilled)
        assert "charlie@example.com" not in final

        # Filter phase: who needs sending?
        missing = delivery_tracker.get_missing_recipients(recipients, today, deliveries_file)
        assert missing == ["charlie@example.com"]  # Only Charlie needs sending


def test_crash_recovery_partial_gmail_recovery():
    """Test when only some crashed sends are in Gmail.

    Bob was sent but not recorded (in Gmail).
    Charlie was sent but not recorded (NOT in Gmail - failed send).
    Expected: Only Bob gets backfilled, Charlie still needs sending.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        deliveries_file = Path(tmpdir) / "deliveries.json"
        today = dt.date(2026, 6, 30)

        mock_service = MagicMock()

        def list_side_effect(userId=None, q=None, maxResults=None):
            mock_result = MagicMock()
            if 'bob@example.com' in (q or ''):
                mock_result.execute = MagicMock(return_value={'messages': [{'id': 'msg_bob_gmail'}]})
            else:
                mock_result.execute = MagicMock(return_value={'messages': []})
            return mock_result

        mock_service.users.return_value.messages.return_value.list.side_effect = list_side_effect

        recipients = ["bob@example.com", "charlie@example.com"]
        backfilled = gmail_recovery.backfill_missing_deliveries(
            mock_service, recipients, today, path=deliveries_file
        )

        # Only Bob backfilled
        assert len(backfilled) == 1
        assert "bob@example.com" in backfilled

        # Charlie still missing
        final = delivery_tracker.get_date_deliveries(today, deliveries_file)
        assert "bob@example.com" in final
        assert "charlie@example.com" not in final

        missing = delivery_tracker.get_missing_recipients(recipients, today, deliveries_file)
        assert "charlie@example.com" in missing


def test_idempotency_after_recovery():
    """Verify that after recovery, retry sends only to truly undelivered."""
    with tempfile.TemporaryDirectory() as tmpdir:
        deliveries_file = Path(tmpdir) / "deliveries.json"
        today = dt.date(2026, 6, 30)

        # Pre-backfill state
        delivery_tracker.record_delivery(
            "alice@example.com", today, "msg_alice",
            path=deliveries_file
        )

        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.execute = MagicMock(return_value={'messages': []})
        mock_service.users.return_value.messages.return_value.list.return_value = mock_result

        recipients = ["alice@example.com", "bob@example.com"]

        # First backfill (Alice already recorded, Bob missing)
        backfill1 = gmail_recovery.backfill_missing_deliveries(
            mock_service, recipients, today, path=deliveries_file
        )

        missing1 = delivery_tracker.get_missing_recipients(recipients, today, deliveries_file)
        assert missing1 == ["bob@example.com"]

        # Record Bob as sent
        delivery_tracker.record_delivery(
            "bob@example.com", today, "msg_bob",
            path=deliveries_file
        )

        # Second backfill (both already delivered)
        backfill2 = gmail_recovery.backfill_missing_deliveries(
            mock_service, recipients, today, path=deliveries_file
        )

        # No new backfills
        assert len(backfill2) == 0

        # No more missing
        missing2 = delivery_tracker.get_missing_recipients(recipients, today, deliveries_file)
        assert missing2 == []
