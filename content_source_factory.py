#!/usr/bin/env python3
"""
Factory for creating ContentSource instances based on configuration.

Allows switching between content sources via the CONTENT_SOURCE environment variable.
"""

import os
import content_source
import ezoe_content_source
import wix_content_source
import stmn1_content_source
ContentSource = content_source.ContentSource
EzoeContentSource = ezoe_content_source.EzoeContentSource
WixContentSource = wix_content_source.WixContentSource
Stmn1ContentSource = stmn1_content_source.Stmn1ContentSource

# Mapping of content source names to their classes
CONTENT_SOURCES = {
    "ezoe": EzoeContentSource,
    "wix": WixContentSource,
    "stmn1": Stmn1ContentSource
}


def get_content_source(source_name: str) -> ContentSource:
    """Returns a ContentSource instance for the given name."""
    source_name = source_name.lower().strip()
    if source_name not in CONTENT_SOURCES:
        available_sources = ", ".join(get_available_sources())
        raise ValueError(f"Unknown content source: {source_name}. Available sources: {available_sources}")
    return CONTENT_SOURCES[source_name]()


def get_active_source() -> ContentSource:
    """Returns the appropriate ContentSource instance based on the CONTENT_SOURCE environment variable."""
    source_name = os.getenv("CONTENT_SOURCE", "ezoe")
    return get_content_source(source_name)


def get_available_sources() -> list:
    """Returns a list of all available content source names."""
    return list(CONTENT_SOURCES.keys())
