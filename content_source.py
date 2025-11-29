#!/usr/bin/env python3
"""
Abstraction layer for content sources in the daily-manna-email system.

Provides the OCP-compliant interface for fetching content from various sources
like ezoe.work or Wix sites.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List


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

    @abstractmethod
    def get_email_subject(self, selector: str, content_title: str) -> str:
        """Returns the email subject for the given selector and content title."""
        pass

    @abstractmethod
    def parse_selector(self, selector: str) -> any:
        """Parses a selector string into a structured object (tuple, dict, etc.)."""
        pass

    @abstractmethod
    def format_selector(self, parsed: any) -> str:
        """Formats a structured selector object back into a string."""
        pass

    @abstractmethod
    def advance_selector(self, selector: str) -> str:
        """Returns the next selector in the sequence."""
        pass

    @abstractmethod
    def previous_selector(self, selector: str) -> str:
        """Returns the previous selector in the sequence."""
        pass

    @abstractmethod
    def validate_selector(self, selector: str) -> bool:
        """Validates if the selector string is well-formed."""
        pass

    @abstractmethod
    def get_default_selector(self) -> str:
        """Returns a default starting selector for this source."""
        pass

    @abstractmethod
    def parse_batch_selectors(self, input_text: str) -> List[str]:
        """
        Parse batch selector input into a list of individual selectors.
        
        Handles content source-specific syntax like:
        - Range syntax (e.g., "2-1-15 to 2-1-19" for Ezoe)
        - Comma/newline separation
        - Content source-specific validation
        
        Args:
            input_text: Raw input from user (may contain ranges, commas, newlines)
            
        Returns:
            List of validated selector strings
            
        Raises:
            ValueError: If input contains invalid selectors or syntax
        """
        pass

    @abstractmethod
    def supports_range_syntax(self) -> bool:
        """
        Returns whether this content source supports range syntax (e.g., "X to Y").
        
        Returns:
            True if range syntax is supported, False otherwise
        """
        pass

    @abstractmethod
    def get_batch_ui_config(self) -> dict:
        """
        Returns UI configuration for batch editing with this content source.
        
        Returns:
            dict with keys:
                - placeholder: str - Placeholder text for batch input field
                - help_text: str - Help text explaining selector format
                - examples: List[str] - Example selectors
                - supports_range: bool - Whether range syntax is supported
                - range_example: str | None - Example of range syntax
        """
        pass
