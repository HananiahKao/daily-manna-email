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


@patch("sjzl_daily_email.fetch")
def test_list_index_pages_discovers_and_stops(mock_fetch):
    # Simulate first two index pages exist, then consecutive misses
    def side_effect(url):
        if url.endswith("index01.html") or url.endswith("index02.html"):
            return "<html>ok</html>"
        if url.endswith("index.html"):
            return "<html>root</html>"
        return None

    mock_fetch.side_effect = side_effect
    pages = sjzl.list_index_pages(sjzl.SJZL_BASE)
    assert any(u.endswith("index01.html") for u in pages)
    assert any(u.endswith("index02.html") for u in pages)


@patch("sjzl_daily_email.fetch")
def test_find_latest_lesson_picks_highest(mock_fetch):
    # Two index pages with different highest lessons
    index1 = """
    <a href="101.html">101</a>
    <a href="150.html">150</a>
    """
    index2 = """
    <a href="120.html">120</a>
    <a href="199.html">199</a>
    """
    seq = ["<html>idx1</html>", index1, "<html>idx2</html>", index2]

    def side_effect(url):
        # First list_index_pages probes return non-empty for first two calls
        if url.endswith("index01.html"):
            return seq[0]
        if url.endswith("index02.html"):
            return seq[2]
        # When fetching the actual pages during find_latest_lesson
        if url.endswith("index01.html"):
            return seq[0]
        if url.endswith("index02.html"):
            return seq[2]
        # Not used
        return None

    # We will intercept fetch calls inside find_latest_lesson with specific returns
    def fetch_for_find(url):
        if url.endswith("index01.html"):
            return index1
        if url.endswith("index02.html"):
            return index2
        return None

    mock_fetch.side_effect = fetch_for_find

    latest = sjzl.find_latest_lesson("https://four.soqimp.com/books/2264")
    # Because list_index_pages relies on fetch too, ensure it returns both pages
    assert latest is not None
    num, url = latest
    assert num == 199
    assert url.endswith("199.html")


def test_extract_readable_text_fallbacks():
    # No h1/h2/h3, but has <title>
    html = """
    <html><head><title>My Title</title></head>
      <body>
        <p>First para</p>
        <p>Second para</p>
        <script>ignore()</script>
      </body>
    </html>
    """
    title, text = sjzl.extract_readable_text(html)
    assert title == "My Title"
    assert "First para" in text and "Second para" in text

    # Minimal content triggers raw text fallback
    html2 = "<html><head><title>T</title></head><body><p>a</p></body></html>"
    title2, text2 = sjzl.extract_readable_text(html2)
    assert title2 in ("T", "聖經之旅 - 每日內容")
    assert isinstance(text2, str)


@patch("sjzl_daily_email.get_gmail_service")
@patch("smtplib.SMTP")
def test_send_email_starttls(mock_smtp, mock_gmail, monkeypatch):
    # Set required envs
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("EMAIL_TO", "to@example.com")
    monkeypatch.setenv("TLS_MODE", "starttls")

    # Mock Gmail service
    mock_service = MagicMock()
    mock_gmail.return_value = mock_service

    sjzl.send_email("Subj", "Body")

    # Since it uses Gmail API now, SMTP mocks shouldn't be called
    assert not mock_smtp.called
    mock_gmail.assert_called()


