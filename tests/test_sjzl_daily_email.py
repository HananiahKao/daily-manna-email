from unittest.mock import patch, MagicMock

import pytest

import sjzl_daily_email as sjzl


def test_extract_lesson_links_parsing_basic():
    html = """
    <html><body>
      <a href="001.html">1</a>
      <a href="210.html">210</a>
      <a href="abc.html">ignore</a>
      <a href="210.html">dup</a>
    </body></html>
    """
    links = sjzl.extract_lesson_links(html, "https://four.soqimp.com/books/2264/index01.html")
    assert links[-1][0] == 210
    assert links[-1][1].endswith("/210.html")
    # unique by number
    assert [n for n, _ in links].count(210) == 1


@patch("sjzl_daily_email.delivery_tracker.get_missing_recipients")
@patch("sjzl_daily_email.delivery_tracker.record_delivery")
@patch("sjzl_daily_email.get_gmail_service")
def test_send_email_records_delivery_on_success(mock_gmail, mock_record, mock_missing, monkeypatch):
    """Test that send_email records delivery after successful send."""
    import datetime as dt
    from unittest.mock import call

    monkeypatch.setenv("EMAIL_FROM", "from@example.com")
    monkeypatch.setenv("RECIPIENT_SOURCE", "email")
    monkeypatch.setenv("EMAIL_TO", "user1@example.com,user2@example.com")
    monkeypatch.delenv("DEBUG_MODE", raising=False)

    # Mock get_missing_recipients to return both users (none delivered yet)
    mock_missing.return_value = ["user1@example.com", "user2@example.com"]

    # Mock Gmail service to return message IDs
    mock_service = MagicMock()
    mock_gmail.return_value = mock_service
    mock_service.users().messages().send().execute.side_effect = [
        {"id": "msg_id_1"},
        {"id": "msg_id_2"}
    ]

    today = dt.date.today()
    recipients = sjzl.send_email("Test Subject", "Test Body", recipients=["test@example.com"])

    # Verify deliveries were recorded
    assert mock_record.call_count == 2
    # Both calls should be for today's date
    calls = mock_record.call_args_list
    assert calls[0][0] == ("user1@example.com", today, "msg_id_1")
    assert calls[1][0] == ("user2@example.com", today, "msg_id_2")

    # Verify return value contains message IDs
    assert recipients == {
        "user1@example.com": "msg_id_1",
        "user2@example.com": "msg_id_2"
    }


@patch("sjzl_daily_email.delivery_tracker.get_missing_recipients")
@patch("sjzl_daily_email.get_gmail_service")
def test_send_email_skips_already_delivered(mock_gmail, mock_missing, monkeypatch):
    """Test that send_email skips recipients already delivered today."""
    monkeypatch.setenv("EMAIL_FROM", "from@example.com")
    monkeypatch.setenv("RECIPIENT_SOURCE", "email")
    monkeypatch.setenv("EMAIL_TO", "user1@example.com,user2@example.com,user3@example.com")
    monkeypatch.delenv("DEBUG_MODE", raising=False)

    # Mock get_missing_recipients to return only user2 and user3 (user1 already delivered)
    mock_missing.return_value = ["user2@example.com", "user3@example.com"]

    # Mock Gmail service
    mock_service = MagicMock()
    mock_gmail.return_value = mock_service
    mock_service.users().messages().send().execute.side_effect = [
        {"id": "msg_id_2"},
        {"id": "msg_id_3"}
    ]

    recipients = sjzl.send_email("Test Subject", "Test Body", recipients=["test@example.com"])

    # Should only send to 2 recipients, not 3
    assert len(recipients) == 2
    assert "user2@example.com" in recipients
    assert "user3@example.com" in recipients
    assert "user1@example.com" not in recipients


@patch("sjzl_daily_email.delivery_tracker.get_missing_recipients")
@patch("sjzl_daily_email.delivery_tracker.record_delivery")
@patch("sjzl_daily_email.get_gmail_service")
def test_send_email_recovery_idempotent(mock_gmail, mock_record, mock_missing, monkeypatch):
    """Test idempotent recovery: sending twice doesn't create duplicates.

    Scenario: System sends to Alice, then crashes before sending to Bob.
    On restart, should only send to Bob.
    """
    import datetime as dt

    monkeypatch.setenv("EMAIL_FROM", "from@example.com")
    monkeypatch.setenv("RECIPIENT_SOURCE", "email")
    monkeypatch.setenv("EMAIL_TO", "alice@example.com,bob@example.com")
    monkeypatch.delenv("DEBUG_MODE", raising=False)

    today = dt.date.today()

    # First run: only Bob is missing (Alice already in delivery tracker)
    mock_missing.return_value = ["bob@example.com"]

    mock_service = MagicMock()
    mock_gmail.return_value = mock_service
    mock_service.users().messages().send().execute.return_value = {"id": "msg_bob"}

    recipients = sjzl.send_email("Test Subject", "Test Body", recipients=["test@example.com"])

    # Should only send to Bob
    assert recipients == {"bob@example.com": "msg_bob"}

    # Verify Bob's delivery was recorded
    mock_record.assert_called_once_with("bob@example.com", today, "msg_bob")
