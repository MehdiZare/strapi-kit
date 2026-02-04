"""In-memory schema cache implementation."""

import logging
from typing import TYPE_CHECKING, Any

from ..exceptions import StrapiError
from ..models.schema import ContentTypeSchema, FieldSchema, FieldType, RelationType

if TYPE_CHECKING:
    from ..client.sync_client import SyncClient

logger = logging.getLogger(__name__)


class InMemorySchemaCache:
    """In-memory cache for content type schemas.

    Temporary cache for export/import operations only.
    NOT persistent across process restarts.

    This cache stores content type schemas to enable proper relation
    resolution during import. Schemas are fetched lazily on first access
    and cached for subsequent lookups.

    Example:
        >>> cache = InMemorySchemaCache(client)
        >>> schema = cache.get_schema("api::article.article")
        >>> target = schema.get_field_target("author")  # Returns "api::author.author"
    """

    def __init__(self, client: "SyncClient") -> None:
        """Initialize the schema cache.

        Args:
            client: Strapi client for fetching schemas
        """
        self.client = client
        self._cache: dict[str, ContentTypeSchema] = {}
        self._fetch_count = 0

    def get_schema(self, content_type: str) -> ContentTypeSchema:
        """Get schema (cached or fetch from API).

        Lazy loading: only fetches on first access.

        Args:
            content_type: Content type UID (e.g., "api::article.article")

        Returns:
            Content type schema

        Raises:
            StrapiError: If schema fetch fails
        """
        # Check cache first (O(1) lookup)
        if content_type in self._cache:
            logger.debug(f"Schema cache hit: {content_type}")
            return self._cache[content_type]

        # Cache miss - fetch from API
        logger.debug(f"Schema cache miss: {content_type}")
        schema = self._fetch_schema(content_type)
        self._cache[content_type] = schema
        self._fetch_count += 1
        return schema

    def cache_schema(self, content_type: str, schema: ContentTypeSchema) -> None:
        """Manually cache a schema.

        Args:
            content_type: Content type UID
            schema: Schema to cache
        """
        self._cache[content_type] = schema
        logger.debug(f"Manually cached schema: {content_type}")

    def has_schema(self, content_type: str) -> bool:
        """Check if schema is cached.

        Args:
            content_type: Content type UID

        Returns:
            True if schema is cached, False otherwise
        """
        return content_type in self._cache

    def clear_cache(self) -> None:
        """Clear all cached schemas."""
        self._cache.clear()
        self._fetch_count = 0
        logger.debug("Schema cache cleared")

    def _fetch_schema(self, content_type: str) -> ContentTypeSchema:
        """Fetch schema from Strapi API.

        Endpoint: GET /api/content-type-builder/content-types/{uid}

        Args:
            content_type: Content type UID

        Returns:
            Parsed content type schema

        Raises:
            StrapiError: If fetch fails
        """
        endpoint = f"content-type-builder/content-types/{content_type}"

        try:
            response = self.client.get(endpoint)
        except Exception as e:
            raise StrapiError(
                f"Failed to fetch schema for {content_type}",
                details={"content_type": content_type, "error": str(e)},
            ) from e

        schema_data = response.get("data")
        if not schema_data:
            raise StrapiError(
                f"Invalid schema response for {content_type}",
                details={"response": response},
            )

        return self._parse_schema_response(content_type, schema_data)

    def _extract_info_from_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
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

    def _parse_schema_response(self, uid: str, schema_data: dict[str, Any]) -> ContentTypeSchema:
        """Parse Strapi schema response.

        Args:
            uid: Content type UID
            schema_data: Schema data from API response

        Returns:
            Parsed content type schema
        """
        # Handle v5 nested schema format (Issue #28)
        if "schema" in schema_data and isinstance(schema_data["schema"], dict):
            schema = schema_data["schema"]
        else:
            schema = schema_data

        info = self._extract_info_from_schema(schema)
        attributes = schema.get("attributes", {})

        fields: dict[str, FieldSchema] = {}
        for field_name, field_data in attributes.items():
            try:
                fields[field_name] = self._parse_field_schema(field_data)
            except Exception as e:
                logger.warning(f"Failed to parse field {field_name}: {e}")

        return ContentTypeSchema(
            uid=uid,
            display_name=info.get("displayName", uid),
            kind=schema.get("kind", "collectionType"),
            singular_name=info.get("singularName"),
            plural_name=info.get("pluralName"),
            fields=fields,
        )

    def _parse_field_schema(self, field_data: dict[str, Any]) -> FieldSchema:
        """Parse a single field schema.

        Args:
            field_data: Field data from API response

        Returns:
            Parsed field schema
        """
        field_type_str = field_data.get("type", "string")

        # Try to match to FieldType enum, fallback to STRING
        try:
            field_type = FieldType(field_type_str)
        except ValueError:
            logger.warning(f"Unknown field type: {field_type_str}, using STRING")
            field_type = FieldType.STRING

        schema = FieldSchema(
            type=field_type,
            required=field_data.get("required", False),
            unique=field_data.get("unique", False),
        )

        # Relation-specific
        if field_type == FieldType.RELATION:
            relation_str = field_data.get("relation")
            if relation_str:
                try:
                    schema.relation = RelationType(relation_str)
                except ValueError:
                    logger.warning(f"Unknown relation type: {relation_str}")

            schema.target = field_data.get("target")
            schema.mapped_by = field_data.get("mappedBy")
            schema.inversed_by = field_data.get("inversedBy")

        return schema

    @property
    def cache_size(self) -> int:
        """Get number of cached schemas.

        Returns:
            Number of schemas in cache
        """
        return len(self._cache)

    @property
    def fetch_count(self) -> int:
        """Get number of schemas fetched from API.

        Returns:
            Number of API fetches performed
        """
        return self._fetch_count
