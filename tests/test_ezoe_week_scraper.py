import re
from unittest.mock import patch

import bs4
import pytest

import ezoe_week_scraper as ez


def test_lesson_url_building():
    assert ez._lesson_url("https://ezoe.work/books/2", 2, 1).endswith("2264-2-1.html")
    assert ez._lesson_url("https://ezoe.work/books/2/", 3, 5).endswith("2264-3-5.html")


def test_invalid_selector_format():
    with pytest.raises(ValueError):
        ez.get_day_html("bad-format")
    with pytest.raises(ValueError):
        ez.get_day_html("1-2-9")


def _fake_page(day_blocks):
    # Build a minimal HTML where each day label is a block-level element
    body = "".join(f"<h3>{label}</h3><p>Content for {label}</p>" for label in ez.DAY_LABELS.values())
    return f"<html><body>{body}</body></html>"


@patch("ezoe_week_scraper._fetch")
def test_get_specific_day_html(mock_fetch):
    mock_fetch.return_value = _fake_page(ez.DAY_LABELS)
    html = ez.get_day_html("2-1-3")  # 周三
    assert "周三" in html
    assert "Content for 周三" in html
    # Ensure it stops before next day's content
    assert "Content for 周四" not in html


@patch("ezoe_week_scraper._fetch")
def test_get_full_lesson_html_day0(mock_fetch):
    mock_fetch.return_value = _fake_page(ez.DAY_LABELS)
    html = ez.get_day_html("2-1-0")
    # Should include multiple day labels since returning full body
    for label in ez.DAY_LABELS.values():
        assert label in html


@patch("ezoe_week_scraper._fetch")
def test_missing_label_raises(mock_fetch):
    # Page without the requested label
    mock_fetch.return_value = "<html><body><h3>周一</h3></body></html>"
    with pytest.raises(ValueError):
        ez.get_day_html("2-1-7")


@patch("ezoe_week_scraper._fetch")
def test_fetch_failure_raises(mock_fetch):
    mock_fetch.return_value = None
    with pytest.raises(ValueError):
        ez.get_day_html("2-1-1")

