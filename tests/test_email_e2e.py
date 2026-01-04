import pytest
from unittest.mock import patch, MagicMock
import sjzl_daily_email as sjzl


@patch("sjzl_daily_email.get_gmail_service")
def test_email_pipeline_e2e_sjzl_mode(mock_get_gmail_service, monkeypatch):
    """End-to-end test of the email sending pipeline for SJZL mode.

    Tests the full flow from content discovery to email sending,
    asserting on the final effect: correct email delivered via Gmail API.
    """
    # Set up environment variables
    monkeypatch.setenv("SMTP_USER", "test@example.com")
    monkeypatch.setenv("EMAIL_FROM", "sender@example.com")
    monkeypatch.setenv("EMAIL_TO", "recipient1@example.com,recipient2@example.com")
    monkeypatch.setenv("DEBUG_MODE", "1")

    # Mock the Gmail service
    mock_service = MagicMock()
    mock_get_gmail_service.return_value = mock_service

    # Execute the full pipeline
    result = sjzl.run_once()

    # Assert successful execution
    assert result == 0

    # Assert that Gmail API was called to send email
    mock_get_gmail_service.assert_called_once()
    mock_service.users.return_value.messages.return_value.send.assert_called_once()

    # Verify the email content
    send_call = mock_service.users.return_value.messages.return_value.send.call_args
    message_data = send_call[1]['body']
    import base64
    import email
    raw_message = base64.urlsafe_b64decode(message_data['raw'])
    message = email.message_from_bytes(raw_message)

    # Check headers
    assert message['From'] == "sender@example.com"
    assert message['To'] == "sender@example.com"
    import email.header
    decoded_subject = email.header.decode_header(message['Subject'])[0][0]
    if isinstance(decoded_subject, bytes):
        decoded_subject = decoded_subject.decode('utf-8')
    assert "聖經之旅" in decoded_subject

    # Check plain text body
    plain_text = message.get_payload(0).get_payload(decode=True).decode('utf-8')
    assert "連結:" in plain_text
    assert len(plain_text) > 100

    # Check HTML body
    html_text = message.get_payload(1).get_payload(decode=True).decode('utf-8')
    assert "<html>" in html_text
    assert "<h1>" in html_text


@patch("sjzl_daily_email.get_gmail_service")
def test_email_pipeline_e2e_ezoe_mode(mock_get_gmail_service, monkeypatch):
    """End-to-end test of the email sending pipeline for EZOe mode.

    Tests the full flow using content sources (e.g., ezoe.work or Wix),
    asserting on the final effect: correct email delivered via Gmail API.
    """
    # Set up environment variables
    monkeypatch.setenv("SMTP_USER", "test@example.com")
    monkeypatch.setenv("EMAIL_FROM", "sender@example.com")
    monkeypatch.setenv("EMAIL_TO", "recipient@example.com")
    monkeypatch.setenv("EZOE_SELECTOR", "2-1-3")  # volume 2, lesson 1, day 3
    monkeypatch.setenv("DEBUG_MODE", "1")
    monkeypatch.setenv("CONTENT_SOURCE", "ezoe")

    # Mock the Gmail service
    mock_service = MagicMock()
    mock_get_gmail_service.return_value = mock_service

    # Execute the full pipeline
    result = sjzl.run_once()

    # Assert successful execution
    assert result == 0

    # Assert that Gmail API was called to send email
    mock_get_gmail_service.assert_called_once()
    mock_service.users.return_value.messages.return_value.send.assert_called_once()

    # Verify the debug output file
    import pathlib
    wrapped_file = pathlib.Path("state/last_ezoe_email_wrapped.html")
    assert wrapped_file.exists()
    content = wrapped_file.read_text()
    assert "<!doctype html>" in content
    assert "email-body" in content
    assert "原文連結" in content
    assert "ezoe.work" in content
