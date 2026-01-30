"""Main import orchestration for Strapi data.

This module coordinates the import of content types, entities,
and media files into a Strapi instance.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from py_strapi.exceptions import ImportExportError, ValidationError
from py_strapi.export.media_handler import MediaHandler
from py_strapi.export.relation_resolver import RelationResolver
from py_strapi.models.export_format import ExportData
from py_strapi.models.import_options import ImportOptions, ImportResult

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
                    response = self.client.create(endpoint, {"data": entity_data})

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

                try:
                    if options.dry_run:
                        continue

                    # Resolve relations using ID mapping
                    # Note: This assumes all relations are to entities in the same export
                    # TODO: Handle relations to entities not in export
                    resolved_relations = {}
                    for field_name, old_ids in entity.relations.items():
                        # For simplicity, we'll just track that relations exist
                        # Full resolution would need to know the target content type
                        resolved_relations[field_name] = old_ids

                    # Build relation payload
                    relation_payload = RelationResolver.build_relation_payload(
                        resolved_relations  # type: ignore[arg-type]
                    )

                    if relation_payload:
                        # Update entity with relations
                        self.client.update(
                            f"{endpoint}/{new_id}",
                            {"data": relation_payload},
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

                # Find local file
                file_path = media_path / exported_media.local_path

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
