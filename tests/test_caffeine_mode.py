"""Tests for caffeine mode functionality."""

from unittest.mock import patch, MagicMock
import pytest
from app.caffeine_mode import start_caffeine_mode, caffeine_ping
from app.config import AppConfig


# Use pyfakefs to handle state directory creation without modifying the real file system
@pytest.fixture(autouse=True)
def fake_fs(fs):
    fs.create_dir("state")


@pytest.mark.asyncio
async def test_caffeine_ping_success():
    """Test that caffeine ping succeeds when endpoint is available."""
    with patch('app.caffeine_mode.requests.get') as mock_get:
        # Configure mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "awake", "message": "Server is awake"}
        mock_get.return_value = mock_response

        # Run the ping
        await caffeine_ping()

        # Verify the request was made with the correct URL (default port 8000)
        mock_get.assert_called_once_with('http://localhost:8000/api/caffeine', timeout=10)


@pytest.mark.asyncio
async def test_caffeine_ping_custom_port():
    """Test that caffeine ping uses custom port from environment variable."""
    with patch('app.caffeine_mode.requests.get') as mock_get, \
         patch('app.caffeine_mode.os.getenv') as mock_getenv:
        
        def get_env_var(name, default=None):
            if name == "PORT":
                return "8080"
            return default
        
        mock_getenv.side_effect = get_env_var
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "awake", "message": "Server is awake"}
        mock_get.return_value = mock_response

        await caffeine_ping()

        mock_get.assert_called_once_with('http://localhost:8080/api/caffeine', timeout=10)


@pytest.mark.asyncio
async def test_caffeine_ping_custom_domain():
    """Test that caffeine ping uses custom domain from environment variable."""
    with patch('app.caffeine_mode.requests.get') as mock_get, \
         patch('app.caffeine_mode.os.getenv') as mock_getenv:
        
        def get_env_var(name, default=None):
            if name == "CAFFEINE_DOMAIN":
                return "example.com"
            return default
        
        mock_getenv.side_effect = get_env_var
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "awake", "message": "Server is awake"}
        mock_get.return_value = mock_response

        await caffeine_ping()

        mock_get.assert_called_once_with('https://example.com/api/caffeine', timeout=10)


@pytest.mark.asyncio
async def test_caffeine_ping_custom_domain_with_http():
    """Test that caffeine ping preserves HTTP protocol when specified."""
    with patch('app.caffeine_mode.requests.get') as mock_get, \
         patch('app.caffeine_mode.os.getenv') as mock_getenv:
        
        def get_env_var(name, default=None):
            if name == "CAFFEINE_DOMAIN":
                return "http://example.com"
            return default
        
        mock_getenv.side_effect = get_env_var
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "awake", "message": "Server is awake"}
        mock_get.return_value = mock_response

        await caffeine_ping()

        mock_get.assert_called_once_with('http://example.com/api/caffeine', timeout=10)


@pytest.mark.asyncio
async def test_caffeine_ping_custom_domain_with_https():
    """Test that caffeine ping preserves HTTPS protocol when specified."""
    with patch('app.caffeine_mode.requests.get') as mock_get, \
         patch('app.caffeine_mode.os.getenv') as mock_getenv:
        
        def get_env_var(name, default=None):
            if name == "CAFFEINE_DOMAIN":
                return "https://example.com"
            return default
        
        mock_getenv.side_effect = get_env_var
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "awake", "message": "Server is awake"}
        mock_get.return_value = mock_response

        await caffeine_ping()

        mock_get.assert_called_once_with('https://example.com/api/caffeine', timeout=10)


@pytest.mark.asyncio
async def test_caffeine_ping_failure():
    """Test that caffeine ping handles connection failures."""
    with patch('app.caffeine_mode.requests.get') as mock_get, \
         patch('app.caffeine_mode.logger') as mock_logger:
        
        mock_get.side_effect = Exception("Connection refused")

        await caffeine_ping()

        assert any("Caffeine ping failed" in call.args[0] for call in mock_logger.error.mock_calls)


@pytest.mark.asyncio
async def test_start_caffeine_mode_disabled():
    """Test that caffeine mode doesn't start when disabled in config."""
    mock_config = MagicMock(spec=AppConfig)
    mock_config.caffeine_mode = False

    with patch('app.caffeine_mode.get_config') as mock_get_config, \
         patch('app.caffeine_mode.caffeine_ping') as mock_ping:
        
        mock_get_config.return_value = mock_config
        
        # We need to cancel the task since it runs indefinitely
        import asyncio
        task = asyncio.create_task(start_caffeine_mode())
        
        await asyncio.sleep(0.1)  # Let the task start
        task.cancel()
        
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        mock_ping.assert_not_called()


@pytest.mark.asyncio
async def test_start_caffeine_mode_enabled():
    """Test that caffeine mode starts and calls ping when enabled."""
    mock_config = MagicMock(spec=AppConfig)
    mock_config.caffeine_mode = True

    with patch('app.caffeine_mode.get_config') as mock_get_config, \
         patch('app.caffeine_mode.caffeine_ping') as mock_ping:
        
        mock_get_config.return_value = mock_config
        
        # Make ping raise an exception after first call to stop the infinite loop
        mock_ping.side_effect = Exception("Test stop")

        import asyncio
        with pytest.raises(Exception, match="Test stop"):
            await start_caffeine_mode()
        
        mock_ping.assert_called_once()