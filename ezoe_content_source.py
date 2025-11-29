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

    def parse_selector(self, selector: str) -> tuple[int, int, int]:
        parts = selector.strip().split("-")
        if len(parts) != 3:
            raise ValueError(f"invalid selector: {selector}")
        volume, lesson, day = (int(parts[0]), int(parts[1]), int(parts[2]))
        if not (1 <= day <= 7):
            raise ValueError("selector day must be 1..7")
        if volume <= 0 or lesson <= 0:
            raise ValueError("selector components must be positive")
        return volume, lesson, day

    def format_selector(self, parsed: tuple[int, int, int]) -> str:
        volume, lesson, day = parsed
        if not (1 <= day <= 7):
            raise ValueError("day must be 1..7")
        if volume <= 0 or lesson <= 0:
            raise ValueError("volume and lesson must be positive")
        return f"{volume}-{lesson}-{day}"

    def advance_selector(self, selector: str) -> str:
        volume, lesson, day = self.parse_selector(selector)
        day += 1
        if day > 7:
            day = 1
            lesson += 1
        return self.format_selector((volume, lesson, day))

    def previous_selector(self, selector: str) -> str:
        volume, lesson, day = self.parse_selector(selector)
        day -= 1
        if day < 1:
            day = 7
            lesson = max(1, lesson - 1)
        return self.format_selector((volume, lesson, day))

    def validate_selector(self, selector: str) -> bool:
        try:
            self.parse_selector(selector)
            return True
        except ValueError:
            return False

    def get_default_selector(self) -> str:
        # Prioritize the full selector if provided (legacy support)
        selector = os.environ.get("EZOE_SELECTOR")
        if selector:
            try:
                self.parse_selector(selector)
                return selector
            except ValueError:
                pass  # Fallback if invalid

        volume = int(os.environ.get("EZOE_VOLUME", "2"))
        lesson = int(os.environ.get("EZOE_LESSON", "1"))
        day = int(os.environ.get("EZOE_DAY_START", "1"))
        return self.format_selector((volume, lesson, day))

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

    def get_max_lesson(self, volume: int) -> int:
        """
        Return the maximum valid lesson number for the given volume.
        Returns 0 if no lessons found or error.
        """
        try:
            # Lazy import to avoid circular dependency if any
            import ezoe_week_scraper as ez
            lessons = ez.get_volume_lessons(volume, base=self.base_url)
            return max(lessons) if lessons else 0
        except Exception:
            return 0

    def validate_lesson_exists(self, volume: int, lesson: int) -> bool:
        """Check if a specific lesson exists and is valid (not a map/manual)."""
        try:
            import ezoe_week_scraper as ez
            lessons = ez.get_volume_lessons(volume, base=self.base_url)
            return lesson in lessons
        except Exception:
            # Fail open or closed? 
            # If we can't check, maybe assume valid to avoid blocking?
            # But the goal is to block invalid ones.
            # Let's assume False if we can't verify, but log it?
            # For now, return False to be safe against garbage.
            return False

    def parse_batch_selectors(self, input_text: str) -> list[str]:
        """Parse Ezoe batch input with support for range syntax."""
        if not input_text or not input_text.strip():
            return []
        
        input_text = input_text.strip()
        
        # Check for range syntax: "X to Y"
        range_match = re.match(r'^(.+?)\s+to\s+(.+)$', input_text, re.IGNORECASE)
        if range_match:
            start = range_match.group(1).strip()
            end = range_match.group(2).strip()
            return self._generate_selector_range(start, end)
        
        # Otherwise, split by comma or newline
        selectors = re.split(r'[,\n]+', input_text)
        selectors = [s.strip() for s in selectors if s.strip()]
        
        # Validate each selector
        for selector in selectors:
            if not self.validate_selector(selector):
                raise ValueError(f"Invalid Ezoe selector: '{selector}'. Expected format: volume-lesson-day (e.g., 2-1-15)")
        
        return selectors

    def _generate_selector_range(self, start: str, end: str) -> list[str]:
        """Generate a range of Ezoe selectors from start to end."""
        # Parse start and end selectors
        try:
            start_vol, start_lesson, start_day = self.parse_selector(start)
            end_vol, end_lesson, end_day = self.parse_selector(end)
        except ValueError as e:
            raise ValueError(f"Invalid range: {e}")
        
        # Validate same volume and lesson
        if start_vol != end_vol or start_lesson != end_lesson:
            raise ValueError(
                f"Range must be within same volume and lesson. "
                f"Got: {start} to {end}"
            )
        
        # Validate start <= end
        if start_day > end_day:
            raise ValueError(
                f"Range start day must be <= end day. Got: {start} to {end}"
            )
        
        # Generate range
        selectors = []
        for day in range(start_day, end_day + 1):
            selectors.append(self.format_selector((start_vol, start_lesson, day)))
        
        return selectors

    def supports_range_syntax(self) -> bool:
        return True

    def get_batch_ui_config(self) -> dict:
        return {
            "placeholder": "e.g., 2-1-15 to 2-1-19 or 2-1-15, 2-1-16, 2-1-17",
            "help_text": "Ezoe format: volume-lesson-day. Use 'X to Y' for ranges within the same lesson.",
            "examples": ["2-1-15", "2-1-16", "2-1-17"],
            "supports_range": True,
            "range_example": "2-1-15 to 2-1-19",
        }

