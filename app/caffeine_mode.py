"""Caffeine mode to prevent server from sleeping by periodic self-pinging."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from pathlib import Path
import requests
import time
import os

from app.config import get_config


# Caffeine mode constants
CAFFEINE_JOB_NAME = "caffeine_mode"
PING_INTERVAL = 600  # 10 minutes in seconds
CAFFEINE_LOG_FILE = "state/caffeine_mode.log"


def _setup_logging() -> logging.Logger:
    """Set up caffeine mode specific logging."""
    logger = logging.getLogger("caffeine_mode")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Create state directory if it doesn't exist
    state_dir = Path("state")
    state_dir.mkdir(exist_ok=True)

    # File handler
    file_handler = logging.FileHandler(CAFFEINE_LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)

    return logger


logger = _setup_logging()


async def caffeine_ping() -> None:
    """Perform a self-ping to keep the server awake."""
    try:
        start_time = time.time()
        logger.info("Starting caffeine ping")

        # Get domain and port from environment variables
        domain = os.getenv("CAFFEINE_DOMAIN", "localhost")
        port = os.getenv("PORT", "8000")
        
        # Build URL with proper port handling
        if domain == "localhost" or domain == "127.0.0.1":
            url = f"http://{domain}:{port}/api/caffeine"
        else:
            # For external domains, use default HTTP/HTTPS based on domain
            if domain.startswith("http://") or domain.startswith("https://"):
                # If domain already includes protocol
                base_url = domain.rstrip("/")
                url = f"{base_url}/api/caffeine"
            else:
                # Default to HTTPS for external domains
                url = f"https://{domain}/api/caffeine"

        logger.info(f"Pinging URL: {url}")

        # Ping the caffeine endpoint
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        # Get response data
        data = response.json()
        duration = time.time() - start_time

        logger.info(f"Caffeine ping successful: {data.get('message')} (took {duration:.2f} seconds)")

    except Exception as e:
        logger.error(f"Caffeine ping failed: {str(e)}")


async def start_caffeine_mode() -> None:
    """Start the caffeine mode background task."""
    config = get_config()
    if not config.caffeine_mode:
        logger.info("Caffeine mode is disabled via CAFFEINE_MODE environment variable")
        return

    logger.info(f"Starting caffeine mode - pinging every {config.caffeine_interval} seconds")

    while True:
        await caffeine_ping()
        await asyncio.sleep(config.caffeine_interval)
