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
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# -------- CSS extraction for ezoe mode --------

def _ezoe_lesson_url(selector: str, base: str) -> str:
    """Build lesson URL like https://ezoe.work/books/2/2264-<volume>-<lesson>.html from selector 'v-l-d'."""
    import re as _re
    m = _re.fullmatch(r"(\d+)-(\d+)-(\d)", selector)
    if not m:
        raise ValueError("Invalid EZOe selector format: '<volume>-<lesson>-<day>'")
    vol = int(m.group(1)); les = int(m.group(2))
    filename = f"2264-{vol}-{les}.html"
    return urljoin(base.rstrip('/') + '/', filename)


def _ezoe_day_anchor(selector: str) -> Optional[str]:
    """Return day anchor id like '1_6'..'1_12' from selector 'v-l-d'."""
    try:
        _v, _l, d = selector.split("-")
        di = int(d)
        if 1 <= di <= 7:
            return f"1_{5 + di}"
    except Exception:
        return None
    return None


def _ezoe_detect_anchor_id(selector: str, base: str) -> Optional[str]:
    """Best-effort detect the actual day anchor id from the live lesson page.

    Uses ezoe_week_scraper's parsing heuristics to locate the day header and
    returns its element id when present. Falls back to None if not found.
    """
    try:
        # Lazy import to avoid hard dependency when selector mode is unused
        import ezoe_week_scraper as ez  # type: ignore
        from bs4 import BeautifulSoup as _BS  # local parser

        m = re.fullmatch(r"(\d+)-(\d+)-(\d)", selector)
        if not m:
            return None
        volume = int(m.group(1)); lesson = int(m.group(2)); day = int(m.group(3))
        if not (1 <= day <= 7):
            return None
        label = ez.DAY_LABELS.get(day)
        if not label:
            return None
        url = ez._lesson_url(base, volume, lesson)  # reuse helper for canonical path
        html = ez._fetch(url)
        if not html:
            return None
        soup = _BS(html, "html.parser")
        content_root = soup.select_one("div.main") or soup.find("body") or soup
        anchor = ez._find_day_anchor(content_root, label)
        if anchor and anchor.get("id"):
            return str(anchor.get("id")).strip() or None
    except Exception:
        # Any failure here should not break the job; we will fallback later
        return None
    return None


