"""Relation resolution for import operations.

This module handles extracting relations from entities during export
and resolving them during import using ID mappings.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..exceptions import StrapiError
from ..models.request.relation_write import relation_write
from ..models.schema import FieldSchema, FieldType, RelationType

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
    def _id_from_relation_object(item: dict[str, Any]) -> int | str | None:
        """Prefer v5 ``documentId``; fall back to numeric ``id``."""
        document_id = item.get("documentId", item.get("document_id"))
        if isinstance(document_id, str) and document_id.strip():
            return document_id.strip()
        if "id" in item and item["id"] is not None:
            raw_id = item["id"]
            if isinstance(raw_id, (int, str)):
                return raw_id
        return None

    @staticmethod
    def _extract_ids_from_field(field_value: Any) -> list[int | str] | None:
        """Extract IDs from a relation field value.

        Handles v4 ``{"data": ...}`` wrappers, flat v5 objects
        (``documentId`` at the field root), lists of those objects, and
        bare ``int`` / ``str`` IDs.

        Args:
            field_value: Field value from entity data

        Returns:
            List of IDs if this looks like a relation, None otherwise
        """
        if field_value is None:
            return []

        # v4 wrapper (not a populated v5 entity, which has documentId at root)
        if (
            isinstance(field_value, dict)
            and "data" in field_value
            and "documentId" not in field_value
            and "document_id" not in field_value
        ):
            return RelationResolver._extract_ids_from_field(field_value["data"])

        if isinstance(field_value, dict):
            extracted = RelationResolver._id_from_relation_object(field_value)
            return [extracted] if extracted is not None else None

        if isinstance(field_value, (int, str)):
            return [field_value]

        if isinstance(field_value, list):
            if not field_value:
                return []
            ids: list[int | str] = []
            found = False
            for item in field_value:
                if isinstance(item, dict):
                    extracted = RelationResolver._id_from_relation_object(item)
                    if extracted is None and "data" in item:
                        nested = RelationResolver._extract_ids_from_field(item)
                        if nested:
                            ids.extend(nested)
                            found = True
                    elif extracted is not None:
                        ids.append(extracted)
                        found = True
                elif isinstance(item, (int, str)):
                    ids.append(item)
                    found = True
            return ids if found else None

        return None

    @staticmethod
    def strip_relations_with_schema(
        data: dict[str, Any],
        schema: ContentTypeSchema,
        schema_cache: InMemorySchemaCache | None = None,
    ) -> dict[str, Any]:
        """Remove relation fields, including nested component / DZ relations.

        Uses schema to identify relation fields, preserving non-relation
        fields that happen to contain {"data": ...}.

        Args:
            data: Entity attributes dictionary
            schema: Content type schema with field definitions
            schema_cache: Optional cache for component schemas

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
        cleaned_data: dict[str, Any] = {}

        for field_name, field_value in data.items():
            field_schema = schema.fields.get(field_name)
            if field_schema is None:
                cleaned_data[field_name] = field_value
                continue
            if field_schema.type == FieldType.RELATION:
                continue
            if (
                field_schema.type == FieldType.COMPONENT
                and schema_cache is not None
                and field_schema.component
            ):
                if field_schema.repeatable and isinstance(field_value, list):
                    cleaned_data[field_name] = [
                        RelationResolver.strip_relations_with_schema(
                            item,
                            schema_cache.get_component_schema(field_schema.component),
                            schema_cache,
                        )
                        if isinstance(item, dict)
                        else item
                        for item in field_value
                    ]
                    continue
                if isinstance(field_value, dict):
                    cleaned_data[field_name] = RelationResolver.strip_relations_with_schema(
                        field_value,
                        schema_cache.get_component_schema(field_schema.component),
                        schema_cache,
                    )
                    continue
            if field_schema.type == FieldType.DYNAMIC_ZONE and isinstance(field_value, list):
                cleaned_items: list[Any] = []
                for item in field_value:
                    if (
                        isinstance(item, dict)
                        and "__component" in item
                        and schema_cache is not None
                    ):
                        dz_uid = item["__component"]
                        try:
                            dz_schema = schema_cache.get_component_schema(dz_uid)
                        except StrapiError:
                            cleaned_items.append(item)
                            continue
                        cleaned_items.append(
                            RelationResolver.strip_relations_with_schema(
                                item, dz_schema, schema_cache
                            )
                        )
                    else:
                        cleaned_items.append(item)
                cleaned_data[field_name] = cleaned_items
                continue
            cleaned_data[field_name] = field_value

        return cleaned_data

    @staticmethod
    def relation_field_is_multiple(
        schema: ContentTypeSchema,
        field_path: str,
        schema_cache: InMemorySchemaCache | None = None,
    ) -> bool:
        """Return True for many-side relations (oneToMany / manyToMany)."""
        field_schema = RelationResolver._field_schema_for_path(schema, field_path, schema_cache)
        if field_schema is None or field_schema.relation is None:
            return False
        return field_schema.relation in {
            RelationType.ONE_TO_MANY,
            RelationType.MANY_TO_MANY,
        }

    @staticmethod
    def target_for_field_path(
        schema: ContentTypeSchema,
        field_path: str,
        schema_cache: InMemorySchemaCache | None = None,
    ) -> str | None:
        """Resolve a (possibly nested) field path to a relation target UID."""
        field_schema = RelationResolver._field_schema_for_path(schema, field_path, schema_cache)
        if field_schema is None or field_schema.type != FieldType.RELATION:
            return None
        return field_schema.target

    @staticmethod
    def _field_schema_for_path(
        schema: ContentTypeSchema,
        field_path: str,
        schema_cache: InMemorySchemaCache | None,
    ) -> FieldSchema | None:
        """Walk ``seo[0].author`` / ``seo.author`` against schema (+ components)."""
        parts = [part for part in field_path.replace("[", ".").replace("]", "").split(".") if part]
        current = schema
        field_schema = None
        for index, part in enumerate(parts):
            if part.isdigit():
                continue
            field_schema = current.fields.get(part)
            if field_schema is None:
                return None
            if index == len(parts) - 1:
                return field_schema
            if field_schema.type == FieldType.COMPONENT and field_schema.component:
                if schema_cache is None:
                    return None
                try:
                    current = schema_cache.get_component_schema(field_schema.component)
                except StrapiError:
                    return None
            elif field_schema.type == FieldType.DYNAMIC_ZONE:
                return None
            else:
                return None
        return field_schema

    @staticmethod
    def build_v5_relation_payload(
        relations: dict[str, list[str]],
        schema: ContentTypeSchema,
        schema_cache: InMemorySchemaCache | None = None,
    ) -> dict[str, Any]:
        """Build a Strapi 5 relation write payload from documentId lists.

        Nested (prefixed) keys are omitted — only top-level relation fields
        are written here.
        """
        payload: dict[str, Any] = {}
        for field_name, document_ids in relations.items():
            if "." in field_name or "[" in field_name:
                continue
            multiple = RelationResolver.relation_field_is_multiple(schema, field_name, schema_cache)
            payload[field_name] = relation_write(document_ids=document_ids, multiple=multiple)
        return payload
