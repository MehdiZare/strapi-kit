"""Main import orchestration for Strapi data.

This module coordinates the import of content types, entities,
and media files into a Strapi instance.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from py_strapi.cache.schema_cache import InMemorySchemaCache
from py_strapi.exceptions import ImportExportError, ValidationError
from py_strapi.export.media_handler import MediaHandler
from py_strapi.export.relation_resolver import RelationResolver
from py_strapi.models.export_format import ExportData
from py_strapi.models.import_options import ImportOptions, ImportResult
from py_strapi.models.schema import ContentTypeSchema

if TYPE_CHECKING:
    from py_strapi.client.sync_client import SyncClient

logger = logging.getLogger(__name__)


class StrapiImporter:
    """Import Strapi content and media from exported format.

    This class handles the complete import process including:
    - Validation of export data
    - Relation resolution
    - Media file upload
    - Entity creation with proper ordering
    - Progress tracking

    Example:
        >>> from py_strapi import SyncClient
        >>> from py_strapi.export import StrapiImporter, StrapiExporter
        >>>
        >>> # Load export data
        >>> export_data = StrapiExporter.load_from_file("export.json")
        >>>
        >>> # Import to new instance
        >>> with SyncClient(target_config) as client:
        ...     importer = StrapiImporter(client)
        ...     result = importer.import_data(export_data)
        ...     print(f"Imported {result.entities_imported} entities")
    """

    def __init__(self, client: "SyncClient"):
        """Initialize importer with Strapi client.

        Args:
            client: Synchronous Strapi client
        """
        self.client = client
        self._schema_cache = InMemorySchemaCache(client)

    def import_data(
        self,
        export_data: ExportData,
        options: ImportOptions | None = None,
        media_dir: Path | str | None = None,
    ) -> ImportResult:
        """Import export data into Strapi instance.

        Args:
            export_data: Export data to import
            options: Import options (uses defaults if None)
            media_dir: Directory containing media files from export

        Returns:
            ImportResult with statistics and any errors

        Raises:
            ImportExportError: If import fails critically

        Example:
            >>> options = ImportOptions(
            ...     dry_run=True,
            ...     conflict_resolution=ConflictResolution.SKIP
            ... )
            >>> result = importer.import_data(
            ...     export_data,
            ...     options,
            ...     media_dir="export/media"
            ... )
            >>> if result.success:
            ...     print("Import successful!")
        """
        if options is None:
            options = ImportOptions()

        result = ImportResult(success=False, dry_run=options.dry_run)

        try:
            # Step 1: Validate export data
            if options.progress_callback:
                options.progress_callback(0, 100, "Validating export data")

            self._validate_export_data(export_data, result)

            if result.errors and not options.dry_run:
                result.success = False
                return result

            # Step 1.5: Load schemas from export metadata
            self._load_schemas_from_export(export_data)

            # Step 2: Filter content types if specified
            content_types_to_import = self._get_content_types_to_import(export_data, options)

            if not content_types_to_import:
                result.add_warning("No content types to import")
                result.success = True
                return result

            # Step 3: Import media first (if requested)
            media_id_mapping: dict[int, int] = {}
            if options.import_media and export_data.media:
                if options.progress_callback:
                    options.progress_callback(20, 100, "Importing media files")

                media_id_mapping = self._import_media(export_data, media_dir, options, result)

            # Step 4: Import entities (with updated media references)
            if options.progress_callback:
                options.progress_callback(40, 100, "Importing entities")

            self._import_entities(
                export_data,
                content_types_to_import,
                media_id_mapping,
                options,
                result,
            )

            # Step 5: Import relations (if not skipped)
            if not options.skip_relations:
                if options.progress_callback:
                    options.progress_callback(60, 100, "Importing relations")

                self._import_relations(
                    export_data,
                    content_types_to_import,
                    options,
                    result,
                )

            if options.progress_callback:
                options.progress_callback(100, 100, "Import complete")

            result.success = result.entities_failed == 0

            return result

        except Exception as e:
            result.add_error(f"Import failed: {e}")
            raise ImportExportError(f"Import failed: {e}") from e

    def _validate_export_data(self, export_data: ExportData, result: ImportResult) -> None:
        """Validate export data format and compatibility.

        Args:
            export_data: Export data to validate
            result: Result object to add errors/warnings to
        """
        # Check format version
        if not export_data.metadata.version.startswith("1."):
            result.add_warning(
                f"Export format version {export_data.metadata.version} may not be fully compatible"
            )

        # Check Strapi version compatibility
        target_version = self.client.api_version
        source_version = export_data.metadata.strapi_version

        if target_version and source_version != target_version:
            result.add_warning(
                f"Source version ({source_version}) differs from target ({target_version}). "
                "Some data may require transformation."
            )

        # Check if we have any data
        if export_data.get_entity_count() == 0:
            result.add_warning("No entities to import")

    def _get_content_types_to_import(
        self, export_data: ExportData, options: ImportOptions
    ) -> list[str]:
        """Determine which content types to import based on options.

        Args:
            export_data: Export data
            options: Import options

        Returns:
            List of content type UIDs to import
        """
        available = list(export_data.entities.keys())

        if options.content_types:
            # Only import specified content types
            return [ct for ct in options.content_types if ct in available]

        return available

    def _import_entities(
        self,
        export_data: ExportData,
        content_types: list[str],
        media_id_mapping: dict[int, int],
        options: ImportOptions,
        result: ImportResult,
    ) -> None:
        """Import entities for specified content types.

        Args:
            export_data: Export data
            content_types: Content types to import
            media_id_mapping: Mapping of old media IDs to new IDs
            options: Import options
            result: Result object to update
        """
        for content_type in content_types:
            entities = export_data.entities.get(content_type, [])

            # Extract endpoint from UID
            endpoint = self._uid_to_endpoint(content_type)

            for entity in entities:
                try:
                    # Update media references if we have mappings
                    entity_data = entity.data
                    if media_id_mapping:
                        entity_data = MediaHandler.update_media_references(
                            entity.data, media_id_mapping
                        )

                    if options.dry_run:
                        # Just validate, don't actually create
                        result.entities_imported += 1
                        continue

                    # Create entity with updated media references
                    # Note: create() already wraps data in {"data": ...}
                    response = self.client.create(endpoint, entity_data)

                    if response.data:
                        # Track ID mapping for relation resolution
                        if content_type not in result.id_mapping:
                            result.id_mapping[content_type] = {}

                        result.id_mapping[content_type][entity.id] = response.data.id
                        result.entities_imported += 1

                except ValidationError as e:
                    result.add_error(f"Validation error importing {content_type} #{entity.id}: {e}")
                    result.entities_failed += 1

                except Exception as e:
                    result.add_error(f"Failed to import {content_type} #{entity.id}: {e}")
                    result.entities_failed += 1

    def _import_relations(
        self,
        export_data: ExportData,
        content_types: list[str],
        options: ImportOptions,
        result: ImportResult,
    ) -> None:
        """Import relations for entities.

        This is done as a second pass after entities are created,
        so that all entities exist before relations are added.

        Args:
            export_data: Export data
            content_types: Content types to import relations for
            options: Import options
            result: Result object to update
        """
        for content_type in content_types:
            entities = export_data.entities.get(content_type, [])
            endpoint = self._uid_to_endpoint(content_type)

            for entity in entities:
                # Skip if no relations
                if not entity.relations:
                    continue

                # Get the new ID from mapping
                if content_type not in result.id_mapping:
                    continue

                old_id = entity.id
                if old_id not in result.id_mapping[content_type]:
                    logger.warning(
                        f"Cannot import relations for {content_type} #{old_id}: "
                        "entity not in ID mapping"
                    )
                    continue

                new_id = result.id_mapping[content_type][old_id]

                # Get schema for this content type
                try:
                    schema = self._schema_cache.get_schema(content_type)
                except Exception as e:
                    logger.warning(f"Could not load schema for {content_type}: {e}")
                    continue

                try:
                    if options.dry_run:
                        continue

                    # FIXED: Resolve relations using schema
                    resolved_relations = self._resolve_relations_with_schema(
                        entity.relations, schema, result.id_mapping
                    )

                    if not resolved_relations:
                        continue

                    # Build relation payload
                    relation_payload = RelationResolver.build_relation_payload(resolved_relations)

                    if relation_payload:
                        # Update entity with relations
                        # Note: update() already wraps data in {"data": ...}
                        self.client.update(
                            f"{endpoint}/{new_id}",
                            relation_payload,
                        )

                except Exception as e:
                    result.add_warning(
                        f"Failed to import relations for {content_type} #{new_id}: {e}"
                    )

    def _import_media(
        self,
        export_data: ExportData,
        media_dir: Path | str | None,
        options: ImportOptions,
        result: ImportResult,
    ) -> dict[int, int]:
        """Import media files from export.

        Args:
            export_data: Export data containing media metadata
            media_dir: Directory containing downloaded media files
            options: Import options
            result: Result object to update

        Returns:
            Mapping of old media IDs to new media IDs
        """
        media_id_mapping: dict[int, int] = {}

        if not export_data.media:
            return media_id_mapping

        if media_dir is None:
            logger.warning(
                "Media directory not specified - skipping media import. "
                "Media references in entities will not be updated."
            )
            return media_id_mapping

        media_path = Path(media_dir)
        if not media_path.exists():
            result.add_error(f"Media directory not found: {media_dir}")
            return media_id_mapping

        for exported_media in export_data.media:
            try:
                if options.dry_run:
                    result.media_imported += 1
                    continue

                # Find local file with path traversal protection
                file_path = (media_path / exported_media.local_path).resolve()

                # Security: Ensure resolved path stays within media_path
                if not file_path.is_relative_to(media_path.resolve()):
                    result.add_error(
                        f"Security: Invalid media path {exported_media.local_path} - "
                        "path traversal detected"
                    )
                    result.media_skipped += 1
                    continue

                if not file_path.exists():
                    result.add_warning(
                        f"Media file not found: {file_path.name} (ID: {exported_media.id})"
                    )
                    result.media_skipped += 1
                    continue

                # Upload file
                uploaded = MediaHandler.upload_media_file(self.client, file_path, exported_media)

                # Track ID mapping
                media_id_mapping[exported_media.id] = uploaded.id
                result.media_imported += 1

            except Exception as e:
                result.add_warning(f"Failed to import media {exported_media.name}: {e}")
                result.media_skipped += 1

        logger.info(f"Imported {result.media_imported}/{len(export_data.media)} media files")
        return media_id_mapping

    def _load_schemas_from_export(self, export_data: ExportData) -> None:
        """Load schemas from export metadata into cache.

        Args:
            export_data: Export data containing schemas
        """
        # Load all schemas into cache
        for content_type, schema in export_data.metadata.schemas.items():
            self._schema_cache.cache_schema(content_type, schema)

        logger.info(f"Loaded {self._schema_cache.cache_size} schemas from export")

    def _resolve_relations_with_schema(
        self,
        relations: dict[str, list[int | str]],
        schema: ContentTypeSchema,
        id_mapping: dict[str, dict[int, int]],
    ) -> dict[str, list[int]]:
        """Resolve relation IDs using schema information.

        Uses content type schemas to determine relation targets, enabling
        proper ID mapping during import.

        Args:
            relations: Raw relations from export (field -> [old_ids])
            schema: Schema for the content type
            id_mapping: Full ID mapping (content_type -> {old_id: new_id})

        Returns:
            Resolved relations with new IDs
        """
        resolved: dict[str, list[int]] = {}

        for field_name, old_ids in relations.items():
            # Get target content type from schema
            target_content_type = schema.get_field_target(field_name)

            if not target_content_type:
                logger.warning(f"Field {field_name} is not a relation. Skipping.")
                continue

            # Get ID mapping for target content type
            if target_content_type not in id_mapping:
                logger.warning(
                    f"No ID mapping for {target_content_type}. "
                    f"Relations in {field_name} cannot be resolved."
                )
                continue

            target_mapping = id_mapping[target_content_type]

            # Resolve old IDs to new IDs
            new_ids = []
            for old_id in old_ids:
                if isinstance(old_id, int) and old_id in target_mapping:
                    new_ids.append(target_mapping[old_id])
                else:
                    logger.warning(
                        f"Could not resolve {target_content_type} ID {old_id} "
                        f"for field {field_name}"
                    )

            if new_ids:
                resolved[field_name] = new_ids

        return resolved

    @staticmethod
    def _uid_to_endpoint(uid: str) -> str:
        """Convert content type UID to API endpoint.

        Args:
            uid: Content type UID (e.g., "api::article.article")

        Returns:
            API endpoint (e.g., "articles")
        """
        # Extract the last part after "::" and make it plural
        parts = uid.split("::")
        if len(parts) == 2:
            name = parts[1].split(".")[0]
            # Simple pluralization
            if not name.endswith("s"):
                return name + "s"
            return name
        return uid
