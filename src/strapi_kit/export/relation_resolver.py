"""Relation resolution for import operations.

This module handles extracting relations from entities during export
and resolving them during import using ID mappings.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..exceptions import StrapiError
from ..models.schema import FieldType

if TYPE_CHECKING:
    from ..cache.schema_cache import InMemorySchemaCache
    from ..models.schema import ContentTypeSchema

logger = logging.getLogger(__name__)


class RelationResolver:
    """Handles relation extraction and resolution for export/import.

    During export: Extracts relation IDs from entity attributes
    During import: Resolves old IDs to new IDs using mapping
    """

    @staticmethod
    def extract_relations(data: dict[str, Any]) -> dict[str, list[int | str]]:
        """Extract relation field IDs from entity data.

        Args:
            data: Entity attributes dictionary

        Returns:
            Dictionary mapping relation field names to lists of IDs

        Example:
            >>> data = {
            ...     "title": "Article",
            ...     "author": {"data": {"id": 5}},
            ...     "categories": {"data": [{"id": 1}, {"id": 2}]}
            ... }
            >>> RelationResolver.extract_relations(data)
            {'author': [5], 'categories': [1, 2]}
        """
        relations: dict[str, list[int | str]] = {}

        for field_name, field_value in data.items():
            if isinstance(field_value, dict) and "data" in field_value:
                # This looks like a relation field
                relation_data = field_value["data"]

                if relation_data is None:
                    # Null relation
                    relations[field_name] = []
                elif isinstance(relation_data, dict):
                    # Single relation
                    if "id" in relation_data:
                        relations[field_name] = [relation_data["id"]]
                elif isinstance(relation_data, list):
                    # Multiple relations
                    ids = [item["id"] for item in relation_data if "id" in item]
                    if ids:
                        relations[field_name] = ids

        return relations

    @staticmethod
    def strip_relations(data: dict[str, Any]) -> dict[str, Any]:
        """Remove relation fields from entity data.

        Useful for importing entities without relations first,
        then adding relations in a second pass.

        Args:
            data: Entity attributes dictionary

        Returns:
            Copy of data with relation fields removed

        Example:
            >>> data = {"title": "Article", "author": {"data": {"id": 5}}}
            >>> RelationResolver.strip_relations(data)
            {'title': 'Article'}
        """
        cleaned_data = {}

        for field_name, field_value in data.items():
            # Skip fields that look like relations
            if isinstance(field_value, dict) and "data" in field_value:
                continue

            cleaned_data[field_name] = field_value

        return cleaned_data

    @staticmethod
    def resolve_relations(
        relations: dict[str, list[int | str]],
        id_mapping: dict[str, dict[int, int]],
        content_type: str,
    ) -> dict[str, list[int]]:
        """Resolve old relation IDs to new IDs using mapping.

        Args:
            relations: Relation field mapping (field -> [old_ids])
            id_mapping: ID mapping (content_type -> {old_id: new_id})
            content_type: Content type of the related entities

        Returns:
            Resolved relations with new IDs

        Example:
            >>> relations = {"categories": [1, 2]}
            >>> id_mapping = {
            ...     "api::category.category": {1: 10, 2: 11}
            ... }
            >>> RelationResolver.resolve_relations(
            ...     relations,
            ...     id_mapping,
            ...     "api::category.category"
            ... )
            {'categories': [10, 11]}
        """
        resolved: dict[str, list[int]] = {}

        type_mapping = id_mapping.get(content_type, {})

        for field_name, old_ids in relations.items():
            new_ids = []
            for old_id in old_ids:
                if isinstance(old_id, int) and old_id in type_mapping:
                    new_ids.append(type_mapping[old_id])
                else:
                    logger.warning(
                        f"Could not resolve {content_type} ID {old_id} for field {field_name}"
                    )

            if new_ids:
                resolved[field_name] = new_ids

        return resolved

    @staticmethod
    def build_relation_payload(
        relations: dict[str, list[int]],
    ) -> dict[str, Any]:
        """Build Strapi relation payload format.

        Args:
            relations: Resolved relations (field -> [new_ids])

        Returns:
            Payload in Strapi format for updating relations

        Example:
            >>> relations = {"author": [10], "categories": [11, 12]}
            >>> RelationResolver.build_relation_payload(relations)
            {'author': 10, 'categories': [11, 12]}

            >>> # Empty list clears the relation
            >>> relations = {"author": []}
            >>> RelationResolver.build_relation_payload(relations)
            {'author': []}
        """
        payload: dict[str, Any] = {}

        for field_name, ids in relations.items():
            if len(ids) == 0:
                # Empty list - explicit clear of relation
                payload[field_name] = []
            elif len(ids) == 1:
                # Single relation - use single ID
                payload[field_name] = ids[0]
            else:
                # Multiple relations - use array
                payload[field_name] = ids

        return payload

    # Schema-aware extraction methods

    @staticmethod
    def extract_relations_with_schema(
        data: dict[str, Any],
        schema: ContentTypeSchema,
        schema_cache: InMemorySchemaCache | None = None,
    ) -> dict[str, list[int | str]]:
        """Extract relations using schema - only actual relation fields.

        This method uses the content type schema to identify relation fields,
        avoiding false positives from fields that happen to contain {"data": ...}.
        It also recursively extracts relations from components and dynamic zones.

        Args:
            data: Entity attributes dictionary
            schema: Content type schema with field definitions
            schema_cache: Optional schema cache for component lookups

        Returns:
            Dictionary mapping relation field paths to lists of IDs

        Example:
            >>> # Only extracts from actual relation fields defined in schema
            >>> data = {
            ...     "title": "Article",
            ...     "author": {"data": {"id": 5}},
            ...     "metadata": {"data": "not a relation"}  # Won't be extracted
            ... }
            >>> relations = RelationResolver.extract_relations_with_schema(data, schema)
            {'author': [5]}  # metadata excluded because not a relation in schema
        """
        relations: dict[str, list[int | str]] = {}

        for field_name, field_value in data.items():
            field_schema = schema.fields.get(field_name)
            if not field_schema:
                continue

            if field_schema.type == FieldType.RELATION:
                # Extract IDs from relation field
                ids = RelationResolver._extract_ids_from_field(field_value)
                if ids is not None:
                    relations[field_name] = ids

            elif field_schema.type == FieldType.COMPONENT and schema_cache:
                # Recursively extract from component
                component_uid = field_schema.component
                if component_uid and field_value:
                    if field_schema.repeatable and isinstance(field_value, list):
                        # Repeatable component - list of components
                        for idx, item in enumerate(field_value):
                            if isinstance(item, dict):
                                nested = RelationResolver._extract_from_component(
                                    item, component_uid, schema_cache, f"{field_name}[{idx}]."
                                )
                                relations.update(nested)
                    elif isinstance(field_value, dict):
                        # Single component
                        nested = RelationResolver._extract_from_component(
                            field_value, component_uid, schema_cache, f"{field_name}."
                        )
                        relations.update(nested)

            elif field_schema.type == FieldType.DYNAMIC_ZONE and schema_cache:
                # Recursively extract from dynamic zone components
                if isinstance(field_value, list):
                    for idx, item in enumerate(field_value):
                        if isinstance(item, dict) and "__component" in item:
                            component_uid = item["__component"]
                            nested = RelationResolver._extract_from_component(
                                item, component_uid, schema_cache, f"{field_name}[{idx}]."
                            )
                            relations.update(nested)

        return relations

    @staticmethod
    def _extract_from_component(
        component_data: dict[str, Any],
        component_uid: str,
        schema_cache: InMemorySchemaCache,
        prefix: str = "",
    ) -> dict[str, list[int | str]]:
        """Recursively extract relations from a component.

        Args:
            component_data: Component data dictionary
            component_uid: Component UID for schema lookup
            schema_cache: Schema cache for component lookups
            prefix: Field path prefix for nested fields

        Returns:
            Dictionary mapping prefixed field paths to lists of IDs
        """
        try:
            component_schema = schema_cache.get_component_schema(component_uid)
        except StrapiError:
            logger.warning(f"Could not fetch component schema: {component_uid}", exc_info=True)
            return {}

        relations: dict[str, list[int | str]] = {}

        for field_name, field_value in component_data.items():
            if field_name == "__component":
                continue  # Skip component type marker

            field_schema = component_schema.fields.get(field_name)
            if not field_schema:
                continue

            full_key = f"{prefix}{field_name}"

            if field_schema.type == FieldType.RELATION:
                ids = RelationResolver._extract_ids_from_field(field_value)
                if ids is not None:
                    relations[full_key] = ids

            elif field_schema.type == FieldType.COMPONENT:
                nested_uid = field_schema.component
                if nested_uid and field_value:
                    if field_schema.repeatable and isinstance(field_value, list):
                        for idx, item in enumerate(field_value):
                            if isinstance(item, dict):
                                nested = RelationResolver._extract_from_component(
                                    item, nested_uid, schema_cache, f"{full_key}[{idx}]."
                                )
                                relations.update(nested)
                    elif isinstance(field_value, dict):
                        nested = RelationResolver._extract_from_component(
                            field_value, nested_uid, schema_cache, f"{full_key}."
                        )
                        relations.update(nested)

            elif field_schema.type == FieldType.DYNAMIC_ZONE:
                if isinstance(field_value, list):
                    for idx, item in enumerate(field_value):
                        if isinstance(item, dict) and "__component" in item:
                            dz_uid = item["__component"]
                            nested = RelationResolver._extract_from_component(
                                item, dz_uid, schema_cache, f"{full_key}[{idx}]."
                            )
                            relations.update(nested)

        return relations

    @staticmethod
    def _extract_ids_from_field(field_value: Any) -> list[int | str] | None:
        """Extract IDs from a relation field value.

        Handles both v4 nested format and v5 flat format.

        Args:
            field_value: Field value from entity data

        Returns:
            List of IDs if this looks like a relation, None otherwise
        """
        if field_value is None:
            return []

        # v4 format: {"data": ...}
        if isinstance(field_value, dict) and "data" in field_value:
            relation_data = field_value["data"]
            if relation_data is None:
                return []
            elif isinstance(relation_data, dict) and "id" in relation_data:
                return [relation_data["id"]]
            elif isinstance(relation_data, list):
                return [
                    item["id"] for item in relation_data if isinstance(item, dict) and "id" in item
                ]

        # v5 format: direct ID or list of IDs (can be int or str)
        if isinstance(field_value, (int, str)):
            return [field_value]
        elif isinstance(field_value, list):
            ids: list[int | str] = [item for item in field_value if isinstance(item, (int, str))]
            if ids:
                return ids

        return None

    @staticmethod
    def strip_relations_with_schema(
        data: dict[str, Any],
        schema: ContentTypeSchema,
    ) -> dict[str, Any]:
        """Remove only actual relation fields from entity data.

        Uses schema to identify relation fields, preserving non-relation
        fields that happen to contain {"data": ...}.

        Args:
            data: Entity attributes dictionary
            schema: Content type schema with field definitions

        Returns:
            Copy of data with relation fields removed

        Example:
            >>> data = {
            ...     "title": "Article",
            ...     "author": {"data": {"id": 5}},  # Relation - removed
            ...     "metadata": {"data": "custom"}   # Not relation - kept
            ... }
            >>> stripped = RelationResolver.strip_relations_with_schema(data, schema)
            {'title': 'Article', 'metadata': {'data': 'custom'}}
        """
        cleaned_data = {}

        for field_name, field_value in data.items():
            field_schema = schema.fields.get(field_name)

            # Keep field if it's not in schema or not a relation
            if not field_schema or field_schema.type != FieldType.RELATION:
                cleaned_data[field_name] = field_value

        return cleaned_data
