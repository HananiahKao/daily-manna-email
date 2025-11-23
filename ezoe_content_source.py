#!/usr/bin/env python3
"""
Content source implementation for the original ezoe.work site.

This wraps the existing ezoe_week_scraper.py logic to conform to the new ContentSource interface.
"""

import os
import re
import content_source
ContentSource = content_source.ContentSource
ContentBlock = content_source.ContentBlock

try:
    from ezoe_week_scraper import get_day_html  # Original implementation
except ImportError:
    # Fallback for cases where the original module is not available
    raise RuntimeError("ezoe_week_scraper module not found. Install or symlink it.")

# Default base URL from original implementation
DEFAULT_EZOE_BASE = os.getenv("EZOE_BASE", "https://ezoe.work/books/2")


class EzoeContentSource(ContentSource):
    """Content source implementation for the original ezoe.work site."""

    def __init__(self, base_url: str = DEFAULT_EZOE_BASE):
        self.base_url = base_url

    def get_source_name(self) -> str:
        return "ezoe"

    def get_selector_type(self) -> str:
        return "volume-lesson-day"

    def get_daily_content(self, selector: str) -> ContentBlock:
        """Fetch content using the original ezoe scraper logic."""
        html_content = get_day_html(selector, base=self.base_url)

        # Extract plain text and title from the HTML (mimicking original logic)
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

        # Remove non-content elements
        for sel in ["script", "style", "nav", "footer", "iframe", ".modal", "img", "a[href]"]:
            for tag in soup.select(sel):
                tag.decompose()

        # Extract title (similar to original sjzl_daily_email logic)
        title = "聖經之旅 每日內容"
        title_tag = soup.find(["h1", "h2", "h3"])
        if title_tag and title_tag.get_text(strip=True):
            title = title_tag.get_text(strip=True)

        # Generate plain text content
        texts = []
        for el in soup.find_all(["p", "li", "h1", "h2", "h3"]):
            text = el.get_text(" ", strip=True)
            if text:
                texts.append(text)
        plain_text_content = "\n\n".join(texts) if texts else "(純文字預覽不可用；請查看 HTML 內容)"

        return ContentBlock(html_content, plain_text_content, title)

    def get_content_url(self, selector: str) -> str:
        """Return ezoe URL with anchor for the specific lesson day."""
        base_url = self._ezoe_lesson_url(selector, self.base_url)
        # Prefer detecting the actual anchor id from the live page, fallback to static mapping
        anchor_id = self._ezoe_detect_anchor_id(selector, self.base_url) or self._ezoe_day_anchor(selector)
        return base_url + (f"#{anchor_id}" if anchor_id else "")

    def get_email_subject(self, selector: str, content_title: str) -> str:
        """Return email subject for Ezoe content source with weekday and content title.
        Handles Simplified‑Chinese weekday prefixes by converting them to Traditional
        before deduplication.
        """
        # Map day number to Traditional Chinese weekday
        day_map = {
            1: "週一",
            2: "週二",
            3: "週三",
            4: "週四",
            5: "週五",
            6: "週六",
            7: "主日",
        }

        # Extract weekday from selector (format: "volume-lesson-day")
        try:
            parts = selector.split("-")
            day_num = int(parts[2])
            weekday = day_map.get(day_num, "週一")
        except (ValueError, IndexError):
            weekday = "週一"

        # ---- NEW: Normalise title ----
        # Convert any Simplified Chinese weekday prefix (周) to Traditional (週)
        cleaned_content = content_title.strip().replace("周", "週")

        # If the title already starts with the weekday, keep it as‑is
        if cleaned_content.startswith(weekday):
            final_title = cleaned_content
        else:
            final_title = f"{weekday} {cleaned_content}" if cleaned_content else weekday

        return f"聖經之旅 | {final_title}"

    def _ezoe_lesson_url(self, selector: str, base: str) -> str:
        """Build lesson URL like https://ezoe.work/books/2/2264-<volume>-<lesson>.html from selector 'v-l-d'."""
        import re as _re
        m = _re.fullmatch(r"(\d+)-(\d+)-(\d)", selector)
        if not m:
            raise ValueError("Invalid EZOe selector format: '<volume>-<lesson>-<day>'")
        vol = int(m.group(1)); les = int(m.group(2))
        filename = f"2264-{vol}-{les}.html"
        from urllib.parse import urljoin
        return urljoin(base.rstrip('/') + '/', filename)

    def _ezoe_day_anchor(self, selector: str):
        """Return day anchor id like '1_6'..'1_12' from selector 'v-l-d'."""
        try:
            _v, _l, d = selector.split("-")
            di = int(d)
            if 1 <= di <= 7:
                return f"1_{5 + di}"
        except Exception:
            return None

    def _ezoe_detect_anchor_id(self, selector: str, base: str) -> str:
        """Best-effort detect the actual day anchor id from the live lesson page."""
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