def _fetch_css_texts_from_page(html: str, page_url: str, max_bytes: int = None) -> str:
    """Collect CSS from inline <style> and linked stylesheets (same-origin).

    For testing, `max_bytes` may be None to disable capping.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    out_parts: List[str] = []
    total = 0
    # Inline styles first
    for st in soup.find_all("style"):
        try:
            txt = st.get_text() or ""
        except Exception:
            txt = ""
        if not txt:
            continue
        b = len(txt.encode("utf-8", errors="ignore"))
        if max_bytes is not None and total + b > max_bytes:
            break
        out_parts.append(txt)
        total += b
    # Linked styles (same-origin only)
    try:
        page_host = urlparse(page_url).hostname or ""
    except Exception:
        page_host = ""
    for link in soup.find_all("link", rel=True, href=True):
        if str(link.get("rel")).lower().find("stylesheet") < 0:
            # accept rel=['stylesheet'] or similar
            rels = link.get("rel")
            if not rels or not any(str(r).lower() == "stylesheet" for r in rels):
                continue
        href = link.get("href").strip()
        css_url = urljoin(page_url, href)
        try:
            if urlparse(css_url).hostname != page_host:
                continue
        except Exception:
            continue
        try:
            resp = requests.get(css_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200 or "text/css" not in resp.headers.get("Content-Type", ""):
                continue
            css_txt = resp.text or ""
        except Exception:
            continue
        if not css_txt:
            continue
        b = len(css_txt.encode("utf-8", errors="ignore"))
        if max_bytes is not None and total + b > max_bytes:
            break
        out_parts.append(css_txt)
        total += b

    # Optionally filter out very site-specific chrome we strip
    if out_parts:
        joined = "\n".join(out_parts)
        # Simple filters/scoping: remove obvious chrome we strip from content,
        # and wrap CSS under a scoping class to avoid collisions.
        scope = ".email-body"
        pruned = []
        for line in joined.splitlines():
            low = line.strip().lower()
            # drop rules that directly target header/feature/back-to-top or body reset we don't need
            if any(tok in low for tok in [".header", ".feature", "#btt", "#toptitle", "iframe", "nav", "footer"]):
                continue
            pruned.append(line)
        css_core = "\n".join(pruned)
        # Naive scoping: prefix top-level selectors by adding `.email-body ` before rules.
        # Keep it simple to avoid breaking @ rules.
        scoped_lines = []
        for ln in css_core.splitlines():
            s = ln.rstrip()
            if not s:
                scoped_lines.append(s)
                continue
            if s.lstrip().startswith("@"):
                # keep @media/@font-face as-is
                scoped_lines.append(s)
            elif "{" in s:
                try:
                    before, after = s.split("{", 1)
                    selectors = before.strip()
                    if selectors:
                        scoped_sel = ",".join(f"{scope} " + sel.strip() for sel in selectors.split(","))
                        scoped_lines.append(scoped_sel + "{" + after)
                    else:
                        scoped_lines.append(s)
                except ValueError:
                    scoped_lines.append(s)
            else:
                scoped_lines.append(s)
        return "\n".join(scoped_lines)
    return ""


def _wrap_email_html_with_css(content_html: str, css_text: str) -> str:
    head = ["<meta charset='utf-8'>"]
    if css_text:
        head.append("<style type=\"text/css\">" + css_text + "</style>")
    shell = (
        "<!doctype html>\n"
        "<html><head>" + "".join(head) + "</head>"
        "<body><div class='email-page'><div class='email-body'>" + content_html + "</div></div></body></html>"
    )
    return shell

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


# -------- zh-CN -> zh-TW conversion (OpenCC) --------

def _maybe_convert_zh_cn_to_zh_tw(text: str) -> str:
    """Convert Simplified Chinese to Traditional Chinese (Taiwan) if OpenCC is available.

    Falls back to the original text when OpenCC is not installed.
    """
    if not text:
        return text
    try:
        from opencc import OpenCC  # type: ignore
        cc = OpenCC('s2tw')  # Simplified Chinese to Traditional Chinese (Taiwan)
        return cc.convert(text)
    except Exception:
        return text


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
    abs_url = None  # Initialize for footer generation
    # If selector mode is enabled, use ezoe scraper
    if EZOe_SELECTOR:
        try:
            import content_source_factory
            active_source = content_source_factory.get_active_source()
            selector_value = EZOe_SELECTOR  # Store in local scope
            content_block = active_source.get_daily_content(selector_value)
            html_day = content_block.html_content
            title = content_block.title
            plain_text_fallback = content_block.plain_text_content
        except Exception as e:
            # Fail the run so stateful script can advance selector; surface suggestion.
            msg = str(e)
            logger.error("Content source failed for %s: %s", EZOe_SELECTOR, msg)
            if "Try:" in msg or "Try selector:" in msg:
                logger.error("Suggested next selector: %s", msg)
            return 2

        # Remove links from content to make it suitable for email (links are interactive on website but not in email)
        soup = BeautifulSoup(html_day, "html.parser")
        for a in soup.find_all("a"):
            a.unwrap()  # Remove <a> tags but keep the text content

        # Remove modal dialog artifacts that are non-functional in email
        for modal in soup.find_all("div", {"class": "modal"}):
            modal.decompose()

        # Remove navigation images and unwanted UI elements
        for img in soup.find_all("img"):
            img.decompose()
        # Remove the styled span container if it's just for a home button image
        for span in soup.find_all("span", style=True):
            style_attr = str(span.get("style") or "")
            if "max-width" in style_attr and "background-color" in style_attr and not span.get_text(strip=True):
                span.decompose()

        html_day = str(soup)

        _debug_preview("EZOE_HTML", html_day)

        # When debugging, persist the raw day HTML to inspect content before wrapping/conversion.
        if _debug_enabled():
            try:
                import pathlib, re as _re
                out_dir = pathlib.Path("state")
                out_dir.mkdir(parents=True, exist_ok=True)
                raw_path = out_dir / "last_ezoe_day_raw.html"
                raw_path.write_text(html_day or "", encoding="utf-8")
                # quick sanity markers
                has_c = "id=\"c\"" in (html_day or "") or "id='c'" in (html_day or "")
                logger.info("DEBUG EZOE_HTML length=%s has_div_c=%s", len(html_day or ""), has_c)
            except Exception as _e:
                logger.info("DEBUG failed to write raw ezOE day html: %s", _e)

        # Build subject and plain-text fallback derived from same HTML; also provide source URL hint
        # Derive source URL based on content source
        source_name = active_source.get_source_name()
        if source_name == "wix":
            source_url = "https://churchintamsui.wixsite.com/index/morning-revival"
        elif source_name == "ezoe":
            try:
                vol, les, day = EZOe_SELECTOR.split("-")
                source_url = f"{EZOe_BASE.rstrip('/')}/2264-{int(vol)}-{int(les)}.html"
            except Exception:
                source_url = EZOe_BASE
        else:
            source_url = "https://example.com"  # fallback

        # Extract a simple title from HTML
        try:
            from bs4 import BeautifulSoup as _BS
            _s = _BS(html_day, "html.parser")
            title_tag = _s.find(["h1", "h2", "h3"]) or _s.find("title")
            title = title_tag.get_text(strip=True) if title_tag else "聖經之旅 每日內容"
        except Exception:
            title = "聖經之旅 每日內容"

        subject = f"聖經之旅 | {title} | {today}"
        # Ensure subject is zh-TW as well
        subject = _maybe_convert_zh_cn_to_zh_tw(subject)
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
        body = f"來源: {source_url}\n日期: {today}\n\n{plain_text_fallback or preview}"
        _debug_preview("EZOE_BODY", body)
        # Inline CSS from the original lesson page so Gmail renders without external links
        # Use a fixed, Gmail-safe custom stylesheet (scoped under .email-body)
        CUSTOM_CSS = (
            ".email-page{background:#f5f6f8;padding:24px 12px;}"
            ".email-body{margin:0 auto;max-width:720px;padding:20px 20px 28px;"
            "background:#ffffff;color:#1a1a1a;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.06);"
            "font:16px/1.65 -apple-system,BlinkMacSystemFont,\"Segoe UI\",Roboto,"
            "\"Noto Sans CJK TC\",\"Noto Sans CJK SC\",\"PingFang TC\",\"PingFang SC\",\"Hiragino Sans GB\",\"Microsoft YaHei\",Arial,sans-serif;"
            "-webkit-font-smoothing:antialiased;text-size-adjust:100%;}"
            ".email-body h1{font-size:24px;line-height:1.25;margin:12px 0;}"
            ".email-body h2{font-size:20px;line-height:1.3;margin:16px 0 10px;}"
            ".email-body h3{font-size:18px;line-height:1.35;margin:14px 0 8px;}"
            ".email-body h4,.email-body h5,.email-body h6{margin:12px 0 6px;line-height:1.4;}"
            ".email-body p{margin:10px 0;}"
            ".email-body ul,.email-body ol{margin:10px 0 10px 22px;padding:0;}"
            ".email-body li{margin:6px 0;}"
            ".email-body blockquote{margin:12px 0;padding:8px 12px;border-left:4px solid #e9e9e9;background:#fafafa;}"
            ".email-body a{color:#0b63ce;text-decoration:underline;}"
            ".email-body a:visited{color:#6b4dd6;}"
            ".email-body hr{border:0;border-top:1px solid #ececec;margin:16px 0;}"
            ".email-body img{max-width:100%;height:auto;border:0;}"
            ".email-body table{border-collapse:collapse;max-width:100%;}"
            ".email-body th,.email-body td{border:1px solid #e5e5e5;padding:6px 8px;}"
            ".email-body .note,.email-body .notice{padding:8px 12px;margin:10px 0;border-left:4px solid #f39c12;"
            "background:#fff8e6;color:#8a6d3b;font-size:13px;}"
        )
        html_with_css = _wrap_email_html_with_css(html_day, CUSTOM_CSS)
        # Append original link footer inside the email body
        # Use the content source's URL generation logic
        abs_url = active_source.get_content_url(selector_value)
        footer = (
            "<hr><p style=\"margin-top:12px;\">原文連結："
            f"<a href=\"{abs_url}\" target=\"_blank\" rel=\"noopener noreferrer\">{abs_url}</a>"
            "</p>"
        )
        # Inject footer before closing .email-body div and log for verification
        try:
            insertion_point = "</div></div></body></html>"
            html_with_css = html_with_css.replace("</div></div></body></html>", footer + insertion_point)
        except Exception:
            # Fallback: append to end if structure changed
            html_with_css = html_with_css + footer
        logger.info("Original link (anchored): %s", abs_url)
        # Persist the final wrapped HTML when debugging for comparison
        if _debug_enabled():
            try:
                import pathlib
                out_dir = pathlib.Path("state")
                out_dir.mkdir(parents=True, exist_ok=True)
                final_path = out_dir / "last_ezoe_email_wrapped.html"
                final_path.write_text(html_with_css or "", encoding="utf-8")
                # ensure conversion/sanitization didn't strip core container
                has_c2 = ("id=\"c\"" in (html_with_css or "")) or ("id='c'" in (html_with_css or ""))
                logger.info("DEBUG EZOE_HTML_WRAPPED length=%s has_div_c=%s", len(html_with_css or ""), has_c2)
            except Exception as _e:
                logger.info("DEBUG failed to write wrapped ezOE email html: %s", _e)
        # Convert visible content to zh-TW (server side) for both HTML and text
        html_with_css = _maybe_convert_zh_cn_to_zh_tw(html_with_css)
        body = _maybe_convert_zh_cn_to_zh_tw(body)
        send_email(subject, body, html_body=html_with_css)
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
    # Convert content to zh-TW prior to building/sending
    title = _maybe_convert_zh_cn_to_zh_tw(title)
    text_body = _maybe_convert_zh_cn_to_zh_tw(text_body)
    html_body = _to_html(title, lesson_url, today, text_body)
    html_body = _maybe_convert_zh_cn_to_zh_tw(html_body)
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
