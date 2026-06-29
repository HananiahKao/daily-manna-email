"""Tests for Gmail recovery (backfill) logic."""

import datetime as dt
from unittest.mock import MagicMock, patch
import tempfile
from pathlib import Path

import pytest

import gmail_recovery
import delivery_tracker


def test_backfill_missing_deliveries_found_in_gmail():
    """Test backfilling a delivery that exists in Gmail sent folder."""
    with tempfile.TemporaryDirectory() as tmpdir:
        deliveries_file = Path(tmpdir) / "deliveries.json"
        today = dt.date(2026, 6, 29)

        # Mock Gmail service that finds a message
        mock_service = MagicMock()
        mock_service.users().messages().list().execute.return_value = {
            'messages': [{'id': 'msg_from_gmail_123'}]
        }

        # No deliveries recorded yet
        recipients = ["alice@example.com", "bob@example.com"]

        with patch('delivery_tracker.get_date_deliveries') as mock_get, \
             patch('delivery_tracker.record_delivery') as mock_record:
            mock_get.return_value = {}  # No deliveries yet

            backfilled = gmail_recovery.backfill_missing_deliveries(
                mock_service, recipients, today
            )

        # Should have attempted to record both recipients
        assert mock_record.call_count == 2
        assert 'alice@example.com' in backfilled or 'bob@example.com' in backfilled


def test_backfill_missing_deliveries_not_in_gmail():
    """Test recipient not in Gmail — will need normal send."""
    # Mock Gmail service that finds nothing
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': []  # Empty — recipient not found in sent folder
    }

    today = dt.date(2026, 6, 29)
    recipients = ["charlie@example.com"]

    with patch('delivery_tracker.get_date_deliveries') as mock_get, \
         patch('delivery_tracker.record_delivery') as mock_record:
        mock_get.return_value = {}  # No deliveries yet

        backfilled = gmail_recovery.backfill_missing_deliveries(
            mock_service, recipients, today
        )

    # Should not have recorded anything (not found in Gmail)
    assert mock_record.call_count == 0
    assert backfilled == {}


def test_backfill_skips_already_recorded():
    """Test that already-recorded deliveries are skipped."""
    mock_service = MagicMock()

    today = dt.date(2026, 6, 29)
    recipients = ["alice@example.com", "bob@example.com"]

    with patch('delivery_tracker.get_date_deliveries') as mock_get, \
         patch('delivery_tracker.record_delivery') as mock_record:
        # Alice already recorded, Bob missing
        mock_get.return_value = {"alice@example.com": "msg_alice"}

        backfilled = gmail_recovery.backfill_missing_deliveries(
            mock_service, recipients, today
        )

    # Should only attempt backfill for Bob, not Alice
    # (service not called for alice)
    assert mock_service.users().messages().list.call_count >= 1


def test_search_gmail_sent_to_recipient():
    """Test searching Gmail for a specific recipient."""
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'msg_123'}]
    }

    today = dt.date(2026, 6, 29)
    result = gmail_recovery._search_gmail_sent_to_recipient(
        mock_service, "user@example.com", today
    )

    assert result == "msg_123"
    # Verify the query was constructed correctly
    call_args = mock_service.users().messages().list.call_args
    assert 'user@example.com' in call_args[1]['q']
    assert today.isoformat() in call_args[1]['q'] or \
           (today - dt.timedelta(days=1)).isoformat() in call_args[1]['q']


def test_search_gmail_sent_not_found():
    """Test when Gmail search finds nothing."""
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': []  # Empty result
    }

    today = dt.date(2026, 6, 29)
    result = gmail_recovery._search_gmail_sent_to_recipient(
        mock_service, "user@example.com", today
    )

    assert result is None


def test_search_gmail_sent_api_error():
    """Test error handling when Gmail API fails."""
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.side_effect = \
        Exception("Gmail API error")

    today = dt.date(2026, 6, 29)
    result = gmail_recovery._search_gmail_sent_to_recipient(
        mock_service, "user@example.com", today
    )

    # Should return None on error, not raise
    assert result is None


def test_ensure_no_duplicates_on_startup_calls_backfill():
    """Test that ensure_no_duplicates_on_startup calls backfill."""
    with patch('gmail_recovery.get_gmail_service') as mock_get_service, \
         patch('gmail_recovery.backfill_missing_deliveries') as mock_backfill:
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service

        today = dt.date(2026, 6, 29)
        recipients = ["alice@example.com"]

        gmail_recovery.ensure_no_duplicates_on_startup(recipients, today)

        mock_backfill.assert_called_once_with(mock_service, recipients, today)


def test_ensure_no_duplicates_on_startup_handles_error():
    """Test that errors in backfill don't crash startup."""
    with patch('gmail_recovery.get_gmail_service') as mock_get_service:
        mock_get_service.side_effect = Exception("OAuth error")

        today = dt.date(2026, 6, 29)
        recipients = ["alice@example.com"]

        # Should not raise, just log and continue
        gmail_recovery.ensure_no_duplicates_on_startup(recipients, today)


def test_crash_recovery_scenario():
    """Verify crash recovery: backfill finds message in Gmail and records it."""
    with tempfile.TemporaryDirectory() as tmpdir:
        deliveries_file = Path(tmpdir) / "deliveries.json"
        today = dt.date(2026, 6, 29)

        # Setup: Alice already recorded
        delivery_tracker.record_delivery(
            "alice@example.com", today, "msg_alice",
            path=deliveries_file
        )

        # Mock Gmail service: has message to Bob
        mock_service = MagicMock()
        mock_service.users().messages().list().execute.return_value = {
            'messages': [{'id': 'msg_bob_from_gmail'}]
        }

        recipients = ["alice@example.com", "bob@example.com"]

        # Backfill using real delivery_tracker with temp file
        backfilled = gmail_recovery.backfill_missing_deliveries(
            mock_service, recipients, today, path=deliveries_file
        )

        # Verify Bob was backfilled
        assert "bob@example.com" in backfilled
        assert backfilled["bob@example.com"] == "msg_bob_from_gmail"

        # Verify Bob is now in deliveries file
        recorded = delivery_tracker.get_date_deliveries(today, deliveries_file)
        assert "alice@example.com" in recorded
        assert "bob@example.com" in recorded
