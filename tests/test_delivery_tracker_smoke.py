"""Smoke tests for delivery tracker with real file I/O (no mocks).

These tests verify the delivery tracking system actually works with real files,
not just with mocked I/O. Useful for verifying the system isn't broken by
import errors or basic runtime issues.
"""

import datetime as dt
import tempfile
from pathlib import Path

import delivery_tracker


def test_smoke_delivery_tracker_workflow():
    """Real workflow: create deliveries, filter, check without any mocks."""
    with tempfile.TemporaryDirectory() as tmpdir:
        deliveries_file = Path(tmpdir) / "deliveries.json"
        today = dt.date(2026, 6, 29)

        # Step 1: Check no deliveries exist yet
        assert delivery_tracker.check_delivery("alice@example.com", today, deliveries_file) is None
        assert delivery_tracker.get_missing_recipients(
            ["alice@example.com", "bob@example.com"], today, deliveries_file
        ) == ["alice@example.com", "bob@example.com"]

        # Step 2: Record Alice's delivery
        delivery_tracker.record_delivery(
            "alice@example.com",
            today,
            "msg_123",
            sent_at=dt.datetime(2026, 6, 29, 6, 0, 15, tzinfo=dt.timezone.utc),
            path=deliveries_file
        )

        # Step 3: Verify file was created and contains data
        assert deliveries_file.exists()
        content = deliveries_file.read_text()
        assert "alice@example.com" in content
        assert "msg_123" in content

        # Step 4: Check Alice's delivery is found
        message_id = delivery_tracker.check_delivery("alice@example.com", today, deliveries_file)
        assert message_id == "msg_123"

        # Step 5: Filter should only return Bob (Alice already delivered)
        missing = delivery_tracker.get_missing_recipients(
            ["alice@example.com", "bob@example.com"], today, deliveries_file
        )
        assert missing == ["bob@example.com"]

        # Step 6: Get all deliveries for the date
        all_delivered = delivery_tracker.get_date_deliveries(today, deliveries_file)
        assert all_delivered == {"alice@example.com": "msg_123"}

        # Step 7: Record Bob's delivery
        delivery_tracker.record_delivery(
            "bob@example.com",
            today,
            "msg_456",
            sent_at=dt.datetime(2026, 6, 29, 6, 0, 16, tzinfo=dt.timezone.utc),
            path=deliveries_file
        )

        # Step 8: Both should now be delivered
        missing = delivery_tracker.get_missing_recipients(
            ["alice@example.com", "bob@example.com"], today, deliveries_file
        )
        assert missing == []

        all_delivered = delivery_tracker.get_date_deliveries(today, deliveries_file)
        assert set(all_delivered.keys()) == {"alice@example.com", "bob@example.com"}
        assert all_delivered["alice@example.com"] == "msg_123"
        assert all_delivered["bob@example.com"] == "msg_456"

        # Step 9: Verify idempotency - recording same delivery again doesn't change anything
        delivery_tracker.record_delivery(
            "alice@example.com",
            today,
            "msg_123",
            sent_at=dt.datetime(2026, 6, 29, 6, 0, 15, tzinfo=dt.timezone.utc),
            path=deliveries_file
        )

        # Should still have exactly 2 entries
        all_delivered = delivery_tracker.get_date_deliveries(today, deliveries_file)
        assert len(all_delivered) == 2


def test_smoke_multiday_deliveries():
    """Verify deliveries are tracked per-date independently."""
    with tempfile.TemporaryDirectory() as tmpdir:
        deliveries_file = Path(tmpdir) / "deliveries.json"

        day1 = dt.date(2026, 6, 29)
        day2 = dt.date(2026, 6, 30)

        # Record Alice on day 1
        delivery_tracker.record_delivery(
            "alice@example.com", day1, "msg_day1",
            path=deliveries_file
        )

        # Alice is missing on day 2 (different date)
        assert delivery_tracker.check_delivery("alice@example.com", day2, deliveries_file) is None
        assert "alice@example.com" in delivery_tracker.get_missing_recipients(
            ["alice@example.com"], day2, deliveries_file
        )

        # But Alice is delivered on day 1
        assert delivery_tracker.check_delivery("alice@example.com", day1, deliveries_file) == "msg_day1"
        assert delivery_tracker.get_missing_recipients(
            ["alice@example.com"], day1, deliveries_file
        ) == []


def test_smoke_crash_recovery_scenario():
    """Simulate crash during batch send and recovery.

    Scenario:
    - Batch 1: Send to Alice (success, recorded)
    - CRASH before sending to Bob
    - Batch 2 (restart): Bob is still missing, resend only to Bob
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        deliveries_file = Path(tmpdir) / "deliveries.json"
        recipients = ["alice@example.com", "bob@example.com", "charlie@example.com"]
        today = dt.date(2026, 6, 29)

        # Batch 1: Send to Alice, crash before Bob
        missing = delivery_tracker.get_missing_recipients(recipients, today, deliveries_file)
        assert missing == recipients  # All missing initially

        # Send to Alice
        delivery_tracker.record_delivery("alice@example.com", today, "msg_alice", path=deliveries_file)

        # CRASH: Never sent to Bob or Charlie, and crash before recording

        # Batch 2 (restart): Check who needs sending
        missing = delivery_tracker.get_missing_recipients(recipients, today, deliveries_file)
        assert set(missing) == {"bob@example.com", "charlie@example.com"}
        assert "alice@example.com" not in missing

        # Send to Bob and Charlie only
        delivery_tracker.record_delivery("bob@example.com", today, "msg_bob", path=deliveries_file)
        delivery_tracker.record_delivery("charlie@example.com", today, "msg_charlie", path=deliveries_file)

        # Verify all 3 delivered exactly once
        all_delivered = delivery_tracker.get_date_deliveries(today, deliveries_file)
        assert len(all_delivered) == 3
        assert all_delivered["alice@example.com"] == "msg_alice"
        assert all_delivered["bob@example.com"] == "msg_bob"
        assert all_delivered["charlie@example.com"] == "msg_charlie"
