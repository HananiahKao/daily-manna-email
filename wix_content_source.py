#!/usr/bin/env python3
"""
Content source implementation for the Wix 'Morning Revival' site.

Fetches content from churchintamsui.wixsite.com/index/morning-revival.
"""

import requests
from bs4 import BeautifulSoup
import re
import logging
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

# Regex pattern to match lower section markers like "第一週•週一", "第一週•週二", etc.
# Uses flexible matching to handle various separators between week and day
# The week number uses Chinese numerals (一二三四五六七八九十), so we match any characters
# Future-proof: allows any characters between "週" and the day part
LOWER_SECTION_PATTERN = re.compile(r'第.+?週.*?(週[一二三四五六日]|主日)')

# Combined markers for sections spanning multiple days (for backward compatibility)
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

        # Clean up Wix-specific styling and empty paragraphs
        self._clean_wix_html(soup_content)

        # Extract title - look for meaningful content title
        title = selector.strip("【】")  # Default to weekday e.g., "週一"
        
        # Try to find a better title from the content
        # Look for bold text or headings that might be the section title
        for tag in soup_content.find_all(["strong", "b", "span"]):
            text = tag.get_text(strip=True)
            # Look for common section titles
            if text and len(text) < 20 and any(keyword in text for keyword in ["晨興", "信息", "餧養", "選讀", "禱告"]):
                title = text
                break
        
        # If no meaningful title found, try h1/h2/h3 (but not if it's just the weekday)
        if title == selector.strip("【】"):
            title_tag = soup_content.find(["h1", "h2", "h3"])
            if title_tag:
                tag_text = title_tag.get_text(strip=True)
                if tag_text and tag_text != selector.strip("【】"):
                    title = tag_text

        # Generate plain text
        plain_text_content = self._extract_plain_text(soup_content)

        # Wrap content with weekday header (use weekday for the header, not the extracted title)
        weekday_label = selector.strip("【】")
        html_content = f"<h3>{weekday_label}</h3>{str(soup_content)}"

        return ContentBlock(html_content, plain_text_content, title)

    def _find_main_content(self, soup: BeautifulSoup):
        """Locate the main content container on the Wix page based on actual structure."""
        # Based on browser inspection, we want the LOWER section with "晨興餧養" and "信息選讀"
        # Look for content indicators from the lower section
        lower_section_indicators = ["晨興餧養", "信息選讀"]
        
        # Look for content that contains the lower section pattern (第X週■週Y)
        best_candidate = None
        max_score = 0

        # Try main containers first
        candidates = [
            soup.find("main"),  # Main semantic tag
            soup.select_one("div[data-testid='rich-text-viewer']"),  # Common Wix rich text container
            soup.find("article"),
            soup.select_one("div.main-content"),
            soup.select_one("div[data-testid='article-content']"),
            soup.find("body"),  # Fallback to body
        ]

        for candidate in candidates:
            if candidate:
                text_content = candidate.get_text()
                # Score based on lower section indicators and pattern matches
                indicator_count = sum(1 for indicator in lower_section_indicators if indicator in text_content)
                pattern_matches = len(LOWER_SECTION_PATTERN.findall(text_content))
                score = indicator_count * 10 + pattern_matches
                
                if score > max_score:
                    max_score = score
                    best_candidate = candidate

        # If we found a container with lower section content, use it
        if best_candidate and max_score > 0:
            return best_candidate

        # Final fallback
        return soup.find("body") or soup

    def _segment_by_weekdays(self, content) -> dict:
        """Split content into segments based on lower section markers (第X週•週Y)."""
        segments = {}
        logger = logging.getLogger(__name__)

        # Find all paragraph elements in the content that can contain markers
        all_paragraphs = content.find_all(['p', 'h2', 'h3', 'h4', 'div'])

        current_selector = None
        current_segments = []

        for p in all_paragraphs:
            text = p.get_text(strip=True)

            # Check if this paragraph starts a new weekday section using the lower section pattern
            match = LOWER_SECTION_PATTERN.search(text)

            if match:
                # Extract the weekday part (週一, 週二, etc. or 主日)
                weekday = match.group(1)
                # Convert to the selector format expected by caller: 【週一】, 【週二】, etc.
                if weekday == "主日":
                    found_marker = "【主日】"
                else:
                    found_marker = f"【{weekday}】"

                # Save previous segment in dictionary
                if current_selector and current_segments:
                    # Combine all paragraphs in this segment, preserving HTML structure
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

        # Debug logging
        found_patterns = list(segments.keys())
        logger.info(f"Wix selector patterns found: {found_patterns}")
        logger.info(f"Wix segments extracted: {list(segments.keys())}")

        if not segments:
            logger.warning("No Wix selector patterns found - page structure may have changed")

        return segments

    def _clean_wix_html(self, soup: BeautifulSoup) -> None:
        """Clean up Wix-specific HTML elements and styling that cause spacing issues in emails."""
        # Remove Wix-specific classes and inline styles
        wix_classes_to_remove = [
            'font_8', 'wixui-rich-text__text', 'backcolor_44', 'color_43',
            'font_9', 'font_10', 'wixui-rich-text', 'wixGuard'
        ]

        # Remove Wix classes from all elements
        for element in soup.find_all(attrs={'class': True}):
            classes = element.get('class')
            if classes is None:
                continue
            if isinstance(classes, str):
                classes = classes.split()
            elif not isinstance(classes, list):
                continue
            # Remove Wix-specific classes
            filtered_classes = [cls for cls in classes if not any(wix_cls in cls for wix_cls in wix_classes_to_remove)]
            if filtered_classes:
                element['class'] = filtered_classes
            else:
                del element['class']

        # Remove Wix inline styles that affect spacing
        for element in soup.find_all(style=True):
            style_attr = element.get('style')
            if not isinstance(style_attr, str):
                continue
            style = style_attr
            # Remove font-size declarations that might override email CSS
            style = re.sub(r'font-size\s*:\s*[^;]+;', '', style)
            # Remove other Wix-specific style properties
            style = re.sub(r'font-family\s*:\s*[^;]+;', '', style)
            # Clean up empty or whitespace-only style attributes
            style = style.strip()
            if style:
                element['style'] = style
            else:
                del element['style']

        # Remove empty paragraphs that contain only zero-width spaces or whitespace
        for p in soup.find_all('p'):
            text_content = p.get_text(strip=True)
            # Remove paragraphs that are empty or contain only zero-width spaces
            if not text_content or text_content == '​' or all(ord(c) in (8203, 160, 32) for c in text_content):
                p.decompose()
                continue

            # Also remove paragraphs that have no meaningful content after cleaning
            if not p.find_all(['strong', 'b', 'em', 'i', 'span']) and len(text_content) < 3:
                p.decompose()

        # Flatten nested spans that don't add value
        for span in soup.find_all('span'):
            # If span has no attributes and only contains text or simple elements, unwrap it
            if not span.attrs and span.parent and span.parent.name in ['p', 'div']:
                span.unwrap()

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

    def get_email_subject(self, selector: str, content_title: str) -> str:
        """Return email subject for Wix content source with weekday only.
        The content title is constant (晨興餧養) and should not appear in the subject.
        """
        # Extract weekday from selector (format: 【週一】, 【週二】, etc.)
        weekday = selector.strip("【】")  # e.g., "週一", "主日"
        return f"晨興聖言 | {weekday}"

    def parse_selector(self, selector: str) -> int:
        """Parse Wix selector (e.g., 【週一】) into a weekday index (0=Mon, 6=Sun)."""
        clean = selector.strip("【】")
        for label, index in WEEKDAY_LABELS.items():
            if label.strip("【】") == clean:
                return index - 1  # Convert 1-7 to 0-6
        # Fallback/Reverse lookup if needed or error
        raise ValueError(f"Invalid Wix selector: {selector}")

    def format_selector(self, parsed: int) -> str:
        """Format weekday index (0-6) back to Wix selector."""
        if not (0 <= parsed <= 6):
            raise ValueError("Weekday index must be 0..6")
        # WEEKDAY_LABELS values are 1-7
        target = parsed + 1
        for label, index in WEEKDAY_LABELS.items():
            if index == target:
                return label
        raise ValueError(f"Could not format weekday index: {parsed}")

    def advance_selector(self, selector: str) -> str:
        """Cycle through weekdays."""
        current = self.parse_selector(selector)
        next_day = (current + 1) % 7
        return self.format_selector(next_day)

    def previous_selector(self, selector: str) -> str:
        """Cycle backwards through weekdays."""
        current = self.parse_selector(selector)
        prev_day = (current - 1) % 7
        return self.format_selector(prev_day)

    def validate_selector(self, selector: str) -> bool:
        try:
            self.parse_selector(selector)
            return True
        except ValueError:
            return False

    def get_default_selector(self) -> str:
        """Default to Monday."""
        return "【週一】"

    def parse_batch_selectors(self, input_text: str) -> list[str]:
        """Parse Wix batch input with support for weekday range syntax."""
        if not input_text or not input_text.strip():
            return []
        
        input_text = input_text.strip()
        
        # Check for range syntax: "X to Y" (supporting various forms)
        range_patterns = [
            (r'^(.+?)\s+to\s+(.+)$', 'to'),      # English "to"
            (r'^(.+?)\s+TO\s+(.+)$', 'TO'),      # Uppercase
            (r'^(.+?)\s+到\s+(.+)$', '到'),      # Chinese "to"
        ]
        
        for pattern, separator in range_patterns:
            range_match = re.match(pattern, input_text, re.IGNORECASE if separator.lower() == 'to' else 0)
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
                raise ValueError(
                    f"Invalid Wix selector: '{selector}'. "
                    f"Expected format: 【週一】, 【週二】, etc."
                )
        
        return selectors

    def _generate_selector_range(self, start: str, end: str) -> list[str]:
        """Generate a range of Wix selectors from start to end weekday."""
        # Parse start and end selectors
        try:
            start_index = self.parse_selector(start)  # 0-6
            end_index = self.parse_selector(end)      # 0-6
        except ValueError as e:
            raise ValueError(f"Invalid range: {e}")
        
        # Generate range (wrapping around if needed, e.g., Fri to Mon)
        selectors = []
        current = start_index
        
        # Handle both forward and backward ranges
        if start_index <= end_index:
            # Forward range: Mon to Fri
            while current <= end_index:
                selectors.append(self.format_selector(current))
                current += 1
        else:
            # Wrap-around range: Fri to Mon (Fri, Sat, Sun, Mon)
            while current <= 6:
                selectors.append(self.format_selector(current))
                current += 1
            current = 0
            while current <= end_index:
                selectors.append(self.format_selector(current))
                current += 1
        
        return selectors

    def supports_range_syntax(self) -> bool:
        return True

    def get_batch_ui_config(self) -> dict:
        return {
            "placeholder": "e.g., 【週一】 to 【週五】 or 【週一】, 【週二】, 【週三】",
            "help_text": "Wix format: Chinese weekday markers. Use 'X to Y' for ranges or separate with commas.",
            "examples": ["【週一】", "【週二】", "【週三】", "【週四】", "【週五】"],
            "supports_range": True,
            "range_example": "【週一】 to 【週五】",
        }
