#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scraper for ezoe.work '聖經之旅' daily sections.

Exports:
  get_day_html(selector: str, base: str = 'https://ezoe.work/books/2') -> str

Selector format (standardized):
  "<volume_number>-<lesson_number>-<day>"
    - volume_number: int (e.g., 2 for 2264-2)
    - lesson_number: int (1-based lesson page within the volume, e.g., 1 for 2264-2-1)
    - day: 0..7 integer for day of the week, mapping:
        1 周一, 2 周二, 3 周三, 4 周四, 5 周五, 6 周六, 7 主日.
      Day 0 returns the entire lesson body (all days combined) as HTML.

Example:
  get_day_html('2-1-1')  -> volume 2, lesson 1, 周一 content HTML
  get_day_html('2-1-0')  -> volume 2, lesson 1, entire lesson HTML (combined)

Notes:
  - This module uses only requests + BeautifulSoup and performs simple parsing based on the
    visible day headings' text found on the lesson page, which is largely static.
"""

from __future__ import annotations

import re
from typing import Optional, List, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

HEADERS = {"User-Agent": "daily-manna-ezoe/1.0 (+non-commercial)"}
REQUEST_TIMEOUT = (10, 20)
try:
    import os as _os
    POLITE_DELAY_MS = int(_os.getenv("POLITE_DELAY_MS", "500"))
except Exception:
    POLITE_DELAY_MS = 500


DAY_LABELS = {
    1: "周一",
    2: "周二",
    3: "周三",
    4: "周四",
    5: "周五",
    6: "周六",
    7: "主日",
}

# Observed pattern on ezoe.work lesson pages: per-lesson day headers appear as
# elements with class 'cn1' and IDs like '1_6'..'1_12' corresponding roughly to
# 周一..主日 in order. Provide a best-effort mapping to prefer structural IDs
# when available.
DAY_ID_BY_INDEX = {
    1: "1_6",  # 周一
    2: "1_7",  # 周二
    3: "1_8",  # 周三
    4: "1_9",  # 周四
    5: "1_10", # 周五
    6: "1_11", # 周六
    7: "1_12", # 主日
}


def _decode_html(resp: requests.Response, url: str = "") -> Optional[str]:
    if resp.status_code != 200 or "text/html" not in resp.headers.get("Content-Type", ""):
        return None
    data = resp.content or b""
    # Prefer robust UTF-8 handling for known host(s)
    try:
        from urllib.parse import urlparse as _urlparse
        host = _urlparse(url).hostname or ""
    except Exception:
        host = ""
    if host.endswith("ezoe.work"):
        try:
            return data.decode("utf-8", errors="replace")
        except Exception:
            pass

    enc = resp.encoding
    if not enc:
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


def _fetch(url: str) -> Optional[str]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        return _decode_html(resp, url)
    except requests.RequestException:
        return None
    finally:
        # Polite pacing between requests
        try:
            if POLITE_DELAY_MS and POLITE_DELAY_MS > 0:
                import time as _time
                _time.sleep(POLITE_DELAY_MS / 1000.0)
        except Exception:
            pass


def _lesson_url(base: str, volume: int, lesson: int) -> str:
    # Book id root is fixed to 2264 in the provided link, with pattern 2264-<volume>-<lesson>.html
    # Base defaults to https://ezoe.work/books/2
    filename = f"2264-{volume}-{lesson}.html"
    return urljoin(base.rstrip("/") + "/", filename)


def _collect_until_next_day(start_node: Tag, day_texts: List[str], next_anchor: Optional[Tag] = None) -> List[Tag]:
    """Collect sibling nodes after start_node until next day boundary.

    If next_anchor is provided, stop when we reach it (by identity or containment).
    Otherwise, stop when a sibling's normalized text matches any known day label.
    """
    collected: List[Tag] = []
    node = start_node.next_sibling
    while node is not None:
        # Stop if we reached explicit next anchor
        if next_anchor is not None:
            # If the node is the anchor or contains it, stop
            try:
                if node is next_anchor or (getattr(node, 'find', None) and node.find(id=next_anchor.get('id'))):
                    break
            except Exception:
                pass
        # Skip pure strings between elements
        if isinstance(node, NavigableString):
            node = node.next_sibling
            continue
        txt = _norm_text(node.get_text())
        if next_anchor is None and txt in day_texts:
            break
        collected.append(node)
        node = node.next_sibling
    return collected


def _norm_text(s: str) -> str:
    # Normalize whitespace and common full-width spaces
    return re.sub(r"\s+", "", s.replace("\u3000", " ")).strip()


def _find_day_anchor(container: Tag, label: str) -> Optional[Tag]:
    # Prefer day rows within the main content: '.cn1' blocks under content container
    target = _norm_text(label)
    # Strong preference: cn1 blocks inside container
    for el in container.select('.cn1'):
        txt = _norm_text(el.get_text())
        if not txt:
            continue
        if target in txt or txt == target:
            return el
    # Secondary: any element in container where normalized text contains the label
    for el in container.find_all(True):
        txt = _norm_text(el.get_text())
        if not txt:
            continue
        if target in txt or txt == target:
            return el
    # Tertiary: structural hint by id pattern when present
    for el in container.select('[id^="1_"]'):
        txt = _norm_text(el.get_text())
        if not txt:
            continue
        if target in txt:
            return el
    return None


def _suggest_next_selector(volume: int, lesson: int, day: int) -> str:
    """Suggest the next logical selector given current triplet.

    Assumes days progress 1..7 then roll to next lesson with day=1.
    """
    if day < 7:
        return f"{volume}-{lesson}-{day + 1}"
    return f"{volume}-{lesson + 1}-1"


def get_day_html(selector: str, base: str = "https://ezoe.work/books/2") -> str:
    """
    Given standardized selector "<volume>-<lesson>-<day>", return HTML for that day's section.
    Day 0 returns combined HTML for the entire lesson content area (best-effort).
    Raises ValueError on bad selector or when content cannot be located.
    """
    m = re.fullmatch(r"(\d+)-(\d+)-(\d)", selector)
    if not m:
        raise ValueError("Invalid selector format. Expected '<volume>-<lesson>-<day>'")
    volume = int(m.group(1))
    lesson = int(m.group(2))
    day = int(m.group(3))
    if day < 0 or day > 7:
        suggestion = _suggest_next_selector(volume, lesson, max(1, min(day, 7)))
        raise ValueError(f"Day out of range (0..7). Try selector: {suggestion}")

    url = _lesson_url(base, volume, lesson)
    html = _fetch(url)
    if not html:
        # Treat as out-of-range lesson/volume. Provide suggestion to advance.
        suggestion = _suggest_next_selector(volume, lesson, max(1, day))
        raise ValueError(f"Lesson or volume not found for {selector}. Try: {suggestion}")

    soup = BeautifulSoup(html, "html.parser")

    # Heuristically identify the main content container: prefer primary lesson area
    # Typical structure uses <div class='main'> for lesson content.
    content_root = soup.select_one("div.main") or soup.find("body") or soup

    if day == 0:
        # Return the inner HTML of the detected content root (excluding scripts/styles)
        for sel in ["script", "style", "nav", "footer", "iframe"]:
            for t in content_root.select(sel):
                t.decompile = True
                t.decompose()
        return str(content_root)

    label = DAY_LABELS.get(day)
    if not label:
        raise ValueError("Unsupported day label")

    # Prefer robust text-based detection first; IDs vary per lesson
    anchor = _find_day_anchor(content_root, label)
    # Fallback to structural id mapping only if text-based detection failed
    if not anchor:
        day_id = DAY_ID_BY_INDEX.get(day)
        if day_id:
            anchor = content_root.find(id=day_id)
    if not anchor:
        # Treat missing anchor as out-of-range day for this lesson.
        suggestion = _suggest_next_selector(volume, lesson, day)
        raise ValueError(f"Day anchor not found for {selector}. Try: {suggestion}")

    # Determine section title from the day header block if available
    section_title = ""
    try:
        if anchor and anchor.get("class") and "cn1" in anchor.get("class", []):
            # Typical structure: <div class="cn1" id="1_8"><div>周三</div> <div>標題</div></div>
            # Gather immediate child divs and use the second one's text as title.
            child_divs = [c for c in anchor.find_all(recursive=False) if isinstance(c, Tag)]
            if len(child_divs) >= 2:
                t = child_divs[1].get_text(strip=True)
                if t:
                    section_title = t
            if not section_title:
                # Fallback: extract text excluding the day label
                full = _norm_text(anchor.get_text())
                lab = _norm_text(label)
                if full.startswith(lab):
                    section_title = full[len(lab):]
    except Exception:
        section_title = ""

    # Collect nodes after the day label until reaching the next label.
    # Prefer explicit structural next anchor when IDs are available.
    day_texts = [_norm_text(v) for v in DAY_LABELS.values()]
    next_anchor = None
    # Try to determine the next day boundary via text-based detection; if not found, fallback to id mapping
    try:
        next_label = DAY_LABELS.get(day + 1)
        if next_label:
            next_anchor = _find_day_anchor(content_root, next_label)
    except Exception:
        next_anchor = None
    if next_anchor is None:
        next_id = DAY_ID_BY_INDEX.get(day + 1)
        if next_id:
            next_anchor = content_root.find(id=next_id)
    nodes = _collect_until_next_day(anchor, day_texts, next_anchor=next_anchor)
    # Also include the immediate subtitle (often the next element following the label in a separate container)
    # If the first collected node is extremely short and there is another sibling text, keep as-is; we return raw HTML

    # Build a minimal wrapper to keep HTML valid and portable
    wrapper = soup.new_tag("div")
    header = soup.new_tag("h3")
    header.string = f"{label}  {section_title}" if section_title else label
    wrapper.append(header)
    # remove chrome from cloned nodes where possible
    for n in nodes:
        if isinstance(n, Tag):
            for sel in ["script", "style", "nav", "footer", "iframe", ".header", ".feature", "#btt", "#toptitle"]:
                for t in n.select(sel):
                    try:
                        t.decompose()
                    except Exception:
                        pass
        wrapper.append(n)

    return str(wrapper)


def get_volume_lessons(volume: int, base: str = "https://ezoe.work/books/2") -> List[int]:
    """
    Fetch the volume page (e.g. base/2264-<volume>.html) and return a sorted list of valid lesson numbers.
    Filters out non-lesson resources (maps, manuals, etc.) based on text patterns.
    """
    # Construct volume URL: e.g. https://ezoe.work/books/2/2264-2.html
    # Note: The base is typically .../books/2, so we append 2264-{volume}.html
    # If base ends with /, strip it.
    base = base.rstrip("/")
    url = f"{base}/2264-{volume}.html"
    
    html = _fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    valid_lessons = []
    
    # Regex to match lesson links: 2264-{volume}-{lesson}.html
    link_pattern = re.compile(r"2264-" + str(volume) + r"-(\d+)\.html")
    
    # Regex to identify valid lesson text (must contain "第" and "课")
    # and exclude known non-lesson keywords
    # Support both digits and Chinese numerals
    lesson_text_pattern = re.compile(r"第\s*[0-9一二三四五六七八九十百]+\s*课")
    blacklist_pattern = re.compile(r"(路线图|平面图|安营图|家长手册)")

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        m = link_pattern.search(href)
        if not m:
            continue
            
        lesson_num = int(m.group(1))
        
        # Get the link text and preceding text to validate
        text = _norm_text(a.get_text())
        
        # Sometimes the "第X课" is in a previous sibling text node
        # But based on inspection, the structure is often:
        # Text: "第一课" <a ...>Title</a>
        # So we should look at the previous sibling text if the link text itself doesn't have it.
        
        context_text = text
        prev = a.previous_sibling
        if isinstance(prev, NavigableString):
            context_text = _norm_text(str(prev)) + " " + text
        elif prev and hasattr(prev, 'get_text'):
             context_text = _norm_text(prev.get_text()) + " " + text

        if blacklist_pattern.search(context_text):
            continue
            
        # If it looks like a lesson (matches "第...课") and isn't blacklisted, include it.
        if lesson_text_pattern.search(context_text):
            valid_lessons.append(lesson_num)

    return sorted(list(set(valid_lessons)))


if __name__ == "__main__":
    import argparse, os, sys
    ap = argparse.ArgumentParser(description="Fetch a day's HTML from ezoe.work lesson page")
    ap.add_argument("selector", help="<volume>-<lesson>-<day>, day 0 returns full lesson HTML")
    ap.add_argument("--base", default="https://ezoe.work/books/2", help="Base URL for books path")
    ap.add_argument(
        "--out",
        help="Write HTML to tmp/decoded/[name].html (default name is selector)",
    )
    args = ap.parse_args()
    try:
        html = get_day_html(args.selector, base=args.base)
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)

    # If --out is provided, write to tmp/decoded path using UTF-8
    if args.out is not None:
        out_name = args.out.strip() or args.selector
        # sanitize filename minimally
        safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "-" for ch in out_name)
        out_dir = os.path.join(os.getcwd(), "tmp", "decoded")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{safe}.html")
        # Ensure browsers can render local file via file:// with correct charset by wrapping
        # in a minimal HTML shell including a UTF-8 meta tag when missing.
        html_to_write = html
        try:
            low = html.strip().lower()
            if "<html" not in low or "<meta" not in low or "charset" not in low:
                html_to_write = (
                    "<!doctype html>\n"
                    "<html><head><meta charset=\"utf-8\"></head><body>" + html + "</body></html>"
                )
        except Exception:
            html_to_write = html
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_to_write)
        sys.stdout.write(out_path + "\n")
    else:
        # default: print to stdout
        sys.stdout.write(html)
