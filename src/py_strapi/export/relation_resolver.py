"""Relation resolution for import operations.

This module handles extracting relations from entities during export
and resolving them during import using ID mappings.
"""

import logging
from typing import Any

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
        """
        payload: dict[str, Any] = {}

        for field_name, ids in relations.items():
            if len(ids) == 1:
                # Single relation - use single ID
                payload[field_name] = ids[0]
            elif len(ids) > 1:
                # Multiple relations - use array
                payload[field_name] = ids

        return payload
