import pytest
from unittest.mock import patch, MagicMock
from stmn1_content_source import Stmn1ContentSource


class TestStmn1ContentSource:
    """Test Stmn1ContentSource functionality with integration and error handling tests."""

    @pytest.fixture
    def stmn1_source(self):
        """Create a Stmn1ContentSource instance."""
        return Stmn1ContentSource()

    def _fake_stmn1_page(self):
        """Create a fake stmn1 page HTML for testing."""
        return """
        <html>
            <head>
                <title>聖經之旅第1冊｜第1課｜創世記第一章</title>
            </head>
            <body>
                <h1>聖經之旅第1冊｜第1課｜創世記第一章</h1>
                <p>《周一》</p>
                <p>周一的內容段落1</p>
                <p>周一的內容段落2</p>
                <p>《周二》</p>
                <p>周二的內容段落1</p>
                <p>《周三》</p>
                <p>周三的內容段落1</p>
                <p>周三的內容段落2</p>
                <p>周三的內容段落3</p>
                <p>問題討論：</p>
                <p>1. 問題1</p>
                <p>2. 問題2</p>
            </body>
        </html>
        """

    @patch("stmn1_content_source.requests.get")
    def test_stmn1_content_fetching(self, mock_get, stmn1_source):
        """Test that Stmn1 content can be fetched successfully with mocked HTTP request."""
        # Create a mock response
        mock_response = MagicMock()
        mock_response.text = self._fake_stmn1_page()
        mock_response.encoding = 'utf-8'
        mock_response.apparent_encoding = 'utf-8'
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # Test with Monday selector
        selector = "1-1-1"
        content = stmn1_source.get_daily_content(selector)

        # Verify content structure
        assert content is not None
        assert hasattr(content, 'html_content')
        assert hasattr(content, 'plain_text_content')
        assert hasattr(content, 'title')

        # Verify content has expected elements
        assert len(content.html_content) > 50
        assert len(content.plain_text_content) > 20
        assert "周一的內容段落1" in content.html_content
        assert "周一的內容段落2" in content.html_content
        assert "周二的內容段落1" not in content.html_content  # Should stop before next day

        # Check title
        assert "聖經之旅" in content.title

    @patch("stmn1_content_source.requests.get")
    def test_stmn1_content_structure(self, mock_get, stmn1_source):
        """Test that fetched content has proper HTML structure with mocked HTTP request."""
        # Create a mock response
        mock_response = MagicMock()
        mock_response.text = self._fake_stmn1_page()
        mock_response.encoding = 'utf-8'
        mock_response.apparent_encoding = 'utf-8'
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        selector = "1-1-1"
        content = stmn1_source.get_daily_content(selector)

        # Should contain daily content wrapper
        assert '<div class="daily-content">' in content.html_content

        # Should have extracted title
        assert "聖經之旅" in content.title

    @patch("stmn1_content_source.requests.get")
    def test_stmn1_extract_title_from_meta(self, mock_get, stmn1_source):
        """Test that title extraction from page metadata works with mocked HTTP request."""
        fake_html = """
        <html>
            <head>
                <title>聖經之旅第2冊｜第5課｜出埃及記第五章</title>
            </head>
            <body>
                <h1>課程標題</h1>
                <p>《周一》</p>
                <p>內容</p>
            </body>
        </html>
        """

        # Create a mock response
        mock_response = MagicMock()
        mock_response.text = fake_html
        mock_response.encoding = 'utf-8'
        mock_response.apparent_encoding = 'utf-8'
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        selector = "2-5-1"
        content = stmn1_source.get_daily_content(selector)

        assert "聖經之旅第2冊｜第5課｜出埃及記第五章" in content.title

    @patch("stmn1_content_source.requests.get")
    def test_stmn1_extract_title_from_heading(self, mock_get, stmn1_source):
        """Test that title extraction from heading works with mocked HTTP request."""
        fake_html = """
        <html>
            <head>
                <!-- No meta title -->
            </head>
            <body>
                <h1>聖經之旅第3冊｜第10課｜利未記第十章</h1>
                <p>《周一》</p>
                <p>內容</p>
            </body>
        </html>
        """

        # Create a mock response
        mock_response = MagicMock()
        mock_response.text = fake_html
        mock_response.encoding = 'utf-8'
        mock_response.apparent_encoding = 'utf-8'
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        selector = "3-10-1"
        content = stmn1_source.get_daily_content(selector)

        assert "聖經之旅第3冊｜第10課｜利未記第十章" in content.title

    def test_stmn1_email_subject_generation(self, stmn1_source):
        """Test email subject generation for Stmn1 content."""
        # Test with Monday
        subject = stmn1_source.get_email_subject("1-1-1", "創世記第一章")
        assert "聖經之旅 | 周一 創世記第一章" in subject

        # Test with Tuesday
        subject = stmn1_source.get_email_subject("1-1-2", "創世記第二章")
        assert "聖經之旅 | 周二 創世記第二章" in subject

        # Test with Sunday (主日)
        subject = stmn1_source.get_email_subject("1-1-7", "創世記第七章")
        assert "聖經之旅 | 主日 創世記第七章" in subject

        # Test with content that already has weekday prefix
        subject = stmn1_source.get_email_subject("1-1-3", "周三 創世記第三章")
        assert "聖經之旅 | 周三 創世記第三章" in subject

        # Test with empty content title
        subject = stmn1_source.get_email_subject("1-1-4", "")
        assert "聖經之旅 | 周四" in subject

    def test_stmn1_content_url_generation(self, stmn1_source):
        """Test content URL generation for Stmn1 content."""
        # Test with various selectors
        assert stmn1_source.get_content_url("1-1-1") == "https://mana.stmn1.com/books/2264/001.html#1"
        assert stmn1_source.get_content_url("1-18-7") == "https://mana.stmn1.com/books/2264/018.html#7"
        assert stmn1_source.get_content_url("2-1-3") == "https://mana.stmn1.com/books/2264/019.html#3"
        assert stmn1_source.get_content_url("15-18-7") == "https://mana.stmn1.com/books/2264/270.html#7"

    @patch("stmn1_content_source.requests.get")
    def test_stmn1_fetch_failure(self, mock_get, stmn1_source):
        """Test that fetch failure raises appropriate error with mocked HTTP request."""
        # Create a mock response that raises an exception
        mock_get.side_effect = Exception("Network error")

        with pytest.raises(RuntimeError, match="Failed to fetch lesson content"):
            stmn1_source.get_daily_content("1-1-1")

    @patch("stmn1_content_source.requests.get")
    def test_stmn1_fetch_returns_none(self, mock_get, stmn1_source):
        """Test that fetch returning None raises appropriate error with mocked HTTP request."""
        # Create a mock response that returns None
        mock_response = MagicMock()
        mock_response.text = None
        mock_response.encoding = 'utf-8'
        mock_response.apparent_encoding = 'utf-8'
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with pytest.raises(RuntimeError, match="Failed to fetch lesson content"):
            stmn1_source.get_daily_content("1-1-1")

    @patch("stmn1_content_source.requests.get")
    def test_stmn1_missing_day_section(self, mock_get, stmn1_source):
        """Test that missing day section returns fallback content with mocked HTTP request."""
        fake_html = """
        <html>
            <head>
                <title>聖經之旅第1冊｜第1課｜創世記第一章</title>
            </head>
            <body>
                <h1>聖經之旅第1冊｜第1課｜創世記第一章</h1>
                <p>《周一》</p>
                <p>周一的內容</p>
                <p>《周二》</p>
                <p>周二的內容</p>
            </body>
        </html>
        """

        # Create a mock response
        mock_response = MagicMock()
        mock_response.text = fake_html
        mock_response.encoding = 'utf-8'
        mock_response.apparent_encoding = 'utf-8'
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # Try to get content for Wednesday (day 3) which is missing
        content = stmn1_source.get_daily_content("1-1-3")

        # Should return fallback content
        assert content.html_content is not None
        assert len(content.html_content) > 0
        assert "周一" in content.html_content
        assert "周二" in content.html_content

    def test_stmn1_lesson_url_generation(self, stmn1_source):
        """Test that lesson URL generation works correctly."""
        # Test with volume 1
        assert stmn1_source._get_lesson_url(1, 1) == "https://mana.stmn1.com/books/2264/001.html"
        assert stmn1_source._get_lesson_url(1, 18) == "https://mana.stmn1.com/books/2264/018.html"

        # Test with volume 2
        assert stmn1_source._get_lesson_url(2, 1) == "https://mana.stmn1.com/books/2264/019.html"
        assert stmn1_source._get_lesson_url(2, 18) == "https://mana.stmn1.com/books/2264/036.html"

        # Test with higher volumes
        assert stmn1_source._get_lesson_url(15, 18) == "https://mana.stmn1.com/books/2264/270.html"

    def test_stmn1_absolute_lesson_number_calculation(self, stmn1_source):
        """Test that absolute lesson number calculation works correctly."""
        # Test volume 1
        assert stmn1_source._get_absolute_lesson_number(1, 1) == 1
        assert stmn1_source._get_absolute_lesson_number(1, 18) == 18

        # Test volume 2
        assert stmn1_source._get_absolute_lesson_number(2, 1) == 19
        assert stmn1_source._get_absolute_lesson_number(2, 18) == 36

        # Test higher volumes
        assert stmn1_source._get_absolute_lesson_number(15, 18) == 270

    def test_stmn1_volume_index_url(self, stmn1_source):
        """Test that volume index URL generation works correctly."""
        assert stmn1_source._get_volume_index_url(1) == "https://mana.stmn1.com/books/2264/index01.html"
        assert stmn1_source._get_volume_index_url(2) == "https://mana.stmn1.com/books/2264/index02.html"
        assert stmn1_source._get_volume_index_url(10) == "https://mana.stmn1.com/books/2264/index10.html"
        assert stmn1_source._get_volume_index_url(15) == "https://mana.stmn1.com/books/2264/index15.html"


class TestContentSourceFactory:
    """Test that ContentSourceFactory properly handles Stmn1ContentSource."""

    def test_factory_returns_stmn1_source(self):
        """Test that the content source factory returns Stmn1ContentSource for 'stmn1' source name."""
        from content_source_factory import get_content_source
        source = get_content_source("stmn1")
        assert isinstance(source, Stmn1ContentSource)

    def test_factory_includes_stmn1_in_available_sources(self):
        """Test that 'stmn1' is included in available sources list."""
        from content_source_factory import get_content_source
        try:
            get_content_source("invalid_source")
        except ValueError as e:
            assert "stmn1" in str(e)
            assert "ezoe" in str(e)
            assert "wix" in str(e)