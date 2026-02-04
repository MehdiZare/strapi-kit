"""Main import orchestration for Strapi data.

This module coordinates the import of content types, entities,
and media files into a Strapi instance.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from strapi_kit.cache.schema_cache import InMemorySchemaCache
from strapi_kit.exceptions import (
    ImportExportError,
    NotFoundError,
    StrapiError,
    ValidationError,
)
from strapi_kit.export.media_handler import MediaHandler
from strapi_kit.export.relation_resolver import RelationResolver
from strapi_kit.models.export_format import ExportData
from strapi_kit.models.import_options import ConflictResolution, ImportOptions, ImportResult
from strapi_kit.models.schema import ContentTypeSchema

if TYPE_CHECKING:
    from strapi_kit.client.sync_client import SyncClient

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
        >>> from strapi_kit import SyncClient
        >>> from strapi_kit.export import StrapiImporter, StrapiExporter
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

            # Step 1.6: Validate relations if requested
            if options.validate_relations:
                if options.progress_callback:
                    options.progress_callback(10, 100, "Validating relations")
                self._validate_relations(export_data, result)

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

    def _validate_relations(self, export_data: ExportData, result: ImportResult) -> None:
        """Validate that all relation targets exist in export data.

        This pre-import validation ensures all referenced entities are present
        in the export, warning about any missing targets.

        Args:
            export_data: Export data to validate
            result: Result object to add warnings to
        """
        # Build set of available IDs per content type
        available_ids: dict[str, set[int]] = {}
        for ct, entities in export_data.entities.items():
            available_ids[ct] = {e.id for e in entities}

        # Check all relations
        for ct, entities in export_data.entities.items():
            # Get schema for this content type
            schema = export_data.metadata.schemas.get(ct)
            if not schema:
                continue

            for entity in entities:
                for field_name, target_ids in entity.relations.items():
                    target_ct = schema.get_field_target(field_name)
                    if not target_ct:
                        continue

                    if target_ct not in available_ids:
                        result.add_warning(
                            f"{ct}#{entity.id}.{field_name} -> target type '{target_ct}' "
                            "not in export"
                        )
                        continue

                    missing = set(target_ids) - available_ids.get(target_ct, set())
                    if missing:
                        result.add_warning(
                            f"{ct}#{entity.id}.{field_name} -> missing IDs in {target_ct}: "
                            f"{sorted(missing)}"
                        )

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

        Handles conflict resolution based on options:
        - SKIP: Skip entities that already exist
        - UPDATE: Update existing entities with imported data
        - FAIL: Fail import if conflicts are detected

        Args:
            export_data: Export data
            content_types: Content types to import
            media_id_mapping: Mapping of old media IDs to new IDs
            options: Import options
            result: Result object to update
        """
        total_entities = sum(len(export_data.entities.get(ct, [])) for ct in content_types)
        processed = 0

        for content_type in content_types:
            entities = export_data.entities.get(content_type, [])

            # Get endpoint from schema (prefers plural_name) or fallback to UID
            endpoint = self._get_endpoint(content_type)

            # Process entities in batches for progress reporting
            for batch_start in range(0, len(entities), options.batch_size):
                batch = entities[batch_start : batch_start + options.batch_size]

                for entity in batch:
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

                        # Check for existing entity if document_id is available (for conflict handling)
                        existing_id: int | None = None
                        if entity.document_id:
                            existing_id = self._check_entity_exists(endpoint, entity.document_id)

                        if existing_id is not None:
                            # Entity already exists - handle according to conflict resolution
                            if options.conflict_resolution == ConflictResolution.SKIP:
                                result.entities_skipped += 1
                                # Still track the ID mapping for relations
                                if content_type not in result.id_mapping:
                                    result.id_mapping[content_type] = {}
                                result.id_mapping[content_type][entity.id] = existing_id
                                continue

                            elif options.conflict_resolution == ConflictResolution.FAIL:
                                raise ImportExportError(
                                    f"Entity already exists: {content_type} with documentId "
                                    f"{entity.document_id}. Use conflict_resolution=SKIP or UPDATE."
                                )

                            elif options.conflict_resolution == ConflictResolution.UPDATE:
                                # Update existing entity
                                response = self.client.update(
                                    f"{endpoint}/{entity.document_id}",
                                    entity_data,
                                )
                                if response.data:
                                    if content_type not in result.id_mapping:
                                        result.id_mapping[content_type] = {}
                                    result.id_mapping[content_type][entity.id] = response.data.id
                                    result.entities_updated += 1
                                continue

                        # Create new entity
                        response = self.client.create(endpoint, entity_data)

                        if response.data:
                            # Track ID mapping for relation resolution
                            if content_type not in result.id_mapping:
                                result.id_mapping[content_type] = {}

                            result.id_mapping[content_type][entity.id] = response.data.id
                            result.entities_imported += 1

                    except ValidationError as e:
                        result.add_error(
                            f"Validation error importing {content_type} #{entity.id}: {e}"
                        )
                        result.entities_failed += 1

                    except ImportExportError:
                        # Re-raise ImportExportError (e.g., from FAIL conflict resolution)
                        raise

                    except StrapiError as e:
                        # Catch Strapi-specific errors (API errors, network issues, etc.)
                        result.add_error(f"Failed to import {content_type} #{entity.id}: {e}")
                        result.entities_failed += 1

                    finally:
                        processed += 1

                # Batch progress callback
                if options.progress_callback and total_entities > 0:
                    progress = 40 + int((processed / total_entities) * 20)
                    options.progress_callback(
                        progress, 100, f"Importing entities ({processed}/{total_entities})"
                    )

    def _check_entity_exists(self, endpoint: str, document_id: str) -> int | None:
        """Check if an entity exists by document ID.

        Args:
            endpoint: API endpoint
            document_id: Document ID to check

        Returns:
            Entity's numeric ID if exists, None otherwise
        """
        try:
            response = self.client.get_one(f"{endpoint}/{document_id}")
            if response.data:
                return response.data.id
        except NotFoundError:
            pass
        except Exception as e:
            logger.warning(f"Error checking entity existence: {e}")
        return None

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
            endpoint = self._get_endpoint(content_type)

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

                # Check for existing media with same hash (if not overwriting)
                if not options.overwrite_media:
                    existing_id = self._find_media_by_hash(exported_media.hash)
                    if existing_id is not None:
                        # Use existing media - no need to upload
                        media_id_mapping[exported_media.id] = existing_id
                        result.media_skipped += 1
                        logger.debug(f"Media {exported_media.name} already exists (hash match)")
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

    def _find_media_by_hash(self, file_hash: str) -> int | None:
        """Find existing media file by hash.

        Args:
            file_hash: File hash to search for

        Returns:
            Media ID if found, None otherwise
        """
        try:
            from strapi_kit.models.request.filters import FilterBuilder
            from strapi_kit.models.request.query import StrapiQuery

            query = StrapiQuery().filter(FilterBuilder().eq("hash", file_hash))
            response = self.client.list_media(query)

            if response.data:
                return response.data[0].id
        except Exception:  # noqa: S110 - Intentionally ignore lookup failures
            pass
        return None

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

            # Preserve empty lists only when source relation was explicitly empty.
            # If old_ids had values but none resolved, skip to avoid clearing relations.
            if new_ids or len(old_ids) == 0:
                resolved[field_name] = new_ids

        return resolved

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

    # Keep for backward compatibility
    @staticmethod
    def _uid_to_endpoint(uid: str) -> str:
        """Convert content type UID to API endpoint.

        Deprecated: Use _get_endpoint() instead which uses schema metadata.

        Args:
            uid: Content type UID (e.g., "api::article.article")

        Returns:
            API endpoint (e.g., "articles")
        """
        return StrapiImporter._uid_to_endpoint_fallback(uid)

    def import_from_jsonl(
        self,
        jsonl_path: str | Path,
        options: ImportOptions | None = None,
        media_dir: Path | str | None = None,
    ) -> ImportResult:
        """Import data from JSONL file with two-pass streaming.

        This method uses two-pass streaming for true O(1) memory usage:
        - Pass 1: Create entities, store only ID mappings (old_id -> new_id)
        - Pass 2: Re-read file to resolve relations using ID mappings

        Memory profile: O(entity_count × 2 ints) for ID mappings only,
        not O(entities) for full entity objects.

        Args:
            jsonl_path: Path to input JSONL file
            options: Import options (uses defaults if None)
            media_dir: Directory containing media files from export

        Returns:
            ImportResult with statistics and any errors

        Raises:
            ImportExportError: If import fails critically

        Example:
            >>> result = importer.import_from_jsonl(
            ...     "export.jsonl",
            ...     media_dir="media/"
            ... )
            >>> if result.success:
            ...     print(f"Imported {result.entities_imported} entities")
        """
        from strapi_kit.export.jsonl_reader import JSONLImportReader

        if options is None:
            options = ImportOptions()

        result = ImportResult(success=False, dry_run=options.dry_run)
        jsonl_path = Path(jsonl_path)

        try:
            # ============================================================
            # Pass 1: Read metadata, import media, create entities
            # Store only ID mappings (O(entity_count × 2 ints))
            # ============================================================
            with JSONLImportReader(jsonl_path) as reader:
                # Step 1: Read metadata
                if options.progress_callback:
                    options.progress_callback(0, 100, "Reading metadata")

                metadata = reader.read_metadata()

                # Load schemas from metadata
                for ct, schema in metadata.schemas.items():
                    self._schema_cache.cache_schema(ct, schema)

                # Step 2: Import media first (if requested)
                media_id_mapping: dict[int, int] = {}
                if options.import_media:
                    if options.progress_callback:
                        options.progress_callback(10, 100, "Importing media files")

                    media_files = reader.read_media_manifest()
                    if media_files and media_dir:
                        media_dir_path = Path(media_dir)
                        for media in media_files:
                            try:
                                if options.dry_run:
                                    result.media_imported += 1
                                    continue

                                # Check for existing media (overwrite_media option)
                                if (
                                    hasattr(options, "overwrite_media")
                                    and not options.overwrite_media
                                ):
                                    # Try to find by hash
                                    existing = self._find_media_by_hash(media.hash)
                                    if existing:
                                        media_id_mapping[media.id] = existing
                                        result.media_skipped += 1
                                        continue

                                # Upload media file with path traversal protection
                                local_path = (media_dir_path / media.local_path).resolve()

                                # Security: Ensure resolved path stays within media_dir_path
                                if not local_path.is_relative_to(media_dir_path.resolve()):
                                    result.add_error(
                                        f"Security: Invalid media path {media.local_path} - "
                                        "path traversal detected"
                                    )
                                    result.media_skipped += 1
                                    continue

                                if local_path.exists():
                                    uploaded = self.client.upload_file(str(local_path))
                                    media_id_mapping[media.id] = uploaded.id
                                    result.media_imported += 1
                                else:
                                    result.add_warning(f"Media file not found: {local_path}")
                            except Exception as e:
                                result.add_error(f"Failed to import media {media.id}: {e}")

                # Step 3: Create entities - streaming with ID mapping only
                if options.progress_callback:
                    options.progress_callback(30, 100, "Creating entities (pass 1)")

                # Store only ID mappings: old_id -> new_id (O(entity_count × 2 ints))
                id_mappings: dict[str, dict[int, int]] = {}

                for entity in reader.iter_entities():
                    # Filter by content types if specified
                    if options.content_types and entity.content_type not in options.content_types:
                        continue

                    content_type = entity.content_type
                    if content_type not in id_mappings:
                        id_mappings[content_type] = {}

                    try:
                        # Update media references
                        entity_data = entity.data
                        if media_id_mapping:
                            entity_data = MediaHandler.update_media_references(
                                entity.data, media_id_mapping
                            )

                        if options.dry_run:
                            result.entities_imported += 1
                            continue

                        # Get endpoint
                        endpoint = self._get_endpoint(content_type)

                        # Check for existing entity
                        existing_id = None
                        if entity.document_id:
                            existing_id = self._check_entity_exists(endpoint, entity.document_id)

                        if existing_id:
                            if options.conflict_resolution == ConflictResolution.SKIP:
                                id_mappings[content_type][entity.id] = existing_id
                                result.entities_skipped += 1
                                continue
                            elif options.conflict_resolution == ConflictResolution.FAIL:
                                result.add_error(
                                    f"Entity already exists: {content_type} {entity.document_id}"
                                )
                                result.entities_failed += 1
                                continue
                            elif options.conflict_resolution == ConflictResolution.UPDATE:
                                # Update existing entity (use document_id for v5 endpoint)
                                self.client.update(
                                    f"{endpoint}/{entity.document_id}", data=entity_data
                                )
                                id_mappings[content_type][entity.id] = existing_id
                                result.entities_updated += 1
                                continue

                        # Create new entity
                        response = self.client.create(endpoint, data=entity_data)
                        if response.data:
                            id_mappings[content_type][entity.id] = response.data.id
                        result.entities_imported += 1

                    except Exception as e:
                        result.add_error(f"Failed to import {content_type} {entity.id}: {e}")
                        result.entities_failed += 1

            # ============================================================
            # Pass 2: Re-read file to resolve relations using ID mappings
            # True O(1) memory - entities processed one at a time
            # ============================================================
            if not options.skip_relations and not options.dry_run:
                if options.progress_callback:
                    options.progress_callback(70, 100, "Resolving relations (pass 2)")

                with JSONLImportReader(jsonl_path) as reader2:
                    # Skip metadata (already loaded)
                    reader2.read_metadata()

                    for entity in reader2.iter_entities():
                        # Filter by content types if specified
                        if (
                            options.content_types
                            and entity.content_type not in options.content_types
                        ):
                            continue

                        # Skip entities without relations
                        if not entity.relations:
                            continue

                        content_type = entity.content_type
                        endpoint = self._get_endpoint(content_type)

                        # Get new ID for this entity
                        new_id = id_mappings.get(content_type, {}).get(entity.id)
                        if not new_id:
                            continue

                        # Get schema from cache
                        try:
                            schema = self._schema_cache.get_schema(content_type)
                        except Exception:  # noqa: S112 - Skip content types without schema
                            continue

                        try:
                            # Resolve relations using ID mappings
                            resolved = self._resolve_relations_with_schema(
                                entity.relations, schema, id_mappings
                            )

                            if resolved:
                                payload = RelationResolver.build_relation_payload(resolved)
                                self.client.update(f"{endpoint}/{new_id}", data=payload)
                                result.relations_imported += 1
                        except Exception as e:
                            result.add_warning(
                                f"Failed to import relations for {content_type} {entity.id}: {e}"
                            )

            if options.progress_callback:
                options.progress_callback(100, 100, "Import complete")

            result.success = result.entities_failed == 0
            return result

        except Exception as e:
            result.add_error(f"JSONL import failed: {e}")
            raise ImportExportError(f"JSONL import failed: {e}") from e
