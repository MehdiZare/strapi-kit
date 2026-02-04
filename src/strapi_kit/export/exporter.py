"""Main export orchestration for Strapi data.

This module coordinates the export of content types, entities,
and media files from a Strapi instance.
"""

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from strapi_kit.cache.schema_cache import InMemorySchemaCache
from strapi_kit.exceptions import ImportExportError, ValidationError
from strapi_kit.export.media_handler import MediaHandler
from strapi_kit.export.relation_resolver import RelationResolver
from strapi_kit.models.export_format import (
    ExportData,
    ExportedEntity,
    ExportedMediaFile,
    ExportMetadata,
)
from strapi_kit.models.request.query import StrapiQuery
from strapi_kit.models.schema import ContentTypeSchema
from strapi_kit.operations.streaming import stream_entities

if TYPE_CHECKING:
    from strapi_kit.client.sync_client import SyncClient

logger = logging.getLogger(__name__)


class StrapiExporter:
    """Export Strapi content and media to portable format.

    This class handles the complete export process including:
    - Content type discovery
    - Entity export with relations
    - Media file download
    - Progress tracking

    Example:
        >>> from strapi_kit import SyncClient
        >>> from strapi_kit.export import StrapiExporter
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
        self._schema_cache = InMemorySchemaCache(client)

    def export_content_types(
        self,
        content_types: list[str],
        *,
        include_media: bool = True,
        media_dir: Path | str | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> ExportData:
        """Export specified content types with all their entities.

        Args:
            content_types: List of content type UIDs to export
            include_media: Whether to include media file references
            media_dir: Directory to download media files to (if include_media=True)
            progress_callback: Optional callback(current, total, message)

        Returns:
            ExportData containing all exported content

        Raises:
            ValidationError: If include_media=True but media_dir is not provided
            ImportExportError: If export fails

        Example:
            >>> export_data = exporter.export_content_types([
            ...     "api::article.article",
            ...     "api::author.author"
            ... ], media_dir="export/media")
            >>> print(f"Exported {export_data.get_entity_count()} entities")
        """
        if include_media and media_dir is None:
            raise ValidationError("media_dir must be provided when include_media=True")

        try:
            # Create metadata
            metadata = ExportMetadata(
                strapi_version=self.client.api_version or "auto",
                source_url=self.client.base_url,
                content_types=content_types,
            )

            export_data = ExportData(metadata=metadata)

            # Fetch schemas upfront (required for relation resolution)
            self._fetch_schemas(content_types, export_data, progress_callback)

            total_content_types = len(content_types)

            # Collect media IDs during entity streaming (before relations are stripped)
            all_media_ids: set[int] = set()

            for idx, content_type in enumerate(content_types):
                if progress_callback:
                    progress_callback(
                        idx,
                        total_content_types,
                        f"Exporting {content_type}",
                    )

                # Extract endpoint from UID (e.g., "api::article.article" -> "articles")
                endpoint = self._get_endpoint(content_type)

                # Build query with populate_all to ensure relations/media are included
                export_query = StrapiQuery().populate_all()

                # Get schema for this content type (already cached from _fetch_schemas)
                # Fallback to heuristic relation handling if schema not available
                try:
                    schema = self._schema_cache.get_schema(content_type)
                except Exception as e:
                    logger.warning(
                        f"Schema not available for {content_type}: {e}. "
                        "Using heuristic relation extraction."
                    )
                    schema = None

                # Stream entities for memory efficiency
                entities = []
                for entity in stream_entities(self.client, endpoint, query=export_query):
                    # Extract media references BEFORE stripping relations
                    # (media can be embedded in relation-like fields with {"data": ...} structure)
                    if include_media:
                        media_ids = MediaHandler.extract_media_references(entity.attributes)
                        all_media_ids.update(media_ids)

                    # Extract relations and strip them from data
                    # Use schema-based methods when available, fall back to heuristics
                    if schema is not None:
                        # Schema-based extraction (more accurate)
                        relations = RelationResolver.extract_relations_with_schema(
                            entity.attributes, schema, self._schema_cache
                        )
                        clean_data = RelationResolver.strip_relations_with_schema(
                            entity.attributes, schema
                        )
                    else:
                        # Heuristic fallback when schema is unavailable
                        relations = RelationResolver.extract_relations(entity.attributes)
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

            # Export media if requested
            if include_media:
                if progress_callback:
                    progress_callback(
                        total_content_types,
                        total_content_types + 1,
                        "Exporting media files",
                    )

                # Type guard: media_dir validated at method start (line 91-92)
                if media_dir is None:
                    raise ValidationError("media_dir must be provided when include_media=True")
                self._export_media(
                    export_data, media_dir, progress_callback, media_ids=all_media_ids
                )

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
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            return ExportData.model_validate(data)

        except Exception as e:
            raise ImportExportError(f"Failed to load export file: {e}") from e

    def _export_media(
        self,
        export_data: ExportData,
        media_dir: Path | str,
        progress_callback: Callable[[int, int, str], None] | None = None,
        *,
        media_ids: set[int] | None = None,
    ) -> None:
        """Export media files referenced in entities.

        Args:
            export_data: Export data to add media to
            media_dir: Directory to download media files to
            progress_callback: Optional progress callback
            media_ids: Pre-collected media IDs (extracted before relation stripping)
        """
        # Use pre-collected media IDs if provided, otherwise collect from entity.data
        # Note: Pre-collecting is important because entity.data has relations stripped,
        # so media embedded in relation-like fields would be lost otherwise.
        if media_ids is None:
            media_ids = set()
            for entities in export_data.entities.values():
                for entity in entities:
                    data_media = MediaHandler.extract_media_references(entity.data)
                    media_ids.update(data_media)

        if not media_ids:
            logger.info("No media files to export")
            return

        logger.info(f"Found {len(media_ids)} media files to export")

        # Download media files
        output_dir = Path(media_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        downloaded = 0
        for idx, media_id in enumerate(sorted(media_ids)):
            try:
                # Get media metadata
                media = self.client.get_media(media_id)

                # Download file
                local_path = MediaHandler.download_media_file(self.client, media, output_dir)

                # Create export metadata
                exported_media = MediaHandler.create_media_export(media, local_path)
                export_data.media.append(exported_media)

                downloaded += 1

                if progress_callback:
                    progress_callback(idx + 1, len(media_ids), f"Downloaded {media.name}")

            except Exception as e:
                logger.warning(f"Failed to download media {media_id}: {e}")

        export_data.metadata.total_media = downloaded
        logger.info(f"Successfully downloaded {downloaded}/{len(media_ids)} media files")

    def _fetch_schemas(
        self,
        content_types: list[str],
        export_data: ExportData,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> None:
        """Fetch and cache schemas for content types.

        Args:
            content_types: List of content type UIDs
            export_data: Export data to add schemas to
            progress_callback: Optional progress callback
        """
        logger.info(f"Fetching schemas for {len(content_types)} content types")

        for idx, content_type in enumerate(content_types):
            try:
                schema = self._schema_cache.get_schema(content_type)
                export_data.metadata.schemas[content_type] = schema

                if progress_callback:
                    progress_callback(
                        idx + 1, len(content_types), f"Fetched schema: {content_type}"
                    )
            except Exception as e:
                logger.warning(f"Failed to fetch schema for {content_type}: {e}")

        logger.info(f"Cached {self._schema_cache.cache_size} schemas")

    def _get_endpoint(self, uid: str) -> str:
        """Get API endpoint for a content type.

        Prefers schema.plural_name when available to handle custom plural
        names correctly (e.g., "person" -> "people"). Falls back to
        hardcoded pluralization rules for basic cases.

        Args:
            uid: Content type UID (e.g., "api::article.article")

        Returns:
            API endpoint (e.g., "articles")
        """
        # Try to get plural_name from cached schema
        if self._schema_cache.has_schema(uid):
            schema = self._schema_cache.get_schema(uid)
            if schema.plural_name:
                return schema.plural_name

        # Fallback to hardcoded pluralization
        return self._uid_to_endpoint_fallback(uid)

    @staticmethod
    def _uid_to_endpoint_fallback(uid: str) -> str:
        """Fallback pluralization for content type UID.

        Handles common English pluralization patterns. Used when schema
        metadata is not available.

        Args:
            uid: Content type UID (e.g., "api::article.article", "api::blog.post")

        Returns:
            API endpoint (e.g., "articles", "posts")
        """
        # Extract the model name (after the dot) and pluralize it
        # For "api::blog.post", we want "post" -> "posts", not "blog" -> "blogs"
        parts = uid.split("::")
        if len(parts) == 2:
            api_model = parts[1]
            # Get model name (after the dot if present)
            if "." in api_model:
                name = api_model.split(".")[1]
            else:
                name = api_model
            # Handle common irregular plurals
            if name.endswith("y") and not name.endswith(("ay", "ey", "oy", "uy")):
                return name[:-1] + "ies"  # category -> categories
            if name.endswith(("s", "x", "z", "ch", "sh")):
                return name + "es"  # class -> classes
            if not name.endswith("s"):
                return name + "s"
            return name
        return uid

    @staticmethod
    def _uid_to_endpoint(uid: str) -> str:
        """Convert content type UID to API endpoint.

        Deprecated: Use _get_endpoint() instead which uses schema metadata.

        Args:
            uid: Content type UID (e.g., "api::article.article")

        Returns:
            API endpoint (e.g., "articles")
        """
        return StrapiExporter._uid_to_endpoint_fallback(uid)

    def export_to_jsonl(
        self,
        content_types: list[str],
        output_path: str | Path,
        *,
        include_media: bool = True,
        media_dir: Path | str | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> int:
        """Export content types to JSONL format with streaming.

        This method writes entities directly to disk as they're fetched,
        providing O(1) memory usage regardless of export size.

        Args:
            content_types: List of content type UIDs to export
            output_path: Path to output JSONL file
            include_media: Whether to include media file references
            media_dir: Directory to download media files to (if include_media=True)
            progress_callback: Optional callback(current, total, message)

        Returns:
            Total number of entities exported

        Raises:
            ValidationError: If include_media=True but media_dir is not provided
            ImportExportError: If export fails

        Example:
            >>> count = exporter.export_to_jsonl(
            ...     ["api::article.article"],
            ...     "export.jsonl",
            ...     media_dir="media/"
            ... )
            >>> print(f"Exported {count} entities")
        """
        from strapi_kit.export.jsonl_writer import JSONLExportWriter

        if include_media and media_dir is None:
            raise ValidationError("media_dir must be provided when include_media=True")

        try:
            # Create initial metadata
            metadata = ExportMetadata(
                strapi_version=self.client.api_version or "auto",
                source_url=self.client.base_url,
                content_types=content_types,
            )

            # Fetch schemas upfront
            schemas: dict[str, ContentTypeSchema] = {}
            for content_type in content_types:
                try:
                    ct_schema = self._schema_cache.get_schema(content_type)
                    schemas[content_type] = ct_schema
                    metadata.schemas[content_type] = ct_schema
                except Exception as e:
                    logger.warning(f"Failed to fetch schema for {content_type}: {e}")

            all_media_ids: set[int] = set()

            with JSONLExportWriter(output_path) as writer:
                # Write metadata first
                writer.write_metadata(metadata)

                total_content_types = len(content_types)

                # Stream entities
                for idx, content_type in enumerate(content_types):
                    if progress_callback:
                        progress_callback(idx, total_content_types, f"Exporting {content_type}")

                    endpoint = self._get_endpoint(content_type)
                    schema: ContentTypeSchema | None = schemas.get(content_type)
                    export_query = StrapiQuery().populate_all()

                    for entity in stream_entities(self.client, endpoint, query=export_query):
                        # Extract media references before stripping
                        if include_media:
                            media_ids = MediaHandler.extract_media_references(entity.attributes)
                            all_media_ids.update(media_ids)

                        # Extract relations using schema if available
                        if schema:
                            relations = RelationResolver.extract_relations_with_schema(
                                entity.attributes, schema, self._schema_cache
                            )
                            clean_data = RelationResolver.strip_relations_with_schema(
                                entity.attributes, schema
                            )
                        else:
                            relations = RelationResolver.extract_relations(entity.attributes)
                            clean_data = RelationResolver.strip_relations(entity.attributes)

                        exported_entity = ExportedEntity(
                            id=entity.id,
                            document_id=entity.document_id,
                            content_type=content_type,
                            data=clean_data,
                            relations=relations,
                        )

                        # Write immediately - no accumulation in memory
                        writer.write_entity(exported_entity)

                # Export media if requested
                media_files: list[ExportedMediaFile] = []
                if include_media and all_media_ids:
                    if progress_callback:
                        progress_callback(
                            total_content_types,
                            total_content_types + 1,
                            "Exporting media files",
                        )

                    # Type guard: validated at method start
                    assert media_dir is not None  # noqa: S101
                    output_dir = Path(media_dir)
                    output_dir.mkdir(parents=True, exist_ok=True)

                    for media_id in sorted(all_media_ids):
                        try:
                            media = self.client.get_media(media_id)
                            local_path = MediaHandler.download_media_file(
                                self.client, media, output_dir
                            )
                            exported_media = MediaHandler.create_media_export(media, local_path)
                            media_files.append(exported_media)
                        except Exception as e:
                            logger.warning(f"Failed to download media {media_id}: {e}")

                # Write media manifest
                writer.write_media_manifest(media_files)

                if progress_callback:
                    progress_callback(
                        total_content_types,
                        total_content_types,
                        "Export complete",
                    )

                return writer.entity_count

        except Exception as e:
            raise ImportExportError(f"JSONL export failed: {e}") from e
