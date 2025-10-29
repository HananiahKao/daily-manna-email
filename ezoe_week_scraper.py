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


DAY_LABELS = {
    1: "周一",
    2: "周二",
    3: "周三",
    4: "周四",
    5: "周五",
    6: "周六",
    7: "主日",
}


def _decode_html(resp: requests.Response) -> Optional[str]:
    if resp.status_code != 200 or "text/html" not in resp.headers.get("Content-Type", ""):
        return None
    data = resp.content or b""
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
        return _decode_html(resp)
    except requests.RequestException:
        return None


def _lesson_url(base: str, volume: int, lesson: int) -> str:
    # Book id root is fixed to 2264 in the provided link, with pattern 2264-<volume>-<lesson>.html
    # Base defaults to https://ezoe.work/books/2
    filename = f"2264-{volume}-{lesson}.html"
    return urljoin(base.rstrip("/") + "/", filename)


def _collect_until_next_day(start_node: Tag, day_texts: List[str]) -> List[Tag]:
    # Simple and robust approach: iterate forward siblings until we reach a next-day label
    collected: List[Tag] = []
    node = start_node.next_sibling
    while node is not None:
        if isinstance(node, NavigableString):
            node = node.next_sibling
            continue
        text = node.get_text(strip=True)
        if text in day_texts:
            break
        collected.append(node)
        node = node.next_sibling
    return collected


def _find_day_anchor(container: Tag, label: str) -> Optional[Tag]:
    # Find a tag whose stripped text exactly matches the day label
    for el in container.find_all(True):
        if el.get_text(strip=True) == label:
            return el
    return None


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
        raise ValueError("Day must be 0..7")

    url = _lesson_url(base, volume, lesson)
    html = _fetch(url)
    if not html:
        raise ValueError(f"Failed to fetch lesson page: {url}")

    soup = BeautifulSoup(html, "html.parser")

    # Heuristically identify the main content container: it's the middle generic block between banners
    # Fall back to body if not obvious
    content_root = soup.find("body") or soup

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

    anchor = _find_day_anchor(content_root, label)
    if not anchor:
        raise ValueError(f"Day label '{label}' not found on page: {url}")

    # Collect nodes after the day label until reaching the next label
    day_texts = list(DAY_LABELS.values())
    nodes = _collect_until_next_day(anchor, day_texts)
    # Also include the immediate subtitle (often the next element following the label in a separate container)
    # If the first collected node is extremely short and there is another sibling text, keep as-is; we return raw HTML

    # Build a minimal wrapper to keep HTML valid and portable
    wrapper = soup.new_tag("div")
    header = soup.new_tag("h3")
    header.string = label
    wrapper.append(header)
    for n in nodes:
        wrapper.append(n)

    return str(wrapper)


if __name__ == "__main__":
    import argparse, json, sys
    ap = argparse.ArgumentParser(description="Fetch a day's HTML from ezoe.work lesson page")
    ap.add_argument("selector", help="<volume>-<lesson>-<day>, day 0 returns full lesson HTML")
    ap.add_argument("--base", default="https://ezoe.work/books/2", help="Base URL for books path")
    args = ap.parse_args()
    try:
        html = get_day_html(args.selector, base=args.base)
        sys.stdout.write(html)
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)
