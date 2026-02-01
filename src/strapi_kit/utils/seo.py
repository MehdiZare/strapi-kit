"""SEO configuration detection utilities.

This module provides functions for detecting SEO configurations
in Strapi content type schemas.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

from ..models.schema import ContentTypeSchema


@dataclass
class SEOConfiguration:
    """SEO configuration detected from a content type schema.

    Attributes:
        has_seo: Whether SEO configuration was detected
        seo_type: Type of SEO setup - "component" (shared SEO component),
                  "flat" (individual fields), or None if not detected
        seo_field_name: Name of the SEO field/component (e.g., "seo", "meta")
        seo_component_uid: Component UID if seo_type is "component"
        fields: Mapping of SEO purpose to field path
                (e.g., {"title": "seo.metaTitle", "description": "seo.metaDescription"})
    """

    has_seo: bool = False
    seo_type: Literal["component", "flat"] | None = None
    seo_field_name: str | None = None
    seo_component_uid: str | None = None
    fields: dict[str, str] = field(default_factory=dict)


# Common SEO field name patterns (case-insensitive)
_SEO_COMPONENT_NAMES = {"seo", "meta", "metadata", "metatags", "seometa"}

# Common SEO field patterns for component detection
_SEO_COMPONENT_UIDS = {
    "shared.seo",
    "seo.seo",
    "shared.meta",
    "shared.metadata",
}

# Flat SEO field patterns (field_name -> purpose)
_FLAT_SEO_FIELD_PATTERNS: dict[str, str] = {
    "metatitle": "title",
    "meta_title": "title",
    "seotitle": "title",
    "seo_title": "title",
    "ogtitle": "og_title",
    "og_title": "og_title",
    "metadescription": "description",
    "meta_description": "description",
    "seodescription": "description",
    "seo_description": "description",
    "ogdescription": "og_description",
    "og_description": "og_description",
    "metakeywords": "keywords",
    "meta_keywords": "keywords",
    "seokeywords": "keywords",
    "seo_keywords": "keywords",
    "metaimage": "image",
    "meta_image": "image",
    "seoimage": "image",
    "seo_image": "image",
    "ogimage": "og_image",
    "og_image": "og_image",
    "canonicalurl": "canonical_url",
    "canonical_url": "canonical_url",
    "canonical": "canonical_url",
    "noindex": "no_index",
    "no_index": "no_index",
    "nofollow": "no_follow",
    "no_follow": "no_follow",
    "robots": "robots",
}


def detect_seo_configuration(
    schema: ContentTypeSchema | dict[str, Any],
) -> SEOConfiguration:
    """Detect SEO configuration in a content type schema.

    Analyzes the schema to detect:
    1. SEO components (shared.seo, seo.seo, etc.)
    2. Flat SEO fields (metaTitle, meta_description, etc.)

    Args:
        schema: Content type schema (ContentTypeSchema or raw dict)

    Returns:
        SEOConfiguration with detection results

    Examples:
        >>> # Schema with SEO component
        >>> schema = ContentTypeSchema(
        ...     uid="api::article.article",
        ...     display_name="Article",
        ...     fields={
        ...         "seo": FieldSchema(type=FieldType.COMPONENT),
        ...     }
        ... )
        >>> config = detect_seo_configuration(schema)
        >>> config.has_seo
        True
        >>> config.seo_type
        'component'

        >>> # Schema with flat SEO fields
        >>> schema_dict = {
        ...     "uid": "api::page.page",
        ...     "attributes": {
        ...         "metaTitle": {"type": "string"},
        ...         "metaDescription": {"type": "text"},
        ...     }
        ... }
        >>> config = detect_seo_configuration(schema_dict)
        >>> config.has_seo
        True
        >>> config.seo_type
        'flat'
    """
    config = SEOConfiguration()

    # Extract attributes from schema
    if isinstance(schema, ContentTypeSchema):
        attributes = {name: _field_to_dict(field) for name, field in schema.fields.items()}
    elif isinstance(schema, dict):
        # Handle both {"fields": ...} and {"attributes": ...} formats
        attributes = schema.get("attributes") or schema.get("fields") or {}
    else:
        return config

    # First, try to detect SEO component
    component_result = _detect_seo_component(attributes)
    if component_result:
        config.has_seo = True
        config.seo_type = "component"
        config.seo_field_name = component_result["field_name"]
        config.seo_component_uid = component_result.get("component_uid")
        config.fields = component_result.get("fields", {})
        return config

    # If no component, look for flat SEO fields
    flat_result = _detect_flat_seo_fields(attributes)
    if flat_result:
        config.has_seo = True
        config.seo_type = "flat"
        config.fields = flat_result
        return config

    return config


def _field_to_dict(field_schema: Any) -> dict[str, Any]:
    """Convert a FieldSchema to dict for processing.

    Args:
        field_schema: FieldSchema instance

    Returns:
        Dictionary representation
    """
    if hasattr(field_schema, "type"):
        result: dict[str, Any] = {"type": field_schema.type.value}
        if hasattr(field_schema, "target") and field_schema.target:
            result["component"] = field_schema.target
        return result
    return {}


def _detect_seo_component(attributes: dict[str, Any]) -> dict[str, Any] | None:
    """Detect SEO component in attributes.

    Args:
        attributes: Field attributes dictionary

    Returns:
        Detection result or None if not found
    """
    for field_name, field_config in attributes.items():
        # Check if field type is component
        field_type = _get_field_type(field_config)
        if field_type != "component":
            continue

        # Check if field name suggests SEO
        field_name_lower = field_name.lower()
        is_seo_name = field_name_lower in _SEO_COMPONENT_NAMES

        # Check if component UID suggests SEO
        component_uid = _get_component_uid(field_config)
        is_seo_component = False
        if component_uid:
            component_uid_lower = component_uid.lower()
            is_seo_component = (
                any(seo_uid in component_uid_lower for seo_uid in _SEO_COMPONENT_UIDS)
                or "seo" in component_uid_lower
            )

        if is_seo_name or is_seo_component:
            # Build field mappings based on common SEO component structure
            fields = _build_component_field_mappings(field_name)
            return {
                "field_name": field_name,
                "component_uid": component_uid,
                "fields": fields,
            }

    return None


def _detect_flat_seo_fields(attributes: dict[str, Any]) -> dict[str, str] | None:
    """Detect flat SEO fields in attributes.

    Args:
        attributes: Field attributes dictionary

    Returns:
        Field mappings or None if not found
    """
    fields: dict[str, str] = {}

    for field_name, _field_config in attributes.items():
        field_name_lower = field_name.lower().replace("-", "_")

        # Check if field name matches known SEO patterns
        if field_name_lower in _FLAT_SEO_FIELD_PATTERNS:
            purpose = _FLAT_SEO_FIELD_PATTERNS[field_name_lower]
            fields[purpose] = field_name

    return fields if fields else None


def _get_field_type(field_config: Any) -> str | None:
    """Extract field type from field configuration.

    Args:
        field_config: Field configuration (dict or object)

    Returns:
        Field type string or None
    """
    if isinstance(field_config, dict):
        return field_config.get("type")
    if hasattr(field_config, "type"):
        field_type = field_config.type
        return field_type.value if hasattr(field_type, "value") else str(field_type)
    return None


def _get_component_uid(field_config: Any) -> str | None:
    """Extract component UID from field configuration.

    Args:
        field_config: Field configuration (dict or object)

    Returns:
        Component UID string or None
    """
    if isinstance(field_config, dict):
        component = field_config.get("component")
        return str(component) if component else None
    if hasattr(field_config, "target"):
        target = field_config.target
        return str(target) if target else None
    return None


def _build_component_field_mappings(field_name: str) -> dict[str, str]:
    """Build standard field mappings for an SEO component.

    Args:
        field_name: Name of the SEO component field

    Returns:
        Field mappings with component prefix
    """
    return {
        "title": f"{field_name}.metaTitle",
        "description": f"{field_name}.metaDescription",
        "keywords": f"{field_name}.keywords",
        "image": f"{field_name}.metaImage",
        "canonical_url": f"{field_name}.canonicalURL",
        "og_title": f"{field_name}.ogTitle",
        "og_description": f"{field_name}.ogDescription",
        "og_image": f"{field_name}.ogImage",
        "twitter_title": f"{field_name}.twitterTitle",
        "twitter_description": f"{field_name}.twitterDescription",
        "twitter_image": f"{field_name}.twitterImage",
        "robots": f"{field_name}.robots",
        "structured_data": f"{field_name}.structuredData",
    }