@patch("sjzl_daily_email.get_gmail_service")
@patch("smtplib.SMTP_SSL")
def test_send_email_ssl_with_html(mock_smtp_ssl, mock_gmail, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("EMAIL_TO", "to1@example.com, to2@example.com")
    monkeypatch.setenv("TLS_MODE", "ssl")

    # Mock Gmail service
    mock_service = MagicMock()
    mock_gmail.return_value = mock_service

    sjzl.send_email("Subj", "Body", html_body="<b>Hi</b>")

    # Since it uses Gmail API now, SMTP mocks shouldn't be called
    assert not mock_smtp_ssl.called
    mock_gmail.assert_called()


@patch("sjzl_daily_email.get_gmail_service")
def test_send_email_debug_mode(mock_gmail, monkeypatch):
    monkeypatch.setenv("EMAIL_FROM", "from@example.com")
    monkeypatch.setenv("EMAIL_TO", "to@example.com")
    monkeypatch.setenv("DEBUG_MODE", "1")

    # Mock Gmail service
    mock_service = MagicMock()
    mock_gmail.return_value = mock_service

    sjzl.send_email("Test Subject", "Test Body")

    # Verify the message was sent
    assert mock_gmail.called

    # Get the sent message data
    call_args = mock_gmail.return_value.users.return_value.messages.return_value.send.call_args
    message_data = call_args[1]['body']

    # Decode the raw message to check recipient
    import base64
    raw_message = base64.urlsafe_b64decode(message_data['raw'])
    message_str = raw_message.decode('utf-8', errors='ignore')

    # In debug mode, should send to EMAIL_FROM
    assert "To: from@example.com" in message_str
    assert "To: to@example.com" not in message_str


@patch("sjzl_daily_email.get_gmail_service")
def test_send_email_normal_mode(mock_gmail, monkeypatch):
    monkeypatch.setenv("EMAIL_FROM", "from@example.com")
    monkeypatch.setenv("EMAIL_TO", "to@example.com")
    monkeypatch.delenv("DEBUG_MODE", raising=False)  # Ensure DEBUG_MODE is not set

    # Mock Gmail service
    mock_service = MagicMock()
    mock_gmail.return_value = mock_service

    sjzl.send_email("Test Subject", "Test Body")

    # Verify the message was sent
    assert mock_gmail.called

    # Get the sent message data
    call_args = mock_gmail.return_value.users.return_value.messages.return_value.send.call_args
    message_data = call_args[1]['body']

    # Decode the raw message to check recipient
    import base64
    raw_message = base64.urlsafe_b64decode(message_data['raw'])
    message_str = raw_message.decode('utf-8', errors='ignore')

    # In normal mode, should send to EMAIL_TO
    assert "To: to@example.com" in message_str
    assert "To: from@example.com" not in message_str


def test_debug_enabled():
    # Test _debug_enabled function
    import os

    # Save original env
    orig_debug_email = os.environ.get("DEBUG_EMAIL")
    orig_debug_mode = os.environ.get("DEBUG_MODE")

    try:
        # Neither set
        if "DEBUG_EMAIL" in os.environ:
            del os.environ["DEBUG_EMAIL"]
        if "DEBUG_MODE" in os.environ:
            del os.environ["DEBUG_MODE"]
        assert not sjzl._debug_enabled()

        # DEBUG_MODE set
        os.environ["DEBUG_MODE"] = "1"
        assert sjzl._debug_enabled()

        # DEBUG_EMAIL set, DEBUG_MODE unset
        del os.environ["DEBUG_MODE"]
        os.environ["DEBUG_EMAIL"] = "1"
        assert sjzl._debug_enabled()

        # Both set
        os.environ["DEBUG_MODE"] = "1"
        assert sjzl._debug_enabled()

        # DEBUG_MODE false values
        os.environ["DEBUG_MODE"] = "0"
        assert sjzl._debug_enabled()  # Still true because DEBUG_EMAIL is set

        os.environ["DEBUG_EMAIL"] = "0"
        assert not sjzl._debug_enabled()

    finally:
        # Restore original env
        if orig_debug_email is not None:
            os.environ["DEBUG_EMAIL"] = orig_debug_email
        elif "DEBUG_EMAIL" in os.environ:
            del os.environ["DEBUG_EMAIL"]

        if orig_debug_mode is not None:
            os.environ["DEBUG_MODE"] = orig_debug_mode
        elif "DEBUG_MODE" in os.environ:
            del os.environ["DEBUG_MODE"]
