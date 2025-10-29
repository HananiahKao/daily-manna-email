#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily 'Shen Jing Zhi Li' fetcher and emailer.

- Discovers the latest available '聖經之旅' lesson under:
  https://four.soqimp.com/books/2264/
- Fetches the lesson page HTML, extracts readable text (title + content).
- Sends an email with the text content.
- Designed for cron/schedule; uses env vars for credentials/config.

Env vars:
  SMTP_HOST          e.g., smtp.gmail.com
  SMTP_PORT          e.g., 587
  SMTP_USER          your SMTP username (email)
  SMTP_PASSWORD      your SMTP password or app password
  EMAIL_FROM         sender email (often same as SMTP_USER)
  EMAIL_TO           recipient email (comma-separated for multiple)
  TLS_MODE           'starttls' (default) or 'ssl'
  SJZL_BASE          optional; default 'https://four.soqimp.com/books/2264'
"""

import os
import re
import sys
import smtplib
import socket
import logging
import datetime as dt
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from email.utils import formataddr
from email import encoders
from email.charset import Charset, QP
from typing import Optional, Tuple, List, Optional as TypingOptional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# -------- Config & Logging --------

SJZL_BASE = os.getenv("SJZL_BASE", "https://four.soqimp.com/books/2264")
# Optional alternate source: ezoe.work via standardized selector "<volume>-<lesson>-<day>".
EZOe_SELECTOR = os.getenv("EZOE_SELECTOR")  # e.g., "2-1-3" (週三)
EZOe_BASE = os.getenv("EZOE_BASE", "https://ezoe.work/books/2")
INDEX_PATTERN = re.compile(r"^index(\d{2})\.html$")  # e.g., index12.html
LESSON_PATTERN = re.compile(r"^(\d{2,3})\.html$")    # e.g., 210.html

REQUEST_TIMEOUT = (10, 20)  # (connect, read) seconds
HEADERS = {
    "User-Agent": "daily-manna-sjzl/1.0 (+https://example.com; personal non-commercial)"
}
HTTP_RETRIES = int(os.getenv("HTTP_RETRIES", "3"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("sjzl-daily")


def _debug_enabled() -> bool:
    return os.getenv("DEBUG_EMAIL") not in (None, "", "0", "false", "False")


def _debug_preview(label: str, text: str) -> None:
    if not _debug_enabled():
        return
    try:
        head = (text or "")[:200]
        rhead = repr((text or ""))[:240]
        logger.info("DEBUG %s (first200): %s", label, head)
        logger.info("DEBUG %s (repr200): %s", label, rhead)
        logger.info("DEBUG %s length: %s", label, len(text or ""))
    except Exception as _e:
        logger.info("DEBUG %s (error previewing): %s", label, _e)


# -------- HTTP helpers --------

def _decode_html(resp: requests.Response, url: str = "") -> Optional[str]:
    """Robustly decode HTML bytes to Unicode, preferring declared/meta charset, fallback UTF-8."""
    if resp.status_code != 200 or "text/html" not in resp.headers.get("Content-Type", ""):
        return None
    data = resp.content or b""
    # Force UTF-8 for known hosts that serve UTF-8 without clear headers
    try:
        from urllib.parse import urlparse as _urlparse
        host = _urlparse(url).hostname or ""
    except Exception:
        host = ""
    if host.endswith("soqimp.com"):
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            pass
    # Try requests-detected encoding first
    enc = resp.encoding
    if not enc:
        # Sniff from meta charset
        try:
            head = data[:2048].decode("ascii", errors="ignore")
            import re as _re
            m = _re.search(r"charset=([A-Za-z0-9_\-]+)", head, _re.I)
            if m:
                enc = m.group(1).strip()
        except Exception:
            enc = None
    if not enc:
        enc = "utf-8"
    try:
        return data.decode(enc, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


def fetch(url: str) -> Optional[str]:
    """GET a URL and return its HTML text, with simple retries and robust decoding."""
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            html = _decode_html(resp, url)
            if html is not None:
                return html
            logger.warning("Attempt %s: Non-200 or non-HTML from %s: %s", attempt, url, resp.status_code)
        except requests.RequestException as e:
            logger.error("Attempt %s: Request failed for %s: %s", attempt, url, e)
        # backoff
        try:
            import time
            time.sleep(min(5, attempt))
        except Exception:
            pass
    return None


# -------- Discovery logic --------

def list_index_pages(base: str) -> List[str]:
    """
    Enumerate index pages by probing index01.html .. index20.html (cap reasonable).
    Stops after a run of misses to keep fast and polite.
    """
    max_probe = 20
    misses_in_row = 0
    pages = []
    for i in range(1, max_probe + 1):
        name = f"index{i:02d}.html"
        url = urljoin(base + "/", name)
        html = fetch(url)
        if html:
            pages.append(url)
            misses_in_row = 0
        else:
            misses_in_row += 1
            if misses_in_row >= 3 and pages:
                break
    if not pages:
        root = urljoin(base + "/", "index.html")
        if fetch(root):
            pages.append(root)
    return pages


def extract_lesson_links(index_html: str, index_url: str) -> List[Tuple[int, str]]:
    """
    From an index page HTML, extract lesson numbers and absolute URLs.
    Returns list of (lesson_num, absolute_url).
    """
    soup = BeautifulSoup(index_html, "html.parser")
    lessons = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        m = LESSON_PATTERN.match(href)
        if not m:
            continue
        num = int(m.group(1))
        abs_url = urljoin(index_url, href)
        lessons.append((num, abs_url))
    unique = {}
    for n, u in lessons:
        unique[n] = u
    return sorted(unique.items(), key=lambda x: x[0])


def find_latest_lesson(base: str) -> Optional[Tuple[int, str]]:
    """
    Scan available index pages and return highest lesson (num, url).
    """
    index_pages = list_index_pages(base)
    if not index_pages:
        logger.error("No index pages discovered under base: %s", base)
        return None

    best_num, best_url = -1, None
    for idx_url in index_pages:
        html = fetch(idx_url)
        if not html:
            continue
        lessons = extract_lesson_links(html, idx_url)
        if lessons:
            num, url = lessons[-1]
            if num > best_num:
                best_num, best_url = num, url

    if best_url is None:
        logger.error("No lessons found in discovered index pages.")
        return None
    return best_num, best_url


# -------- Content extraction --------

def extract_readable_text(lesson_html: str) -> Tuple[str, str]:
    """
    Extract a reasonable title and text content from a lesson page.
    Returns (title, text_body).
    """
    soup = BeautifulSoup(lesson_html, "html.parser")

    title_tag = soup.find(["h1", "h2", "h3"])
    if title_tag and title_tag.get_text(strip=True):
        title = title_tag.get_text(strip=True)
    elif soup.title and soup.title.get_text(strip=True):
        title = soup.title.get_text(strip=True)
    else:
        title = "聖經之旅 - 每日內容"

    for sel in ["script", "style", "nav", "footer", "iframe"]:
        for tag in soup.select(sel):
            tag.decompose()

    texts = []
    body = soup.find("body") or soup
    for el in body.find_all(["p", "h1", "h2", "h3", "li", "blockquote", "pre"]):
        t = el.get_text(" ", strip=True)
        if t and len(t) >= 2:
            texts.append(t)

    if len(texts) < 5:
        raw = soup.get_text("\n", strip=True)
        lines = [ln for ln in raw.splitlines() if len(ln.strip()) >= 2]
        texts = lines[:200]

    text_body = "\n\n".join(texts)
    return title, text_body


# -------- Email sending --------

def send_email(subject: str, body: str, html_body: TypingOptional[str] = None) -> None:
    """
    Send email using SMTP with STARTTLS or SSL based on TLS_MODE.
    """
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASSWORD"]
    email_from = os.getenv("EMAIL_FROM", smtp_user)
    email_to_raw = os.environ["EMAIL_TO"]
    recipients = [addr.strip() for addr in email_to_raw.split(",") if addr.strip()]
    tls_mode = os.getenv("TLS_MODE", "starttls").lower()

    # Always send multipart/alternative so clients can choose best part
    msg = MIMEMultipart("alternative")
    msg["From"] = email_from
    msg["To"] = ", ".join(recipients)
    # RFC 2047 encode the subject to avoid mojibake in some clients
    msg["Subject"] = str(Header(subject, "utf-8"))
    # Optional language hint
    msg["Content-Language"] = os.getenv("CONTENT_LANGUAGE", "zh-Hant")

    # Plain-text fallback part (let library choose safe encoding)
    text_part = MIMEText(body, "plain", "utf-8")
    msg.attach(text_part)
    # Optional HTML part for richer formatting
    if html_body:
        html_part = MIMEText(html_body, "html", "utf-8")
        # Let library choose transfer encoding to avoid duplicate headers
        msg.attach(html_part)

    try:
        if tls_mode == "ssl":
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
        with server:
            if tls_mode == "starttls":
                server.ehlo()
                server.starttls()
                server.ehlo()
            if smtp_user:
                server.login(smtp_user, smtp_pass)
            server.sendmail(email_from, recipients, msg.as_string())
    except (smtplib.SMTPException, socket.error) as e:
        logger.error("Failed to send email: %s", e)
        raise


# -------- Main job --------

def run_once() -> int:
    """Fetch content and email it. Returns exit code.

    Modes:
      - Default (SJZL): discover latest from four.soqimp.com and send plain text.
      - Selector HTML mode (EZOE_SELECTOR set): fetch ezoe.work lesson day HTML and send rich HTML with plain-text fallback.
    """
    today = dt.datetime.now().strftime("%Y-%m-%d")
    # If selector mode is enabled, use ezoe scraper
    if EZOe_SELECTOR:
        try:
            from ezoe_week_scraper import get_day_html  # local module
        except Exception as imp_exc:
            logger.error("Failed to import ezoe_week_scraper: %s", imp_exc)
            return 1

        try:
            html_day = get_day_html(EZOe_SELECTOR, base=EZOe_BASE)
        except Exception as e:
            logger.error("Failed to fetch ezoe day HTML for selector %s: %s", EZOe_SELECTOR, e)
            return 2
        _debug_preview("EZOE_HTML", html_day)

        # Build subject and plain-text fallback derived from same HTML; also provide source URL hint
        # Derive source URL based on selector
        try:
            vol, les, day = EZOe_SELECTOR.split("-")
            source_url = f"{EZOe_BASE.rstrip('/')}/2264-{int(vol)}-{int(les)}.html"
        except Exception:
            source_url = EZOe_BASE

        # Extract a simple title from HTML
        try:
            from bs4 import BeautifulSoup as _BS
            _s = _BS(html_day, "html.parser")
            title_tag = _s.find(["h1", "h2", "h3"]) or _s.find("title")
            title = title_tag.get_text(strip=True) if title_tag else "聖經之旅 每日內容"
        except Exception:
            title = "聖經之旅 每日內容"

        subject = f"聖經之旅 | {title} | {today}"
        try:
            from bs4 import BeautifulSoup as _BS
            _s2 = _BS(html_day, "html.parser")
            for sel in ["script", "style", "nav", "footer", "iframe"]:
                for t in _s2.select(sel):
                    t.decompose()
            snippets = []
            for el in _s2.find_all(["p", "li", "h1", "h2", "h3"]):
                txt = el.get_text(" ", strip=True)
                if txt:
                    snippets.append(txt)
            preview = "\n\n".join(snippets)
            if len(preview) > 1200:
                preview = preview[:1200] + "…"
        except Exception:
            preview = "(純文字預覽不可用；請查看 HTML 內容)"
        _debug_preview("EZOE_TEXT_PREVIEW", preview)
        body = f"來源: {source_url}\n日期: {today}\n\n{preview}"
        _debug_preview("EZOE_BODY", body)
        send_email(subject, body, html_body=html_day)
        logger.info("HTML email (ezoe) sent to %s", os.environ.get("EMAIL_TO", ""))
        return 0
    # Allow override for testing SMTP without discovery/fetch variability
    test_url = os.getenv("TEST_LESSON_URL")
    if test_url:
        logger.info("TEST_LESSON_URL set; using override URL: %s", test_url)
        lesson_url = test_url
        lesson_num = -1
    else:
        latest = find_latest_lesson(SJZL_BASE)
        if not latest:
            return 2
        lesson_num, lesson_url = latest
        logger.info("Latest lesson detected: %s (%s)", lesson_num, lesson_url)

    html = fetch(lesson_url)
    if not html:
        logger.error("Failed to fetch lesson page: %s", lesson_url)
        return 3

    title, text_body = extract_readable_text(html)
    # Build simple HTML email from extracted text
    import html as _html
    def _to_html(title: str, url: str, date_str: str, text_body: str) -> str:
        esc = _html.escape
        paras = "".join(f"<p>{esc(p)}</p>" for p in text_body.split("\n\n") if p.strip())
        return f"""
        <!doctype html>
        <html><head><meta charset='utf-8'/>
        <meta name='viewport' content='width=device-width, initial-scale=1'/>
        <style>body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;line-height:1.5;color:#111}}
        a{{color:#0b65c6;text-decoration:none}}</style></head>
        <body><div style='max-width:720px;margin:16px auto;padding:0 12px;'>
        <h1>{esc(title)}</h1>
        <div style='color:#666;font-size:12px;margin-bottom:16px;'>日期: {esc(date_str)} · <a href='{esc(url)}'>原文链接</a></div>
        {paras}
        </div></body></html>
        """
    html_body = _to_html(title, lesson_url, today, text_body)
    _debug_preview("SJZL_TEXT_BODY", text_body)
    _debug_preview("SJZL_HTML_BODY", html_body)
    subject = f"聖經之旅 | 第 {lesson_num if lesson_num!=-1 else '測試'} 課 | {today}"
    body = f"{title}\n連結: {lesson_url}\n日期: {today}\n\n{text_body}"
    _debug_preview("SJZL_SUBJECT", subject)
    _debug_preview("SJZL_BODY", body)

    send_email(subject, body, html_body=html_body)
    logger.info("Email sent to %s", os.environ.get("EMAIL_TO", ""))
    return 0


if __name__ == "__main__":
    required = ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        sys.stderr.write(f"Missing required env vars: {', '.join(missing)}\n")
        sys.exit(1)
    try:
        sys.exit(run_once())
    except Exception as exc:
        logger.exception("Unhandled error: %s", exc)
        sys.exit(1)
