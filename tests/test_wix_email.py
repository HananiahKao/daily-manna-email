import pytest
import os
from unittest.mock import patch, MagicMock
from wix_content_source import WixContentSource


class TestWixEmailContent:
    """Test Wix content source email functionality."""

    @pytest.fixture
    def wix_source(self):
        """Create a Wix content source instance."""
        return WixContentSource()

    def test_wix_content_fetching(self, wix_source):
        """Test that Wix content can be fetched successfully."""
        # Test with Monday selector (should work if site is up)
        selector = "【週一】"

        # This test will make a real HTTP request
        content = wix_source.get_daily_content(selector)

        # Verify content structure
        assert content is not None
        assert hasattr(content, 'html_content')
        assert hasattr(content, 'plain_text_content')
        assert hasattr(content, 'title')

        # Verify content has expected elements
        assert len(content.html_content) > 100  # Should have substantial content
        assert len(content.plain_text_content) > 50  # Should have text content
        # Title should be meaningful content title, not just weekday
        assert content.title != selector.strip("【】")  # Should not be just the weekday
        assert len(content.title) > 1   # Should have meaningful content

        # Check for key content markers
        assert '晨興餧養' in content.html_content
        assert '信息選讀' in content.html_content

    def test_wix_content_structure(self, wix_source):
        """Test that fetched content has proper HTML structure."""
        selector = "【週一】"
        content = wix_source.get_daily_content(selector)

        # Should start with weekday header
        assert content.html_content.startswith('<h3>週一</h3>')

        # Should contain the content in a div
        assert '<div>' in content.html_content

        # Should have proper title (extracted from content, not just weekday)
        # The title should be a meaningful content title like "晨興餧養" or similar
        assert content.title != '週一'  # Should not be just the weekday
        assert len(content.title) > 1   # Should have meaningful content
        assert any(keyword in content.title for keyword in ["晨興", "信息", "餧養", "選讀", "禱告"]) or content.title in ['週一', '週二', '週三', '週四', '週五', '週六', '主日']

    def test_wix_invalid_selector(self, wix_source):
        """Test that invalid selectors raise appropriate errors."""
        with pytest.raises(ValueError, match="Weekday selector .* not found"):
            wix_source.get_daily_content("【無效】")

    def test_wix_email_subject_generation(self, wix_source):
        """Test email subject generation for Wix content."""
        selector = "【週一】"
        content = wix_source.get_daily_content(selector)

        subject = wix_source.get_email_subject(selector, content.title)

        # Should follow expected format: uses weekday from selector, not content title
        weekday = selector.strip("【】")  # e.g., "週一"
        assert subject == f"晨興聖言 | {weekday}"
        assert weekday in subject

    @pytest.mark.skipif(
        not all(os.getenv(key) for key in ['EMAIL_TO', 'EMAIL_FROM', 'SMTP_HOST']),
        reason="Email environment variables not configured"
    )
    def test_wix_email_sending_integration(self, wix_source):
        """Integration test for sending Wix content via email.

        This test is skipped if email environment variables are not set.
        When run, it will actually send an email.
        """
        import sjzl_daily_email as sjzl

        selector = "【週一】"
        content = wix_source.get_daily_content(selector)

        subject = f"[TEST] 晨興聖言 - {content.title}"

        # This will actually send an email if environment is configured
        recipients = sjzl.send_email(subject, content.plain_text_content, html_body=content.html_content)
        assert len(recipients) > 0  # Should have sent to at least one recipient

        # If we get here without exception, email was sent successfully
        assert True

    def test_wix_content_contains_expected_sections(self, wix_source):
        """Test that Wix content contains expected Bible study sections."""
        selector = "【週一】"
        content = wix_source.get_daily_content(selector)

        # Content should contain typical morning revival elements
        html_content = content.html_content.lower()

        # Should contain Bible references or study content
        # At minimum, should have substantial Chinese text content
        assert len([c for c in content.plain_text_content if '\u4e00' <= c <= '\u9fff']) > 100

        # Should have structured content (not just raw HTML)
        assert '晨興' in content.plain_text_content or '晨興' in content.html_content
