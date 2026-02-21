#!/usr/bin/env python3
"""
Content source implementation for the mana.stmn1.com Bible Journey site.
"""

import logging
import os
import re
from typing import Optional
import content_source
ContentSource = content_source.ContentSource
ContentBlock = content_source.ContentBlock

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Default base URL for the stmn1 Bible Journey site
DEFAULT_STMN1_BASE = os.getenv("STMN1_BASE", "https://mana.stmn1.com/books/2264")


class Stmn1ContentSource(ContentSource):
    """Content source implementation for the mana.stmn1.com Bible Journey site."""

    def __init__(self, base_url: str = DEFAULT_STMN1_BASE):
        self.base_url = base_url

    def get_source_name(self) -> str:
        return "stmn1"

    def get_selector_type(self) -> str:
        return "volume-lesson-day"

    def get_daily_content(self, selector: str) -> ContentBlock:
        """Fetch and process daily content from stmn1.com."""
        volume, lesson, day = self.parse_selector(selector)
        
        # Get lesson page URL
        lesson_url = self._get_lesson_url(volume, lesson)
        
        # Fetch and parse lesson content
        html = self._fetch(lesson_url)
        if not html:
            raise RuntimeError(f"Failed to fetch lesson content from {lesson_url}")
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract daily content by weekday
        daily_content = self._extract_daily_section(soup, day)
        
        # Extract title
        title = self._extract_title(soup)
        
        # Generate plain text content
        plain_text_content = self._html_to_plain_text(daily_content)
        
        return ContentBlock(daily_content, plain_text_content, title)

    def get_content_url(self, selector: str) -> str:
        """Return stmn1 URL for the given selector with anchor if available."""
        volume, lesson, day = self.parse_selector(selector)
        base_url = self._get_lesson_url(volume, lesson)
        anchor_id = str(day)
        return f"{base_url}#{anchor_id}"

    def get_email_subject(self, selector: str, content_title: str) -> str:
        """Return email subject for stmn1 content source with weekday and content title."""
        day_map = {
            1: "周一",
            2: "周二",
            3: "周三",
            4: "周四",
            5: "周五",
            6: "周六",
            7: "主日",
        }
        
        try:
            parts = selector.split("-")
            day_num = int(parts[2])
            weekday = day_map.get(day_num, "周一")
        except (ValueError, IndexError):
            weekday = "周一"
        
        # Keep original content title but check for weekday prefix
        original_content = content_title.strip()
        
        # Check if content already starts with any weekday prefix
        has_weekday_prefix = False
        for day in day_map.values():
            if original_content.startswith(day):
                has_weekday_prefix = True
                break
        
        if has_weekday_prefix:
            final_title = original_content
        else:
            final_title = f"{weekday} {original_content}" if original_content else weekday
        
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
        # Prioritize the full selector if provided
        selector = os.environ.get("STMN1_SELECTOR")
        if selector:
            try:
                self.parse_selector(selector)
                return selector
            except ValueError:
                pass
        
        volume = int(os.environ.get("STMN1_VOLUME", "1"))
        lesson = int(os.environ.get("STMN1_LESSON", "1"))
        day = int(os.environ.get("STMN1_DAY_START", "1"))
        return self.format_selector((volume, lesson, day))

    def parse_batch_selectors(self, input_text: str) -> list[str]:
        """Parse stmn1 batch input with support for range syntax."""
        if not input_text or not input_text.strip():
            return []
        
        input_text = input_text.strip()
        
        range_match = re.match(r'^(.+?)\s+to\s+(.+)$', input_text, re.IGNORECASE)
        if range_match:
            start = range_match.group(1).strip()
            end = range_match.group(2).strip()
            return self._generate_selector_range(start, end)
        
        selectors = re.split(r'[,\n]+', input_text)
        selectors = [s.strip() for s in selectors if s.strip()]
        
        for selector in selectors:
            if not self.validate_selector(selector):
                raise ValueError(f"Invalid stmn1 selector: '{selector}'. Expected format: volume-lesson-day (e.g., 1-1-1)")
        
        return selectors

    def _generate_selector_range(self, start: str, end: str) -> list[str]:
        """Generate a range of stmn1 selectors from start to end."""
        try:
            start_vol, start_lesson, start_day = self.parse_selector(start)
            end_vol, end_lesson, end_day = self.parse_selector(end)
        except ValueError as e:
            raise ValueError(f"Invalid range: {e}")
        
        if start_vol != end_vol or start_lesson != end_lesson:
            raise ValueError(
                f"Range must be within same volume and lesson. "
                f"Got: {start} to {end}"
            )
        
        if start_day > end_day:
            raise ValueError(
                f"Range start day must be <= end day. Got: {start} to {end}"
            )
        
        selectors = []
        for day in range(start_day, end_day + 1):
            selectors.append(self.format_selector((start_vol, start_lesson, day)))
        
        return selectors

    def supports_range_syntax(self) -> bool:
        return True

    def get_batch_ui_config(self) -> dict:
        return {
            "placeholder": "e.g., 1-1-1 to 1-1-7 or 1-1-1, 1-1-2, 1-1-3",
            "help_text": "stmn1 format: volume-lesson-day. Use 'X to Y' for ranges within the same lesson.",
            "examples": ["1-1-1", "1-1-2", "1-1-3"],
            "supports_range": True,
            "range_example": "1-1-1 to 1-1-7",
        }

    def _get_lesson_url(self, volume: int, lesson: int) -> str:
        """Generate lesson URL from volume and lesson numbers."""
        lesson_num = self._get_absolute_lesson_number(volume, lesson)
        filename = f"{lesson_num:03d}.html"
        from urllib.parse import urljoin
        return urljoin(self.base_url.rstrip('/') + '/', filename)

    def _get_volume_index_url(self, volume: int) -> str:
        """Generate volume index URL from volume number."""
        filename = f"index{volume:02d}.html"
        from urllib.parse import urljoin
        return urljoin(self.base_url.rstrip('/') + '/', filename)

    def _get_absolute_lesson_number(self, volume: int, lesson: int) -> int:
        """Calculate absolute lesson number from volume and lesson."""
        lessons_per_volume = 18
        # Pattern: Each volume starts at (volume * 19) - 19 + 1, with 18 lessons
        # Volume 1: 001-018 (18 lessons)
        # Volume 2: 020-037 (18 lessons) - gap at 019
        # Volume 3: 039-056 (18 lessons) - gap at 038
        # Volume 4: 058-075 (18 lessons) - gap at 057, etc.
        start = (volume * 19) - 19
        return start + lesson

    def _fetch(self, url: str) -> Optional[str]:
        """Fetch URL content with error handling."""
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=30)
            response.encoding = response.apparent_encoding or 'utf-8'
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    def _extract_daily_section(self, soup: BeautifulSoup, day: int) -> str:
        """Extract daily content section by day number (1-7)."""
        # Day heading patterns: 周一、周二、...、周六、主日
        day_headers = [
            "周一", "周二", "周三", "周四", 
            "周五", "周六", "主日"
        ]
        
        target_header = day_headers[day - 1]
        
        # Find all paragraph elements
        paragraphs = soup.find_all('p')
        
        content = []
        collecting = False
        
        for p in paragraphs:
            text = p.get_text(strip=True)
            
            # Check if this paragraph contains the day header
            if text.startswith(f"《{target_header}》"):
                collecting = True
                content.append(str(p))
            elif collecting:
                # Stop collecting when we reach the next day's header
                next_day_found = False
                for next_header in day_headers:
                    if text.startswith(f"《{next_header}》") and next_header != target_header:
                        next_day_found = True
                        break
                        
                if not next_day_found and text and not text.startswith("问题讨论："):
                    content.append(str(p))
                elif next_day_found or text.startswith("问题讨论："):
                    break
        
        # If we found content, wrap it in a div with appropriate styling
        if content:
            return '<div class="daily-content">' + ''.join(content) + '</div>'
        
        # Fallback: return all content if we couldn't find the specific day section
        logger.warning(f"Failed to find specific day section for day {day}, returning full content")
        return str(soup.find('body') or soup)

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract title from lesson page."""
        title = "聖經之旅 每日內容"
        
        # Check page title (preferred source)
        if soup.title and soup.title.string:
            title = soup.title.string.strip().replace("圣经之旅第", "聖經之旅第").replace("册丨", "冊｜")
        else:
            # Fallback to first heading only if no meta title
            title_tag = soup.find(["h1", "h2", "h3"])
            if title_tag and title_tag.get_text(strip=True):
                title = title_tag.get_text(strip=True)
        
        return title

    def _html_to_plain_text(self, html: str) -> str:
        """Convert HTML content to plain text."""
        soup = BeautifulSoup(html, 'html.parser')
        
        for tag in soup.find_all(["script", "style", "iframe"]):
            tag.decompose()
        
        texts = []
        for el in soup.find_all(["p", "li", "h1", "h2", "h3"]):
            text = el.get_text(" ", strip=True)
            if text:
                texts.append(text)
        
        return "\n\n".join(texts) if texts else "(純文字預覽不可用；請查看 HTML 內容)"