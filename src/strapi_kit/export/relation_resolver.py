"""Relation resolution for import operations.

This module handles extracting relations from entities during export
and resolving them during import using ID mappings.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from copy import deepcopy
from typing import TYPE_CHECKING, Any, TypeGuard

from ..exceptions import StrapiError
from ..models.export_format import RelationId
from ..models.request.relation_write import relation_write
from ..models.schema import FieldSchema, FieldType, RelationType

if TYPE_CHECKING:
    from ..cache.schema_cache import InMemorySchemaCache
    from ..models.schema import ContentTypeSchema

logger = logging.getLogger(__name__)


def _is_relation_id_value(value: object) -> TypeGuard[int | str]:
    """Return True for extractable relation IDs.

    ``RelationId`` is a Pydantic input type, not an ``isinstance`` target.
    ``bool`` is a subclass of ``int`` but is not a valid id.
    """
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, str))


class RelationResolver:
    """Handles relation extraction and resolution for export/import.

    During export: Extracts relation IDs from entity attributes
    During import: Resolves old IDs to new IDs using mapping
    """

    @staticmethod
    def resolve_relations(
        relations: dict[str, list[RelationId]],
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
    ) -> dict[str, list[RelationId]]:
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
        relations: dict[str, list[RelationId]] = {}

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
                component_uid = field_schema.component
                if component_uid and field_value:
                    for suffix, item in RelationResolver._component_items(
                        field_value, field_path=field_name
                    ):
                        nested = RelationResolver._extract_from_component(
                            item, component_uid, schema_cache, f"{field_name}{suffix}"
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
    ) -> dict[str, list[RelationId]]:
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

        relations: dict[str, list[RelationId]] = {}

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
                    for suffix, item in RelationResolver._component_items(
                        field_value, field_path=full_key
                    ):
                        nested = RelationResolver._extract_from_component(
                            item, nested_uid, schema_cache, f"{full_key}{suffix}"
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
    def _id_from_relation_object(item: dict[str, Any]) -> RelationId | None:
        """Prefer v5 ``documentId``; fall back to numeric ``id``."""
        document_id = item.get("documentId", item.get("document_id"))
        if isinstance(document_id, str) and document_id.strip():
            return document_id.strip()
        if "id" in item and item["id"] is not None:
            raw_id = item["id"]
            if _is_relation_id_value(raw_id):
                return raw_id
        return None

    @staticmethod
    def _extract_ids_from_field(field_value: Any) -> list[RelationId] | None:
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

        if _is_relation_id_value(field_value):
            return [field_value]

        if isinstance(field_value, list):
            if not field_value:
                return []
            ids: list[RelationId] = []
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
                elif _is_relation_id_value(item):
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
                field_value = RelationResolver._unwrap_component_payload(field_value)
                if isinstance(field_value, list):
                    try:
                        component_schema = schema_cache.get_component_schema(field_schema.component)
                    except StrapiError:
                        cleaned_data[field_name] = field_value
                        continue
                    cleaned_items: list[Any] = []
                    for idx, item in enumerate(field_value):
                        if isinstance(item, dict):
                            cleaned_items.append(
                                RelationResolver.strip_relations_with_schema(
                                    item, component_schema, schema_cache
                                )
                            )
                            continue
                        logger.warning(
                            "Unexpected component list item at %s[%s]: %s",
                            field_name,
                            idx,
                            type(item).__name__,
                        )
                        cleaned_items.append(item)
                    cleaned_data[field_name] = cleaned_items
                    continue
                if isinstance(field_value, dict):
                    try:
                        component_schema = schema_cache.get_component_schema(field_schema.component)
                    except StrapiError:
                        cleaned_data[field_name] = field_value
                        continue
                    cleaned_data[field_name] = RelationResolver.strip_relations_with_schema(
                        field_value, component_schema, schema_cache
                    )
                    continue
                if field_value is not None:
                    logger.warning(
                        "Unexpected component payload for %s: %s",
                        field_name,
                        type(field_value).__name__,
                    )
                cleaned_data[field_name] = field_value
                continue
            if field_schema.type == FieldType.DYNAMIC_ZONE and isinstance(field_value, list):
                cleaned_zone: list[Any] = []
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
                            cleaned_zone.append(item)
                            continue
                        cleaned_zone.append(
                            RelationResolver.strip_relations_with_schema(
                                item, dz_schema, schema_cache
                            )
                        )
                    else:
                        cleaned_zone.append(item)
                cleaned_data[field_name] = cleaned_zone
                continue
            cleaned_data[field_name] = field_value

        return cleaned_data

    _V4_COMPONENT_WRAPPER_KEYS = frozenset({"data", "meta"})

    @staticmethod
    def _unwrap_component_payload(field_value: Any) -> Any:
        """Unwrap a v4 ``{data: dict|list}`` component wrapper when present.

        Only ``{"data": ...}`` / ``{"data": ..., "meta": ...}`` are wrappers.
        A real component that also has a ``data`` field keeps its siblings.
        """
        if not isinstance(field_value, dict) or "data" not in field_value:
            return field_value
        if field_value.keys() - RelationResolver._V4_COMPONENT_WRAPPER_KEYS:
            return field_value
        if any(key in field_value for key in ("documentId", "document_id", "__component")):
            return field_value
        inner = field_value["data"]
        if inner is None or isinstance(inner, (dict, list)):
            return inner
        return field_value

    @staticmethod
    def _component_items(
        field_value: Any, *, field_path: str = ""
    ) -> list[tuple[str, dict[str, Any]]]:
        """Walk a component field by payload shape, not ``repeatable``.

        A ``repeatable=False`` schema with a list still yields ``seo[0].``
        prefixes so nested paths such as ``seo[0].author`` are not dropped.
        v4 ``{data: ...}`` wrappers are unwrapped first. Unexpected shapes
        are logged and skipped.
        """
        value = RelationResolver._unwrap_component_payload(field_value)
        if value is None:
            return []
        if isinstance(value, list):
            items: list[tuple[str, dict[str, Any]]] = []
            for idx, item in enumerate(value):
                if isinstance(item, dict):
                    items.append((f"[{idx}].", item))
                    continue
                logger.warning(
                    "Unexpected component list item at %s[%s]: %s",
                    field_path or "component",
                    idx,
                    type(item).__name__,
                )
            return items
        if isinstance(value, dict):
            return [(".", value)]
        logger.warning(
            "Unexpected component payload for %s: %s",
            field_path or "component",
            type(value).__name__,
        )
        return []

    @staticmethod
    def split_field_path(field_path: str) -> list[tuple[str, int | None]]:
        """Split ``seo[0].author`` / ``seo.author`` into ``(name, index)`` tokens."""
        tokens: list[tuple[str, int | None]] = []
        for raw in field_path.replace("]", "").split("."):
            if not raw:
                continue
            if "[" in raw:
                name, index_text = raw.split("[", 1)
                if not name or not index_text.isdigit():
                    return []
                tokens.append((name, int(index_text)))
            else:
                tokens.append((raw, None))
        return tokens

    @staticmethod
    def relation_field_is_multiple(
        schema: ContentTypeSchema,
        field_path: str,
        schema_cache: InMemorySchemaCache | None = None,
        entity_data: dict[str, Any] | None = None,
    ) -> bool:
        """Return True for many-side relations (oneToMany / manyToMany)."""
        field_schema = RelationResolver._field_schema_for_path(
            schema, field_path, schema_cache, entity_data
        )
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
        entity_data: dict[str, Any] | None = None,
    ) -> str | None:
        """Resolve a (possibly nested) field path to a relation target UID."""
        field_schema = RelationResolver._field_schema_for_path(
            schema, field_path, schema_cache, entity_data
        )
        if field_schema is None or field_schema.type != FieldType.RELATION:
            return None
        return field_schema.target

    @staticmethod
    def _field_schema_for_path(
        schema: ContentTypeSchema,
        field_path: str,
        schema_cache: InMemorySchemaCache | None,
        entity_data: dict[str, Any] | None = None,
    ) -> FieldSchema | None:
        """Walk ``seo[0].author`` / ``content[0].author`` against schema + data."""
        tokens = RelationResolver.split_field_path(field_path)
        if not tokens:
            return None
        current_schema = schema
        current_data: Any = entity_data
        field_schema: FieldSchema | None = None
        for position, (name, index) in enumerate(tokens):
            field_schema = current_schema.fields.get(name)
            if field_schema is None:
                return None
            if position == len(tokens) - 1:
                return field_schema
            next_data: Any = None
            if isinstance(current_data, dict):
                next_data = current_data.get(name)
                if index is not None:
                    if not isinstance(next_data, list) or index >= len(next_data):
                        next_data = None
                    else:
                        next_data = next_data[index]
            elif isinstance(current_data, list) and index is not None and index < len(current_data):
                next_data = current_data[index]
            if field_schema.type == FieldType.COMPONENT and field_schema.component:
                if schema_cache is None:
                    return None
                try:
                    current_schema = schema_cache.get_component_schema(field_schema.component)
                except StrapiError:
                    return None
                current_data = next_data
            elif field_schema.type == FieldType.DYNAMIC_ZONE:
                if schema_cache is None or not isinstance(next_data, dict):
                    return None
                component_uid = next_data.get("__component")
                if not isinstance(component_uid, str) or not component_uid:
                    return None
                try:
                    current_schema = schema_cache.get_component_schema(component_uid)
                except StrapiError:
                    return None
                current_data = next_data
            else:
                return None
        return field_schema

    @staticmethod
    def _set_path_value(tree: dict[str, Any], field_path: str, value: Any) -> bool:
        """Set ``value`` at ``field_path`` inside ``tree``. Returns False if missing."""
        tokens = RelationResolver.split_field_path(field_path)
        if not tokens:
            return False
        current: Any = tree
        for name, index in tokens[:-1]:
            if not isinstance(current, dict) or name not in current:
                return False
            current = current[name]
            if index is not None:
                if not isinstance(current, list) or index >= len(current):
                    return False
                current = current[index]
        last_name, last_index = tokens[-1]
        if last_index is not None:
            if not isinstance(current, dict) or last_name not in current:
                return False
            target = current[last_name]
            if not isinstance(target, list) or last_index >= len(target):
                return False
            target[last_index] = value
            return True
        if not isinstance(current, dict):
            return False
        current[last_name] = value
        return True

    @staticmethod
    def _build_relation_payload(
        relations: dict[str, list[Any]],
        schema: ContentTypeSchema,
        schema_cache: InMemorySchemaCache | None,
        entity_data: dict[str, Any] | None,
        skipped: list[str] | None,
        value_for: Callable[[list[Any], bool], Any],
    ) -> dict[str, Any]:
        """Build top-level and nested relation writes from path keys."""
        payload: dict[str, Any] = {}
        nested_by_root: dict[str, list[tuple[str, list[Any]]]] = {}
        for field_name, ids in relations.items():
            if "." in field_name or "[" in field_name:
                tokens = RelationResolver.split_field_path(field_name)
                if not tokens:
                    if skipped is not None:
                        skipped.append(field_name)
                    continue
                nested_by_root.setdefault(tokens[0][0], []).append((field_name, ids))
                continue
            multiple = RelationResolver.relation_field_is_multiple(
                schema, field_name, schema_cache, entity_data
            )
            payload[field_name] = value_for(ids, multiple)

        for root, items in nested_by_root.items():
            if entity_data is None or root not in entity_data:
                if skipped is not None:
                    skipped.extend(path for path, _ in items)
                continue
            tree = {root: deepcopy(entity_data[root])}
            wrote_any = False
            for path, ids in items:
                multiple = RelationResolver.relation_field_is_multiple(
                    schema, path, schema_cache, entity_data
                )
                if not RelationResolver._set_path_value(tree, path, value_for(ids, multiple)):
                    if skipped is not None:
                        skipped.append(path)
                    continue
                wrote_any = True
            if wrote_any:
                payload[root] = tree[root]
        return payload

    @staticmethod
    def build_v5_relation_payload(
        relations: dict[str, list[str]],
        schema: ContentTypeSchema,
        schema_cache: InMemorySchemaCache | None = None,
        *,
        entity_data: dict[str, Any] | None = None,
        skipped: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build a Strapi 5 relation write payload from documentId lists.

        Nested paths such as ``seo[0].author`` are merged into a copy of
        ``entity_data`` so component / dynamic-zone scalars are preserved.
        Paths that cannot be written are appended to ``skipped``.
        """
        return RelationResolver._build_relation_payload(
            relations,
            schema,
            schema_cache,
            entity_data,
            skipped,
            lambda ids, multiple: relation_write(document_ids=ids, multiple=multiple),
        )

    @staticmethod
    def build_nested_numeric_payload(
        relations: dict[str, list[int]],
        schema: ContentTypeSchema,
        schema_cache: InMemorySchemaCache | None = None,
        *,
        entity_data: dict[str, Any] | None = None,
        skipped: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build a v4 numeric relation payload, including nested component paths."""

        def _numeric(ids: list[Any], multiple: bool) -> Any:
            numbers = [item for item in ids if isinstance(item, int)]
            if not numbers:
                return []
            if multiple or len(numbers) != 1:
                return numbers
            return numbers[0]

        return RelationResolver._build_relation_payload(
            relations,
            schema,
            schema_cache,
            entity_data,
            skipped,
            _numeric,
        )
