#!/usr/bin/env python3
"""
Factory for creating ContentSource instances based on configuration.

Allows switching between content sources via the CONTENT_SOURCE environment variable.
"""

import os
import content_source
import ezoe_content_source
import wix_content_source
ContentSource = content_source.ContentSource
EzoeContentSource = ezoe_content_source.EzoeContentSource
WixContentSource = wix_content_source.WixContentSource


def get_content_source(source_name: str) -> ContentSource:
    """Returns a ContentSource instance for the given name."""
    source_name = source_name.lower().strip()
    if source_name == "ezoe":
        return EzoeContentSource()
    elif source_name == "wix":
        return WixContentSource()
    else:
        available_sources = ["ezoe", "wix"]
        raise ValueError(f"Unknown content source: {source_name}. Available sources: {', '.join(available_sources)}")


def get_active_source() -> ContentSource:
    """Returns the appropriate ContentSource instance based on the CONTENT_SOURCE environment variable."""
    source_name = os.getenv("CONTENT_SOURCE", "ezoe")
    return get_content_source(source_name)
