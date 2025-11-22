#!/usr/bin/env python3
"""
Abstraction layer for content sources in the daily-manna-email system.

Provides the OCP-compliant interface for fetching content from various sources
like ezoe.work or Wix sites.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ContentBlock:
    """Standardized container for content returned by any ContentSource."""
    html_content: str
    plain_text_content: str
    title: str


class ContentSource(ABC):
    """Abstract base class defining the contract for all content providers."""

    @abstractmethod
    def get_daily_content(self, selector: str) -> ContentBlock:
        """Fetches and processes the content for a given selector."""
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """Returns a unique identifier for the source (e.g., 'ezoe', 'wix')."""
        pass

    @abstractmethod
    def get_selector_type(self) -> str:
        """Returns the type of selector this source uses (e.g., 'volume-lesson-day', 'chinese-weekday')."""
        pass

    @abstractmethod
    def get_content_url(self, selector: str) -> str:
        """Returns the canonical URL for the given selector, with appropriate anchoring when available."""
        pass
