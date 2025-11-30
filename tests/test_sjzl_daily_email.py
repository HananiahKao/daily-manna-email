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


@patch("sjzl_daily_email.get_xoauth2_string")
@patch("smtplib.SMTP")
def test_send_email_starttls(mock_smtp, mock_oauth, monkeypatch):
    # Set required envs
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("EMAIL_TO", "to@example.com")
    monkeypatch.setenv("TLS_MODE", "starttls")

    # Mock OAuth to return a valid XOAUTH2 string
    mock_oauth.return_value = "user=user@example.com\x01auth=Bearer fake_token\x01\x01"

    # Create mock server instance
    instance = MagicMock()
    instance.docmd.return_value = (235, b"Authentication successful")
    
    # Configure the SMTP mock to return our instance via context manager
    mock_smtp.return_value = instance

    sjzl.send_email("Subj", "Body")

    assert mock_smtp.called
    # starttls/docmd/sendmail are called on the server object
    instance.starttls.assert_called()
    instance.docmd.assert_called()
    instance.sendmail.assert_called()


@patch("sjzl_daily_email.get_xoauth2_string")
@patch("smtplib.SMTP_SSL")
def test_send_email_ssl_with_html(mock_smtp_ssl, mock_oauth, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("EMAIL_TO", "to1@example.com, to2@example.com")
    monkeypatch.setenv("TLS_MODE", "ssl")

    # Mock OAuth to return a valid XOAUTH2 string
    mock_oauth.return_value = "user=user@example.com\x01auth=Bearer fake_token\x01\x01"

    # Create mock server instance
    instance = MagicMock()
    instance.docmd.return_value = (235, b"Authentication successful")
    
    # Configure the SMTP_SSL mock to return our instance via context manager
    mock_smtp_ssl.return_value = instance

    sjzl.send_email("Subj", "Body", html_body="<b>Hi</b>")

    assert mock_smtp_ssl.called
    instance.sendmail.assert_called()
