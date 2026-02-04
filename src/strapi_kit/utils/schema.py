"""Schema utility functions.

This module provides shared utility functions for handling Strapi schema data,
particularly for extracting info from various schema formats.
"""

from typing import Any


def extract_info_from_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Extract info dict from schema, handling both v5 formats.

    Strapi v5 may return info in two formats:
    1. Nested: schema.info.displayName (alternative format)
    2. Flat: schema.displayName (actual v5 API format from Issue #28)

    Args:
        schema: Schema dict from API response

    Returns:
        Info dict with displayName, singularName, pluralName, description
    """
    # Check for nested info object first
    nested_info: dict[str, Any] = schema.get("info", {})
    if nested_info.get("displayName"):
        return nested_info

    # Extract from top-level schema properties (actual v5 format)
    return {
        "displayName": schema.get("displayName", ""),
        "singularName": schema.get("singularName"),
        "pluralName": schema.get("pluralName"),
        "description": schema.get("description"),
    }
