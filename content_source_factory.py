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


def get_all_sources() -> list:
    """Returns all content source names (available + disabled) - for admin use only."""
    return list(CONTENT_SOURCES.keys())


def get_available_sources() -> list:
    """Returns a list of all available content source names (excluding disabled sources)."""
    disabled_raw = os.getenv("DISABLED_CONTENT_SOURCES", "").strip()
    disabled = {s.strip().lower() for s in disabled_raw.split(",") if s.strip()}
    return [s for s in CONTENT_SOURCES.keys() if s.lower() not in disabled]


def get_disabled_sources() -> list:
    """Returns list of disabled content source names."""
    disabled_raw = os.getenv("DISABLED_CONTENT_SOURCES", "").strip()
    disabled = {s.strip().lower() for s in disabled_raw.split(",") if s.strip()}
    return [s for s in CONTENT_SOURCES.keys() if s.lower() in disabled]


def get_source_display_names(language: str = "zh", include_disabled: bool = False) -> dict:
    """Returns {source_id: display_name} for sources.

    Args:
        language: "zh" for Chinese, "en" for English
        include_disabled: If True, include disabled sources. If False, only available sources.

    If multiple sources have the same display name, appends source ID in parentheses
    to disambiguate (e.g., "聖經之旅 (stmn1)" vs "聖經之旅 (ezoe)").
    """
    sources = get_all_sources() if include_disabled else get_available_sources()
    raw_names = {
        source_id: CONTENT_SOURCES[source_id].get_display_name(language)
        for source_id in sources
    }

    # Check for duplicate display names
    name_counts = {}
    for source_id, display_name in raw_names.items():
        name_counts[display_name] = name_counts.get(display_name, 0) + 1

    # Append source ID to duplicates for disambiguation
    result = {}
    for source_id, display_name in raw_names.items():
        if name_counts[display_name] > 1:
            result[source_id] = f"{display_name} ({source_id})"
        else:
            result[source_id] = display_name

    return result
