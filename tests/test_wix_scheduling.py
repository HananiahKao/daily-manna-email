import datetime as dt
import pytest
import schedule_manager as sm
from wix_content_source import WixContentSource

def test_wix_advance_selector():
    source = WixContentSource()
    assert source.advance_selector("【週一】") == "【週二】"
    assert source.advance_selector("【週六】") == "【主日】"
    assert source.advance_selector("【主日】") == "【週一】"

def test_wix_ensure_date_range():
    source = WixContentSource()
    schedule = sm.Schedule()
    start = dt.date(2025, 1, 13)  # Monday
    end = start + dt.timedelta(days=6)

    changed = sm.ensure_date_range(schedule, source, start, end, seed_selector="【週一】")

    assert changed is True
    assert len(schedule.entries) == 7
    selectors = [entry.selector for entry in schedule.entries]
    assert selectors[0] == "【週一】"
    assert selectors[1] == "【週二】"
    assert selectors[-1] == "【主日】"

def test_wix_parse_format_selector():
    source = WixContentSource()
    parsed = source.parse_selector("【週三】")
    assert parsed == 2  # 0-indexed, so Wed is 2
    formatted = source.format_selector(2)
    assert formatted == "【週三】"

def test_wix_validate_selector():
    source = WixContentSource()
    assert source.validate_selector("【週一】") is True
    assert source.validate_selector("【Invalid】") is False
