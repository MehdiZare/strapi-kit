"""Main export orchestration for Strapi data.

This module coordinates the export of content types, entities,
and media files from a Strapi instance.
"""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from py_strapi.exceptions import ImportExportError
from py_strapi.models.export_format import (
    ExportData,
    ExportedEntity,
    ExportedMediaFile,
    ExportMetadata,
)
from py_strapi.operations.streaming import stream_entities
from py_strapi.export.relation_resolver import RelationResolver

if TYPE_CHECKING:
    from py_strapi.client.sync_client import SyncClient

logger = logging.getLogger(__name__)


class StrapiExporter:
    """Export Strapi content and media to portable format.

    This class handles the complete export process including:
    - Content type discovery
    - Entity export with relations
    - Media file download
    - Progress tracking

    Example:
        >>> from py_strapi import SyncClient
        >>> from py_strapi.export import StrapiExporter
        >>>
        >>> with SyncClient(config) as client:
        ...     exporter = StrapiExporter(client)
        ...     export_data = exporter.export_content_types(
        ...         ["api::article.article", "api::author.author"]
        ...     )
        ...     exporter.save_to_file(export_data, "export.json")
    """

    def __init__(self, client: "SyncClient"):
        """Initialize exporter with Strapi client.

        Args:
            client: Synchronous Strapi client
        """
        self.client = client

    def export_content_types(
        self,
        content_types: list[str],
        *,
        include_media: bool = True,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> ExportData:
        """Export specified content types with all their entities.

        Args:
            content_types: List of content type UIDs to export
            include_media: Whether to include media file references
            progress_callback: Optional callback(current, total, message)

        Returns:
            ExportData containing all exported content

        Raises:
            ImportExportError: If export fails

        Example:
            >>> export_data = exporter.export_content_types([
            ...     "api::article.article",
            ...     "api::author.author"
            ... ])
            >>> print(f"Exported {export_data.get_entity_count()} entities")
        """
        try:
            # Create metadata
            metadata = ExportMetadata(
                strapi_version=self.client.api_version or "auto",
                source_url=self.client.base_url,
                content_types=content_types,
            )

            export_data = ExportData(metadata=metadata)

            total_content_types = len(content_types)

            for idx, content_type in enumerate(content_types):
                if progress_callback:
                    progress_callback(
                        idx,
                        total_content_types,
                        f"Exporting {content_type}",
                    )

                # Extract endpoint from UID (e.g., "api::article.article" -> "articles")
                endpoint = self._uid_to_endpoint(content_type)

                # Stream entities for memory efficiency
                entities = []
                for entity in stream_entities(self.client, endpoint):
                    # Extract relations from entity data
                    relations = RelationResolver.extract_relations(entity.attributes)

                    # Strip relations from data to store separately
                    clean_data = RelationResolver.strip_relations(entity.attributes)

                    exported_entity = ExportedEntity(
                        id=entity.id,
                        document_id=entity.document_id,
                        content_type=content_type,
                        data=clean_data,
                        relations=relations,
                    )
                    entities.append(exported_entity)

                export_data.entities[content_type] = entities

            # Update metadata with counts
            export_data.metadata.total_entities = export_data.get_entity_count()

            # TODO: Export media if requested
            if include_media:
                logger.warning("Media export not yet implemented")

            if progress_callback:
                progress_callback(
                    total_content_types,
                    total_content_types,
                    "Export complete",
                )

            return export_data

        except Exception as e:
            raise ImportExportError(f"Export failed: {e}") from e

    @staticmethod
    def save_to_file(export_data: ExportData, file_path: str | Path) -> None:
        """Save export data to JSON file.

        Args:
            export_data: Export data to save
            file_path: Path to output file

        Example:
            >>> StrapiExporter.save_to_file(export_data, "backup.json")
        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            # Use model_dump with mode='json' for proper serialization
            json.dump(export_data.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

        logger.info(f"Export saved to {path}")

    @staticmethod
    def load_from_file(file_path: str | Path) -> ExportData:
        """Load export data from JSON file.

        Args:
            file_path: Path to export file

        Returns:
            Loaded export data

        Raises:
            ImportExportError: If file cannot be loaded

        Example:
            >>> export_data = StrapiExporter.load_from_file("backup.json")
        """
        try:
            path = Path(file_path)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            return ExportData.model_validate(data)

        except Exception as e:
            raise ImportExportError(f"Failed to load export file: {e}") from e

    @staticmethod
    def _uid_to_endpoint(uid: str) -> str:
        """Convert content type UID to API endpoint.

        Args:
            uid: Content type UID (e.g., "api::article.article")

        Returns:
            API endpoint (e.g., "articles")

        Example:
            >>> StrapiExporter._uid_to_endpoint("api::article.article")
            'articles'
        """
        # Extract the last part after "::" and make it plural
        # This is a simplified approach - may need refinement
        parts = uid.split("::")
        if len(parts) == 2:
            name = parts[1].split(".")[0]
            # Simple pluralization - add 's' if not already plural
            if not name.endswith("s"):
                return name + "s"
            return name
        return uid
