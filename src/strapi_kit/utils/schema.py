"""Schema utility functions.

This module provides shared utility functions for handling Strapi schema data,
particularly for extracting info from various schema formats.
"""

from typing import Any

_DRAFT_AND_PUBLISH_KEYS = ("draftAndPublish", "draft_and_publish")


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
    nested_info_raw = schema.get("info")
    nested_info: dict[str, Any] = nested_info_raw if isinstance(nested_info_raw, dict) else {}
    if nested_info.get("displayName"):
        return nested_info

    # Extract from top-level schema properties (actual v5 format)
    return {
        "displayName": schema.get("displayName", ""),
        "singularName": schema.get("singularName"),
        "pluralName": schema.get("pluralName"),
        "description": schema.get("description"),
    }


def extract_content_type_options(item: dict[str, Any]) -> dict[str, Any] | None:
    """Return Content-Type Builder options without dropping extra keys.

    Merges top-level ``options`` with ``schema.options`` when both are present.
    Nested schema options win on key conflicts.

    Args:
        item: Raw content-type item (v4 flat or v5 nested schema)

    Returns:
        A shallow copy of the options dict, or None if no options object exists.
    """
    top = item.get("options")
    top_options = dict(top) if isinstance(top, dict) else None

    schema = item.get("schema")
    schema_options: dict[str, Any] | None = None
    if isinstance(schema, dict):
        nested = schema.get("options")
        if isinstance(nested, dict):
            schema_options = dict(nested)

    if top_options is None and schema_options is None:
        return None
    if top_options is None:
        return schema_options
    if schema_options is None:
        return top_options
    return {**top_options, **schema_options}


def extract_draft_and_publish(item: dict[str, Any]) -> bool | None:
    """Extract Draft & Publish from all known CTB wire locations.

    Looks at boolean ``draftAndPublish`` / ``draft_and_publish`` on:

    * the top-level item
    * ``options``
    * ``schema``
    * ``schema.options``

    ``True`` if any of those locations has a boolean ``True``.
    ``False`` only when a boolean ``False`` was seen and no ``True`` was seen.
    ``None`` when the flag is not mentioned. Absence is not ``False``.

    Does not infer Draft & Publish from ``publishedAt`` or other attributes.

    Args:
        item: Raw or flattened content-type item

    Returns:
        True, False, or None
    """
    seen_true = False
    seen_false = False

    def consider(source: Any) -> None:
        nonlocal seen_true, seen_false
        if not isinstance(source, dict):
            return
        for key in _DRAFT_AND_PUBLISH_KEYS:
            value = source.get(key)
            if isinstance(value, bool):
                if value:
                    seen_true = True
                else:
                    seen_false = True

    consider(item)
    consider(item.get("options"))
    schema = item.get("schema")
    consider(schema)
    if isinstance(schema, dict):
        consider(schema.get("options"))

    if seen_true:
        return True
    if seen_false:
        return False
    return None


def apply_draft_and_publish_sources(data: Any) -> Any:
    """Copy a payload and populate first-class Draft & Publish fields.

    Sets ``draftAndPublish`` from all known wire locations. When ``options`` is
    missing, copies it from nested schema options so extra keys are retained.

    Args:
        data: Raw model payload (typically a dict)

    Returns:
        Unchanged non-dict values, or a shallow-copied dict with D&P applied
    """
    if not isinstance(data, dict):
        return data
    payload = dict(data)
    payload["draftAndPublish"] = extract_draft_and_publish(payload)
    if not isinstance(payload.get("options"), dict):
        options = extract_content_type_options(payload)
        if options is not None:
            payload["options"] = options
    return payload
