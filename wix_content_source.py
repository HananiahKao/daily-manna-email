#!/usr/bin/env python3
"""
Content source implementation for the Wix 'Morning Revival' site.

Fetches content from churchintamsui.wixsite.com/index/morning-revival.
"""

import requests
from bs4 import BeautifulSoup
import content_source
ContentSource = content_source.ContentSource
ContentBlock = content_source.ContentBlock

# Fixed Wix URL for the morning revival
WIX_URL = "https://churchintamsui.wixsite.com/index/morning-revival"
HEADERS = {"User-Agent": "daily-manna-wix/1.0 (+non-commercial)"}

# Chinese weekday labels used by the site
WEEKDAY_LABELS = {
    "【週一】": 1,
    "【週二】": 2,
    "【週三】": 3,
    "【週四】": 4,
    "【週五】": 5,
    "【週六】": 6,
    "【主日】": 7,
}

# Combined markers for sections spanning multiple days
SECTION_MARKERS = list(WEEKDAY_LABELS.keys()) + ["【週四、週五】"]


class WixContentSource(ContentSource):
    """Content source implementation for the Wix 'Morning Revival' site."""

    def get_source_name(self) -> str:
        return "wix"

    def get_selector_type(self) -> str:
        return "chinese-weekday"

    def get_daily_content(self, selector: str) -> ContentBlock:
        """Fetch and segment content from the Wix page based on Chinese weekday selector."""
        # Fetch the current week's content
        response = requests.get(WIX_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()

        # Decode with UTF-8
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.content, 'html.parser')

        # Find the main content area - may need inspection to confirm selector
        # Based on typical Wix structure; adjust if needed
        main_content = self._find_main_content(soup)

        if not main_content:
            raise ValueError("Could not find main content area on Wix page")

        # Segment content by weekday labels
        segments = self._segment_by_weekdays(main_content)

        if selector not in segments:
            raise ValueError(f"Weekday selector '{selector}' not found on Wix page")

        content_html = segments[selector]

        # Extract clean HTML for email
        soup_content = BeautifulSoup(f"<div>{content_html}</div>", 'html.parser')

        # Remove non-essential elements
        for sel in ["script", "style", "nav", "footer", "iframe", ".header", ".feature", "#btt", "#toptitle"]:
            for tag in soup_content.select(sel):
                tag.decompose()

        # Extract title (use weekday as title, or find h1/h2 if present)
        title = selector.strip("【】")  # e.g., "週一"
        title_tag = soup_content.find(["h1", "h2", "h3"])
        if title_tag and title_tag.get_text(strip=True):
            title = title_tag.get_text(strip=True)

        # Generate plain text
        plain_text_content = self._extract_plain_text(soup_content)

        # Wrap content with weekday header
        html_content = f"<h3>{title}</h3>{str(soup_content)}"

        return ContentBlock(html_content, plain_text_content, title)

    def _find_main_content(self, soup: BeautifulSoup):
        """Locate the main content container on the Wix page based on actual structure."""
        # Based on browser inspection, look for the main content area with "晨興聖言" (Morning Revival)
        # First try to find sections containing the weekday markers
        weekday_markers = ["【週一】", "【週二】", "【週三】", "【週四】", "【週五】", "【週六】", "【主日】"]

        # Look for content that contains these markers
        best_candidate = None
        max_markers = 0

        # Try main containers first
        candidates = [
            soup.find("main"),  # Main semantic tag
            soup.select_one("div[data-testid='rich-text-viewer']"),  # Common Wix rich text container
            soup.find("article"),
            soup.select_one("div.main-content"),
            soup.select_one("div[data-testid='article-content']"),
        ]

        for candidate in candidates:
            if candidate:
                text_content = candidate.get_text()
                marker_count = sum(1 for marker in weekday_markers if marker in text_content)
                if marker_count > max_markers:
                    max_markers = marker_count
                    best_candidate = candidate

        # If we found a container with markers, use it
        if best_candidate:
            return best_candidate

        # Fallback: search the entire body for content with markers
        body = soup.find("body")
        if body:
            text_content = body.get_text()
            has_markers = any(marker in text_content for marker in weekday_markers)
            if has_markers:
                return body

        # Final fallback
        return soup.find("body") or soup

    def _segment_by_weekdays(self, content) -> dict:
        """Split content into segments based on 【週X】 headings."""
        segments = {}

        # Find all paragraph elements in the content
        all_paragraphs = content.find_all(['p', 'h2', 'h3'])

        current_selector = None
        current_segments = []

        for p in all_paragraphs:
            text = p.get_text(strip=True)

            # Check if this paragraph starts a new weekday section
            found_marker = None
            for marker in SECTION_MARKERS:
                if marker in text or text.startswith(marker):
                    found_marker = marker
                    break

            if found_marker:
                # Save previous segment in dictionary
                if current_selector and current_segments:
                    # Combine all paragraphs in this segment
                    content_html = '\n'.join([str(seg) for seg in current_segments])
                    segments[current_selector] = content_html

                # Start new segment
                current_selector = found_marker
                current_segments = []
            elif current_selector:
                # Add content to current segment
                current_segments.append(p)

        # Add the last segment
        if current_selector and current_segments:
            content_html = '\n'.join([str(seg) for seg in current_segments])
            segments[current_selector] = content_html

        return segments

    def _extract_plain_text(self, soup: BeautifulSoup) -> str:
        """Extract readable plain text from HTML content."""
        # Remove unwanted elements
        for sel in ["script", "style", "nav", "footer", "iframe"]:
            for tag in soup.select(sel):
                tag.decompose()

        # Extract text from meaningful elements
        texts = []
        for el in soup.find_all(["p", "li", "h1", "h2", "h3", "blockquote", "pre"]):
            t = el.get_text(" ", strip=True)
            if t and len(t) >= 2:
                texts.append(t)

        # Remove duplicates to fix the duplication issue
        unique_texts = []
        for text in texts:
            if text not in unique_texts:
                unique_texts.append(text)

        if len(unique_texts) < 3:
            # Fallback to raw text extraction when structured extraction yields insufficient content
            raw = soup.get_text("\n", strip=True)
            lines = [ln for ln in raw.splitlines() if len(ln.strip()) >= 2]
            # Remove duplicates from fallback as well
            unique_lines = []
            for line in lines[:200]:
                if line not in unique_lines:
                    unique_lines.append(line)
            unique_texts = unique_lines

        return "\n\n".join(unique_texts) if unique_texts else "(純文字預覽不可用；請查看 HTML 內容)"

    def get_content_url(self, selector: str) -> str:
        """Return Wix base URL (no anchoring since Wix uses single-page design)."""
        return WIX_URL
