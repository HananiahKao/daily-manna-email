#!/usr/bin/env python3
"""
Test ContentSource implementations through the ABC interface.

Tests that are dependent on the ContentSource ABC, testing both EzoeContentSource
and WixContentSource implementations polymorphically where possible.
"""

import pytest
from content_source import ContentSource
from ezoe_content_source import EzoeContentSource
from wix_content_source import WixContentSource


class TestContentSourceABC:
    """Test the ContentSource ABC contract and implementations."""

    @pytest.fixture
    def ezoe_source(self):
        """FIXME: Returns an EzoeContentSource instance."""
        return EzoeContentSource()

    @pytest.fixture
    def wix_source(self):
        """FIXME: Returns a WixContentSource instance."""
        return WixContentSource()

    @pytest.mark.parametrize("source_factory", [
        lambda: EzoeContentSource(),
        lambda: WixContentSource(),
    ], ids=["ezoe", "wix"])
    def test_content_source_implements_abc(self, source_factory):
        """Test that implementations properly implement the ContentSource ABC."""
        source = source_factory()
        assert isinstance(source, ContentSource)

        # Test all abstract methods are implemented
        required_methods = [
            'get_daily_content', 'get_source_name', 'get_selector_type',
            'get_content_url', 'get_email_subject', 'parse_selector',
            'format_selector', 'advance_selector', 'previous_selector',
            'validate_selector', 'get_default_selector', 'parse_batch_selectors',
            'supports_range_syntax', 'get_batch_ui_config'
        ]

        for method in required_methods:
            assert hasattr(source, method), f"Missing method: {method}"
            assert callable(getattr(source, method)), f"Not callable: {method}"

    @pytest.mark.parametrize("source_factory,default_selector", [
        (lambda: EzoeContentSource(), "2-1-1"),
        (lambda: WixContentSource(), "【週一】"),
    ], ids=["ezoe", "wix"])
    def test_default_selector(self, source_factory, default_selector):
        """Test get_default_selector returns expected value."""
        source = source_factory()
        assert source.get_default_selector() == default_selector

    @pytest.mark.parametrize("source_factory,expected_name", [
        (lambda: EzoeContentSource(), "ezoe"),
        (lambda: WixContentSource(), "wix"),
    ], ids=["ezoe", "wix"])
    def test_source_name(self, source_factory, expected_name):
        """Test get_source_name returns expected identifier."""
        source = source_factory()
        assert source.get_source_name() == expected_name

    @pytest.mark.parametrize("source_factory,expected_type", [
        (lambda: EzoeContentSource(), "volume-lesson-day"),
        (lambda: WixContentSource(), "chinese-weekday"),
    ], ids=["ezoe", "wix"])
    def test_selector_type(self, source_factory, expected_type):
        """Test get_selector_type returns expected type."""
        source = source_factory()
        assert source.get_selector_type() == expected_type

    def test_ezoe_selector_parsing(self, ezoe_source):
        """Test EzoeContentSource selector parsing and formatting."""
        # Valid selectors
        test_cases = [
            ("2-1-1", (2, 1, 1)),
            ("5-3-7", (5, 3, 7)),
            ("1-10-6", (1, 10, 6)),
        ]

        for selector_str, expected_parsed in test_cases:
            # Test parsing
            parsed = ezoe_source.parse_selector(selector_str)
            assert parsed == expected_parsed

            # Test formatting back
            formatted = ezoe_source.format_selector(parsed)
            assert formatted == selector_str

            # Test validation
            assert ezoe_source.validate_selector(selector_str) is True

    def test_wix_selector_parsing(self, wix_source):
        """Test WixContentSource selector parsing and formatting."""
        # Valid selectors (weekday indices: 0=Mon, 6=Sun)
        test_cases = [
            ("【週一】", 0),
            ("【主日】", 6),
            ("【週三】", 2),
            ("【週五】", 4),
        ]

        for selector_str, expected_parsed in test_cases:
            # Test parsing
            parsed = wix_source.parse_selector(selector_str)
            assert parsed == expected_parsed

            # Test formatting back
            formatted = wix_source.format_selector(parsed)
            assert formatted == selector_str

            # Test validation
            assert wix_source.validate_selector(selector_str) is True

    @pytest.mark.parametrize("source_factory", [
        lambda: EzoeContentSource(),
        lambda: WixContentSource(),
    ], ids=["ezoe", "wix"])
    def test_selector_validation_invalid(self, source_factory):
        """Test validate_selector returns False for invalid selectors."""
        source = source_factory()

        invalid_selectors = ["", "invalid", "1", "a-b-c", "【invalid】"]

        for invalid_selector in invalid_selectors:
            if invalid_selector:  # Skip empty string if handled differently
                assert source.validate_selector(invalid_selector) is False

    def test_ezoe_selector_advancement(self, ezoe_source):
        """Test advance_selector and previous_selector for EzoeContentSource."""
        # Normal advancement within lesson
        assert ezoe_source.advance_selector("2-1-1") == "2-1-2"
        assert ezoe_source.advance_selector("2-1-6") == "2-1-7"

        # Advancement to next lesson
        assert ezoe_source.advance_selector("2-1-7") == "2-2-1"
        assert ezoe_source.advance_selector("2-3-7") == "2-4-1"

        # Previous selector
        assert ezoe_source.previous_selector("2-1-2") == "2-1-1"
        assert ezoe_source.previous_selector("2-1-1") == "2-1-7"
        assert ezoe_source.previous_selector("2-2-1") == "2-1-7"

    def test_wix_selector_advancement(self, wix_source):
        """Test advance_selector and previous_selector for WixContentSource."""
        # Normal advancement
        assert wix_source.advance_selector("【週一】") == "【週二】"
        assert wix_source.advance_selector("【週六】") == "【主日】"

        # Wrap around
        assert wix_source.advance_selector("【主日】") == "【週一】"

        # Previous selector
        assert wix_source.previous_selector("【週二】") == "【週一】"
        assert wix_source.previous_selector("【週一】") == "【主日】"
        assert wix_source.previous_selector("【主日】") == "【週六】"

    @pytest.mark.parametrize("source_factory", [
        lambda: EzoeContentSource(),
        lambda: WixContentSource(),
    ], ids=["ezoe", "wix"])
    def test_supports_range_syntax(self, source_factory):
        """Test supports_range_syntax returns True for both implementations."""
        source = source_factory()
        assert source.supports_range_syntax() is True

    @pytest.mark.parametrize("source_factory,expected_config", [
        (lambda: EzoeContentSource(),
         {"supports_range": True,
          "range_example": "2-1-15 to 2-1-19",
          "placeholder": "e.g., 2-1-15 to 2-1-19 or 2-1-15, 2-1-16, 2-1-17"}),
        (lambda: WixContentSource(),
         {"supports_range": True,
          "range_example": "【週一】 to 【週五】",
          "placeholder": "e.g., 【週一】 to 【週五】 or 【週一】, 【週二】, 【週三】"}),
    ], ids=["ezoe", "wix"])
    def test_batch_ui_config(self, source_factory, expected_config):
        """Test get_batch_ui_config returns correct configuration."""
        source = source_factory()
        config = source.get_batch_ui_config()

        for key, expected_value in expected_config.items():
            assert key in config, f"Missing key: {key}"
            assert config[key] == expected_value, f"Value mismatch for {key}"

    def test_ezoe_parse_batch_selectors_comma_separated(self, ezoe_source):
        """Test parse_batch_selectors with comma-separated input for Ezoe."""
        input_text = "2-1-1, 2-1-2 ,2-1-3"
        result = ezoe_source.parse_batch_selectors(input_text)
        expected = ["2-1-1", "2-1-2", "2-1-3"]
        assert result == expected

    def test_wix_parse_batch_selectors_comma_separated(self, wix_source):
        """Test parse_batch_selectors with comma-separated input for Wix."""
        input_text = "【週一】, 【週二】 ,【週三】"
        result = wix_source.parse_batch_selectors(input_text)
        expected = ["【週一】", "【週二】", "【週三】"]
        assert result == expected

    def test_ezoe_parse_batch_selectors_range(self, ezoe_source):
        """Test parse_batch_selectors with range syntax for Ezoe."""
        input_text = "2-1-1 to 2-1-3"
        result = ezoe_source.parse_batch_selectors(input_text)
        expected = ["2-1-1", "2-1-2", "2-1-3"]
        assert result == expected

        # Test invalid range (different volume/lesson)
        with pytest.raises(ValueError, match="Range must be within same volume and lesson"):
            ezoe_source.parse_batch_selectors("2-1-1 to 2-2-1")

    def test_wix_parse_batch_selectors_range(self, wix_source):
        """Test parse_batch_selectors with range syntax for Wix."""
        input_text = "【週一】 to 【週三】"
        result = wix_source.parse_batch_selectors(input_text)
        expected = ["【週一】", "【週二】", "【週三】"]
        assert result == expected

        # Test wrap-around range (Saturday to Tuesday)
        input_text = "【週六】 to 【週二】"
        result = wix_source.parse_batch_selectors(input_text)
        expected = ["【週六】", "【主日】", "【週一】", "【週二】"]
        assert result == expected

    @pytest.mark.parametrize("source_factory,input_text", [
        (lambda: EzoeContentSource(), ""),
        (lambda: EzoeContentSource(), "   "),
        (lambda: WixContentSource(), ""),
        (lambda: WixContentSource(), "   "),
        (lambda: WixContentSource(), "\n\n"),
    ], ids=["ezoe_empty", "ezoe_spaces", "wix_empty", "wix_spaces", "wix_newlines"])
    def test_parse_batch_selectors_empty_input(self, source_factory, input_text):
        """Test parse_batch_selectors handles empty/whitespace input."""
        source = source_factory()
        result = source.parse_batch_selectors(input_text)
        assert result == []

    @pytest.mark.parametrize("source_factory,invalid_input,expected_error", [
        (lambda: EzoeContentSource(), "2-1-1, invalid, 2-1-3", "Invalid Ezoe selector"),
        (lambda: WixContentSource(), "【週一】, invalid, 【週三】", "Invalid Wix selector"),
    ], ids=["ezoe_invalid", "wix_invalid"])
    def test_parse_batch_selectors_invalid_selectors(self, source_factory, invalid_input, expected_error):
        """Test parse_batch_selectors raises ValueError for invalid selectors."""
        source = source_factory()
        with pytest.raises(ValueError, match=expected_error):
            source.parse_batch_selectors(invalid_input)
