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
    plain_part = message.get_payload(0)
    if isinstance(plain_part, str):
        plain_text = plain_part
    else:
        plain_text = plain_part.get_payload(decode=True).decode('utf-8')  # type: ignore
    assert "連結:" in plain_text
    assert len(plain_text) > 100

    # Check HTML body
    html_part = message.get_payload(1)
    if isinstance(html_part, str):
        html_text = html_part
    else:
        html_text = html_part.get_payload(decode=True).decode('utf-8')  # type: ignore
    assert "<html>" in html_text
    assert "<h1>" in html_text


def test_email_pipeline_e2e_ezoe_mode(monkeypatch, fs):
    """End-to-end test of the email sending pipeline for EZOe mode.

    Tests the full flow using content sources (e.g., ezoe.work or Wix),
    asserting on the final effect: correct email delivered via Gmail API.
    """
    # Set up environment variables
    monkeypatch.setenv("SMTP_USER", "test@example.com")
    monkeypatch.setenv("EMAIL_FROM", "sender@example.com")
    monkeypatch.setenv("EMAIL_TO", "recipient@example.com")
    monkeypatch.setenv("EZOE_SELECTOR", "2-1-3")
    monkeypatch.setenv("DEBUG_MODE", "1")
    monkeypatch.setenv("CONTENT_SOURCE", "ezoe")

    # Allow access to real opencc configuration files
    import opencc
    import os
    opencc_path = os.path.dirname(os.path.abspath(opencc.__file__))
    fs.add_real_directory(opencc_path)

    # Create state directory in fake file system
    fs.create_dir("state")

    # Create a mock content block
    class MockContentBlock:
        def __init__(self):
            self.html_content = """
            <div class="email-body">
                <p>Test content</p>
                <a href="https://ezoe.work/test">原文連結</a>
            </div>
            """
            self.title = "Test Lesson"
            self.plain_text_content = "Test content\n原文連結"

    # Create a mock active source
    mock_source = MagicMock()
    mock_source.get_daily_content.return_value = MockContentBlock()
    mock_source.get_email_subject.return_value = "聖經之旅"
    mock_source.get_content_url.return_value = "https://ezoe.work/test"
    mock_source.get_source_name.return_value = "ezoe"

    # Mock the Gmail service
    mock_service = MagicMock()
    mock_get_gmail = MagicMock(return_value=mock_service)

    # Import and reload the module with the patches
    import importlib
    import sjzl_daily_email as sjzl
    
    # Patch the module-level variable directly
    with patch.object(sjzl, "get_gmail_service", mock_get_gmail), \
         patch.object(sjzl, "find_latest_lesson"), \
         patch("content_source_factory.get_active_source", return_value=mock_source), \
         patch.object(sjzl, "EZOe_SELECTOR", "2-1-3"):
        
        # Execute the full pipeline
        result = sjzl.run_once()

        # Assert successful execution
        assert result == 0

        # Assert that Gmail API was called to send email
        mock_get_gmail.assert_called_once()
        mock_service.users.return_value.messages.return_value.send.assert_called_once()

        # Verify the debug output file in fake file system
        import pathlib
        wrapped_file = pathlib.Path("state/last_ezoe_email_wrapped.html")
        assert wrapped_file.exists()
        content = wrapped_file.read_text()
        assert "<!doctype html>" in content
        assert "email-body" in content
        assert "原文連結" in content
        assert "ezoe.work" in content
