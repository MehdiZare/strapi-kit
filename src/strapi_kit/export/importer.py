"""Main import orchestration for Strapi data.

This module coordinates the import of content types, entities,
and media files into a Strapi instance.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from strapi_kit.cache.schema_cache import InMemorySchemaCache
from strapi_kit.exceptions import (
    ImportExportError,
    NotFoundError,
    StrapiError,
    ValidationError,
    is_unknown_locale_param,
    is_unknown_status_param,
)
from strapi_kit.export.media_handler import MediaHandler
from strapi_kit.export.relation_resolver import RelationResolver
from strapi_kit.models.enums import DocumentStatus
from strapi_kit.models.export_format import ExportData, ExportedEntity, ExportedMediaFile
from strapi_kit.models.import_options import ConflictResolution, ImportOptions, ImportResult
from strapi_kit.models.request.filters import FilterBuilder
from strapi_kit.models.request.query import StrapiQuery
from strapi_kit.models.schema import ContentTypeSchema
from strapi_kit.utils.endpoints import collection_endpoint

if TYPE_CHECKING:
    from strapi_kit.client.sync_client import SyncClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _MediaMaps:
    """Destination media id mappings for entity write-shape remapping."""

    id_to_id: dict[int, int]
    doc_to_doc: dict[str, str]
    id_to_doc: dict[int, str]


@dataclass(frozen=True, slots=True)
class _ExistingDocument:
    """A dest document returned by the existence probe."""

    id: int
    document_id: str | None


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
            media_maps = _MediaMaps(id_to_id={}, doc_to_doc={}, id_to_doc={})
            if options.import_media and export_data.media:
                if options.progress_callback:
                    options.progress_callback(20, 100, "Importing media files")

                media_maps = self._import_media(export_data, media_dir, options, result)

            # Step 4: Import entities (with updated media references)
            if options.progress_callback:
                options.progress_callback(40, 100, "Importing entities")

            pending_publish: list[tuple[str, Any, str]] = []
            fail_conflicts: list[str] = []
            fail_conflict_keys: set[tuple[str, int]] = set()
            self._import_entities(
                export_data,
                content_types_to_import,
                media_maps,
                options,
                result,
                pending_publish,
                fail_conflicts,
                fail_conflict_keys,
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
                    fail_conflict_keys,
                )

            # Publish after relations so stock v5 PUT ?status=published
            # is not overwritten by a later draft relation write.
            self._publish_pending(pending_publish, options, result)

            if options.progress_callback:
                options.progress_callback(100, 100, "Import complete")

            self._raise_fail_conflicts(fail_conflicts, result)

            result.success = result.entities_failed == 0 and not result.errors

            return result

        except ImportExportError:
            raise
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
        # Build set of available IDs per content type (both int and str for v5)
        available_ids: dict[str, set[int | str]] = {}
        for ct, entities in export_data.entities.items():
            ids: set[int | str] = set()
            for e in entities:
                ids.add(e.id)
                # Include document_id for v5 string-based relations
                if e.document_id:
                    ids.add(e.document_id)
            available_ids[ct] = ids

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
        media_maps: _MediaMaps,
        options: ImportOptions,
        result: ImportResult,
        pending_publish: list[tuple[str, Any, str]],
        fail_conflicts: list[str],
        fail_conflict_keys: set[tuple[str, int]],
    ) -> None:
        """Import entities for specified content types.

        Handles conflict resolution based on options:
        - SKIP: Skip locales that already exist; write missing locales
        - UPDATE: Overwrite existing locales; write missing locales
        - FAIL: Record an existing locale, keep writing missing locales,
          then abort after the entity/relation/publish pass

        Args:
            export_data: Export data
            content_types: Content types to import
            media_maps: Destination media id / documentId mappings
            options: Import options
            result: Result object to update
            pending_publish: Live source rows to publish after relations
            fail_conflicts: FAIL hits collected for a late abort
            fail_conflict_keys: ``(content_type, entity.id)`` of FAIL hits so
                the relation pass can skip overwriting those locales
        """
        total_entities = sum(len(export_data.entities.get(ct, [])) for ct in content_types)
        processed = 0

        for content_type in content_types:
            entities = export_data.entities.get(content_type, [])

            endpoint = self._get_endpoint(content_type)

            # Process entities in batches for progress reporting
            for batch_start in range(0, len(entities), options.batch_size):
                batch = entities[batch_start : batch_start + options.batch_size]

                for entity in batch:
                    try:
                        # Update media references if we have mappings
                        entity_data = entity.data
                        if media_maps.id_to_id or media_maps.doc_to_doc:
                            entity_data = MediaHandler.update_media_references(
                                entity.data,
                                media_maps.id_to_id,
                                media_maps.doc_to_doc,
                                media_maps.id_to_doc,
                            )

                        if options.dry_run:
                            result.entities_imported += 1
                            continue

                        self._import_one_entity(
                            entity,
                            endpoint=endpoint,
                            content_type=content_type,
                            entity_data=entity_data,
                            options=options,
                            pending_publish=pending_publish,
                            id_mapping=result.id_mapping,
                            doc_id_mapping=result.doc_id_mapping,
                            doc_id_to_new_id=result.doc_id_to_new_id,
                            doc_id_to_new_document_id=result.doc_id_to_new_document_id,
                            result=result,
                            fail_conflicts=fail_conflicts,
                            fail_conflict_keys=fail_conflict_keys,
                        )

                    except ValidationError as e:
                        result.add_error(
                            f"Validation error importing {content_type} #{entity.id}: {e}"
                        )
                        result.entities_failed += 1

                    except ImportExportError:
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

    def _import_one_entity(
        self,
        entity: ExportedEntity,
        *,
        endpoint: str,
        content_type: str,
        entity_data: dict[str, Any],
        options: ImportOptions,
        pending_publish: list[tuple[str, Any, str]],
        id_mapping: dict[str, dict[int, int]],
        doc_id_mapping: dict[str, dict[int, str]],
        doc_id_to_new_id: dict[str, dict[str, int]],
        doc_id_to_new_document_id: dict[str, dict[str, str]],
        result: ImportResult,
        fail_conflicts: list[str],
        fail_conflict_keys: set[tuple[str, int]],
    ) -> None:
        """Create, localize, skip, or update one exported entity."""
        source_doc = entity.document_id
        dest_doc = (
            doc_id_to_new_document_id.get(content_type, {}).get(source_doc) if source_doc else None
        )

        this_locale: _ExistingDocument | None = None
        if source_doc:
            this_locale = self._probe_document(endpoint, source_doc, entity.locale)

        if this_locale is not None:
            dest_doc = dest_doc or this_locale.document_id or source_doc
            if options.conflict_resolution == ConflictResolution.SKIP:
                result.entities_skipped += 1
                self._record_entity_mappings(
                    content_type=content_type,
                    entity_id=entity.id,
                    source_document_id=source_doc,
                    new_id=this_locale.id,
                    dest_document_id=dest_doc,
                    id_mapping=id_mapping,
                    doc_id_mapping=doc_id_mapping,
                    doc_id_to_new_id=doc_id_to_new_id,
                    doc_id_to_new_document_id=doc_id_to_new_document_id,
                )
                return

            if options.conflict_resolution == ConflictResolution.FAIL:
                locale_note = f" locale={entity.locale}" if entity.locale else ""
                fail_conflicts.append(
                    f"Entity already exists: {content_type} with documentId "
                    f"{source_doc}{locale_note}. Use conflict_resolution=SKIP or UPDATE."
                )
                fail_conflict_keys.add((content_type, entity.id))
                result.entities_failed += 1
                self._record_entity_mappings(
                    content_type=content_type,
                    entity_id=entity.id,
                    source_document_id=source_doc,
                    new_id=this_locale.id,
                    dest_document_id=dest_doc,
                    id_mapping=id_mapping,
                    doc_id_mapping=doc_id_mapping,
                    doc_id_to_new_id=doc_id_to_new_id,
                    doc_id_to_new_document_id=doc_id_to_new_document_id,
                )
                return

            write_query = self._write_query(entity)
            response = self.client.update(
                endpoint, entity_data, query=write_query, document_id=dest_doc
            )
            if response.data:
                dest_document_id = response.data.document_id or dest_doc
                self._record_entity_mappings(
                    content_type=content_type,
                    entity_id=entity.id,
                    source_document_id=source_doc,
                    new_id=response.data.id,
                    dest_document_id=dest_document_id,
                    id_mapping=id_mapping,
                    doc_id_mapping=doc_id_mapping,
                    doc_id_to_new_id=doc_id_to_new_id,
                    doc_id_to_new_document_id=doc_id_to_new_document_id,
                )
                self._queue_publish(pending_publish, content_type, entity, dest_document_id)
                result.entities_updated += 1
            return

        write_query = self._write_query(entity)
        if dest_doc is None and source_doc and entity.locale:
            any_locale = self._probe_any_document(endpoint, source_doc)
            if any_locale is not None:
                dest_doc = any_locale.document_id or source_doc

        if dest_doc is not None:
            response = self.client.update(
                endpoint, entity_data, query=write_query, document_id=dest_doc
            )
            if response.data:
                dest_document_id = response.data.document_id or dest_doc
                self._record_entity_mappings(
                    content_type=content_type,
                    entity_id=entity.id,
                    source_document_id=source_doc,
                    new_id=response.data.id,
                    dest_document_id=dest_document_id,
                    id_mapping=id_mapping,
                    doc_id_mapping=doc_id_mapping,
                    doc_id_to_new_id=doc_id_to_new_id,
                    doc_id_to_new_document_id=doc_id_to_new_document_id,
                )
                self._queue_publish(pending_publish, content_type, entity, dest_document_id)
                result.entities_imported += 1
            return

        response = self.client.create(endpoint, entity_data, query=write_query)
        if response.data:
            self._record_entity_mappings(
                content_type=content_type,
                entity_id=entity.id,
                source_document_id=source_doc,
                new_id=response.data.id,
                dest_document_id=response.data.document_id,
                id_mapping=id_mapping,
                doc_id_mapping=doc_id_mapping,
                doc_id_to_new_id=doc_id_to_new_id,
                doc_id_to_new_document_id=doc_id_to_new_document_id,
            )
            self._queue_publish(
                pending_publish,
                content_type,
                entity,
                response.data.document_id,
            )
            result.entities_imported += 1

    def _probe_document(
        self, endpoint: str, document_id: str, locale: str | None
    ) -> _ExistingDocument | None:
        """Published-then-draft existence probe, optionally locale-scoped.

        ``Invalid key locale`` retries that GET once without ``locale``.
        A draft ``ValidationError`` is absent only for unknown
        ``status`` / ``publicationState``.
        """
        path = self.client.document_path(endpoint, document_id)
        published = StrapiQuery().with_locale(locale) if locale else None
        try:
            response = self._get_one_with_locale_fallback(path, published, had_locale=bool(locale))
            found = self._existing_from_response(response)
            if found is not None:
                return found
        except NotFoundError:
            pass

        draft = StrapiQuery().with_document_status(DocumentStatus.DRAFT)
        if locale:
            draft = draft.with_locale(locale)
        try:
            response = self._get_one_with_locale_fallback(path, draft, had_locale=bool(locale))
            return self._existing_from_response(response)
        except NotFoundError:
            return None
        except ValidationError as error:
            if is_unknown_status_param(error):
                return None
            raise

    def _probe_any_document(self, endpoint: str, document_id: str) -> _ExistingDocument | None:
        """Find a dest document across locales.

        A no-locale GET is the default locale only. ``locale=all`` plus a
        ``documentId`` filter sees a dest that exists only in a non-default
        locale. ``Invalid key locale`` falls back to the default-locale
        document GET (non-i18n types).
        """
        published = (
            StrapiQuery()
            .filter(FilterBuilder().eq("documentId", document_id))
            .with_locale("all")
            .paginate(page=1, page_size=1)
        )
        try:
            found = self._existing_from_collection(self.client.get_many(endpoint, query=published))
            if found is not None:
                return found
        except NotFoundError:
            pass
        except ValidationError as error:
            if is_unknown_locale_param(error):
                return self._probe_document(endpoint, document_id, locale=None)
            raise

        draft = published.copy().with_document_status(DocumentStatus.DRAFT)
        try:
            return self._existing_from_collection(self.client.get_many(endpoint, query=draft))
        except NotFoundError:
            return None
        except ValidationError as error:
            if is_unknown_locale_param(error):
                return self._probe_document(endpoint, document_id, locale=None)
            if is_unknown_status_param(error):
                return None
            raise

    def _get_one_with_locale_fallback(
        self, path: str, query: StrapiQuery | None, *, had_locale: bool
    ) -> Any:
        """GET once; if ``locale=`` is unknown, retry without it."""
        try:
            return self.client.get_one(path, query=query)
        except ValidationError as error:
            if had_locale and is_unknown_locale_param(error):
                return self.client.get_one(path, query=self._without_locale(query))
            raise

    @staticmethod
    def _without_locale(query: StrapiQuery | None) -> StrapiQuery | None:
        """Return a copy of ``query`` with ``locale`` cleared."""
        if query is None:
            return None
        copied = query.copy().without_locale()
        return copied if copied.to_query_params() else None

    @staticmethod
    def _existing_from_response(response: Any) -> _ExistingDocument | None:
        """Build a probe hit when the body identifies a document."""
        data = response.data
        if data is None or data.id is None:
            return None
        return _ExistingDocument(id=data.id, document_id=data.document_id)

    @staticmethod
    def _existing_from_collection(response: Any) -> _ExistingDocument | None:
        """Build a probe hit from the first row of a collection GET."""
        rows = response.data
        if not rows:
            return None
        data = rows[0]
        if data.id is None:
            return None
        return _ExistingDocument(id=data.id, document_id=data.document_id)

    @staticmethod
    def _record_entity_mappings(
        *,
        content_type: str,
        entity_id: int,
        source_document_id: str | None,
        new_id: int,
        dest_document_id: str | None,
        id_mapping: dict[str, dict[int, int]],
        doc_id_mapping: dict[str, dict[int, str]],
        doc_id_to_new_id: dict[str, dict[str, int]],
        doc_id_to_new_document_id: dict[str, dict[str, str]],
    ) -> None:
        """Record numeric and documentId mappings for later relation writes."""
        id_mapping.setdefault(content_type, {})[entity_id] = new_id
        if dest_document_id:
            doc_id_mapping.setdefault(content_type, {})[entity_id] = dest_document_id
        if source_document_id:
            doc_id_to_new_id.setdefault(content_type, {})[source_document_id] = new_id
            if dest_document_id:
                doc_id_to_new_document_id.setdefault(content_type, {})[source_document_id] = (
                    dest_document_id
                )

    def _write_query(self, entity: ExportedEntity) -> StrapiQuery | None:
        """Locale query for create, update, localize, publish, and relation PUT."""
        if entity.locale:
            return StrapiQuery().with_locale(entity.locale)
        return None

    @staticmethod
    def _raise_fail_conflicts(fail_conflicts: list[str], result: ImportResult) -> None:
        """Abort after the write pass when FAIL collected existing locales.

        ``ImportResult`` counts and later-pass ``errors`` travel on
        ``ImportExportError.details`` so a late abort does not hide what
        already landed (or failed) on dest.
        """
        if not fail_conflicts:
            return
        details: dict[str, Any] = {
            "conflicts": list(fail_conflicts),
            "errors": list(result.errors),
            "entities_imported": result.entities_imported,
            "entities_failed": result.entities_failed,
            "entities_skipped": result.entities_skipped,
            "relations_imported": result.relations_imported,
        }
        extra = ""
        if result.errors:
            extra = " Additional import errors: " + "; ".join(result.errors)
        if len(fail_conflicts) == 1:
            raise ImportExportError(fail_conflicts[0] + extra, details=details)
        raise ImportExportError(
            f"{len(fail_conflicts)} locales already exist. "
            "Use conflict_resolution=SKIP or UPDATE. " + "; ".join(fail_conflicts) + extra,
            details=details,
        )

    @staticmethod
    def _queue_publish(
        pending_publish: list[tuple[str, Any, str]],
        content_type: str,
        entity: ExportedEntity,
        dest_document_id: str | None,
    ) -> None:
        """Queue a live source document to publish after relations are written."""
        if entity.published_at is None or not dest_document_id:
            return
        pending_publish.append((content_type, entity, dest_document_id))

    def _publish_pending(
        self,
        pending_publish: list[tuple[str, Any, str]],
        options: ImportOptions,
        result: ImportResult,
    ) -> None:
        """Publish after relation writes so stock v5 draft PUTs cannot hide links."""
        if options.dry_run or not pending_publish:
            return
        for content_type, entity, dest_document_id in pending_publish:
            try:
                endpoint = self._get_endpoint(content_type)
                self.client.publish(endpoint, dest_document_id, query=self._write_query(entity))
            except StrapiError as error:
                result.add_error(f"Failed to publish {content_type} #{entity.id}: {error}")

    def _import_relations(
        self,
        export_data: ExportData,
        content_types: list[str],
        options: ImportOptions,
        result: ImportResult,
        fail_conflict_keys: set[tuple[str, int]],
    ) -> None:
        """Import relations for entities.

        This is done as a second pass after entities are created,
        so that all entities exist before relations are added.

        Args:
            export_data: Export data
            content_types: Content types to import relations for
            options: Import options
            result: Result object to update
            fail_conflict_keys: FAIL-conflicted locales; keep inbound mappings
                but do not overwrite those dest rows
        """
        for content_type in content_types:
            entities = export_data.entities.get(content_type, [])
            endpoint = self._get_endpoint(content_type)

            for entity in entities:
                # Skip if no relations
                if not entity.relations:
                    continue
                if (content_type, entity.id) in fail_conflict_keys:
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
                    result.add_error(
                        f"Failed to load schema for {content_type} while importing relations: {e}"
                    )
                    continue

                try:
                    if options.dry_run:
                        continue

                    applied, skipped = self._apply_entity_relations(
                        entity,
                        schema,
                        endpoint,
                        result.id_mapping,
                        result.doc_id_mapping,
                        result.doc_id_to_new_id,
                        result.doc_id_to_new_document_id,
                    )
                    if skipped:
                        result.add_error(
                            "Skipped nested relations for "
                            f"{content_type} #{entity.id}: {', '.join(skipped)}"
                        )
                    if applied:
                        result.relations_imported += 1
                    elif entity.relations:
                        result.add_error(
                            f"Could not write relations for {content_type} #{entity.id}"
                        )

                except Exception as e:
                    result.add_error(
                        f"Failed to import relations for {content_type} #{new_id}: {e}"
                    )

    def _import_media(
        self,
        export_data: ExportData,
        media_dir: Path | str | None,
        options: ImportOptions,
        result: ImportResult,
    ) -> _MediaMaps:
        """Import media files from export.

        Args:
            export_data: Export data containing media metadata
            media_dir: Directory containing downloaded media files
            options: Import options
            result: Result object to update

        Returns:
            Destination media id / documentId mappings
        """
        media_maps = _MediaMaps(id_to_id={}, doc_to_doc={}, id_to_doc={})

        if not export_data.media:
            return media_maps

        if media_dir is None:
            logger.warning(
                "Media directory not specified - skipping media import. "
                "Media references in entities will not be updated."
            )
            return media_maps

        media_path = Path(media_dir)
        if not media_path.exists():
            result.add_error(f"Media directory not found: {media_dir}")
            return media_maps

        for exported_media in export_data.media:
            try:
                if options.dry_run:
                    result.media_imported += 1
                    continue

                # Check for existing media with same hash (if not overwriting)
                if not options.overwrite_media:
                    existing = self._find_media_by_hash(exported_media.hash)
                    if existing is not None:
                        dest_id, dest_doc = existing
                        self._record_media_mapping(media_maps, exported_media, dest_id, dest_doc)
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

                uploaded = MediaHandler.upload_media_file(self.client, file_path, exported_media)
                self._record_media_mapping(
                    media_maps, exported_media, uploaded.id, uploaded.document_id
                )
                result.media_imported += 1

            except Exception as e:
                result.add_warning(f"Failed to import media {exported_media.name}: {e}")
                result.media_skipped += 1

        logger.info(f"Imported {result.media_imported}/{len(export_data.media)} media files")
        return media_maps

    @staticmethod
    def _record_media_mapping(
        media_maps: _MediaMaps,
        exported_media: ExportedMediaFile,
        dest_id: int,
        dest_document_id: str | None,
    ) -> None:
        """Record numeric and documentId mappings for a dest media file."""
        media_maps.id_to_id[exported_media.id] = dest_id
        if dest_document_id:
            media_maps.id_to_doc[exported_media.id] = dest_document_id
            if exported_media.document_id:
                media_maps.doc_to_doc[exported_media.document_id] = dest_document_id

    def _load_schemas_from_export(self, export_data: ExportData) -> None:
        """Load schemas from export metadata into cache.

        Args:
            export_data: Export data containing schemas
        """
        # Load all schemas into cache
        for content_type, schema in export_data.metadata.schemas.items():
            self._schema_cache.cache_schema(content_type, schema)

        logger.info(f"Loaded {self._schema_cache.cache_size} schemas from export")

    def _find_media_by_hash(self, file_hash: str) -> tuple[int, str | None] | None:
        """Find existing media file by hash.

        Args:
            file_hash: File hash to search for

        Returns:
            ``(id, documentId)`` if found, None otherwise
        """
        try:
            from strapi_kit.models import FilterBuilder, StrapiQuery

            query = StrapiQuery().filter(FilterBuilder().eq("hash", file_hash))
            response = self.client.list_media(query)

            if response.data:
                found = response.data[0]
                if found.id is None:
                    return None
                return found.id, found.document_id
        except Exception:  # noqa: BLE001, S110 - Intentionally ignore lookup failures
            pass
        return None

    def _resolve_relations_with_schema(
        self,
        relations: dict[str, list[int | str]],
        schema: ContentTypeSchema,
        id_mapping: dict[str, dict[int, int]],
        doc_id_to_new_id: dict[str, dict[str, int]] | None = None,
        entity_data: dict[str, Any] | None = None,
    ) -> dict[str, list[int]]:
        """Resolve relation IDs using schema information.

        Uses content type schemas to determine relation targets, enabling
        proper ID mapping during import. Handles both numeric IDs and
        string documentIds (v5 format).

        Args:
            relations: Raw relations from export (field -> [old_ids])
            schema: Schema for the content type
            id_mapping: Full ID mapping (content_type -> {old_id: new_id})
            doc_id_to_new_id: Optional document_id mapping for v5 string IDs
                (content_type -> {old_document_id: new_id})

        Returns:
            Resolved relations with new IDs
        """
        resolved: dict[str, list[int]] = {}

        for field_name, old_ids in relations.items():
            # Get target content type from schema (including nested paths)
            target_content_type = RelationResolver.target_for_field_path(
                schema, field_name, self._schema_cache, entity_data
            )
            if not target_content_type:
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
            target_doc_mapping = (
                doc_id_to_new_id.get(target_content_type, {}) if doc_id_to_new_id else {}
            )

            # Resolve old IDs to new IDs (supports both int and str IDs)
            new_ids = []
            for old_id in old_ids:
                if isinstance(old_id, int) and old_id in target_mapping:
                    new_ids.append(target_mapping[old_id])
                elif isinstance(old_id, str) and old_id in target_doc_mapping:
                    # V5 string documentId - look up in doc_id mapping
                    new_ids.append(target_doc_mapping[old_id])
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

    def _apply_entity_relations(
        self,
        entity: Any,
        schema: ContentTypeSchema,
        endpoint: str,
        id_mapping: dict[str, dict[int, int]],
        doc_id_mapping: dict[str, dict[int, str]],
        doc_id_to_new_id: dict[str, dict[str, int]],
        doc_id_to_new_document_id: dict[str, dict[str, str]],
    ) -> tuple[bool, list[str]]:
        """Write resolved relations.

        Returns:
            Tuple of (whether an update was sent, nested paths that could not
            be written).
        """
        skipped: list[str] = []
        write_query = self._write_query(entity)
        resolved_docs = self._resolve_relation_document_ids(
            entity.relations,
            schema,
            id_mapping,
            doc_id_mapping,
            doc_id_to_new_id,
            doc_id_to_new_document_id,
            entity.data,
        )
        payload = RelationResolver.build_v5_relation_payload(
            resolved_docs,
            schema,
            self._schema_cache,
            entity_data=entity.data,
            skipped=skipped,
        )
        new_document_id = doc_id_mapping.get(entity.content_type, {}).get(entity.id)
        if payload and new_document_id:
            self.client.update(endpoint, payload, document_id=new_document_id, query=write_query)
            return True, skipped

        resolved_nums = self._resolve_relations_with_schema(
            entity.relations,
            schema,
            id_mapping,
            doc_id_to_new_id,
            entity.data,
        )
        new_id = id_mapping.get(entity.content_type, {}).get(entity.id)
        if resolved_nums and new_id is not None:
            numeric_payload = RelationResolver.build_nested_numeric_payload(
                resolved_nums,
                schema,
                self._schema_cache,
                entity_data=entity.data,
                skipped=skipped,
            )
            if numeric_payload:
                self.client.update(f"{endpoint}/{new_id}", numeric_payload, query=write_query)
                return True, skipped

        return False, skipped

    def _resolve_relation_document_ids(
        self,
        relations: dict[str, list[int | str]],
        schema: ContentTypeSchema,
        id_mapping: dict[str, dict[int, int]],
        doc_id_mapping: dict[str, dict[int, str]],
        doc_id_to_new_id: dict[str, dict[str, int]],
        doc_id_to_new_document_id: dict[str, dict[str, str]],
        entity_data: dict[str, Any] | None = None,
    ) -> dict[str, list[str]]:
        """Resolve exported relation IDs to destination documentIds."""
        resolved: dict[str, list[str]] = {}
        for field_name, old_ids in relations.items():
            target = RelationResolver.target_for_field_path(
                schema, field_name, self._schema_cache, entity_data
            )
            if not target:
                logger.warning(f"Field {field_name} is not a relation. Skipping.")
                continue
            new_docs: list[str] = []
            for old_id in old_ids:
                new_doc: str | None = None
                if isinstance(old_id, str):
                    new_doc = doc_id_to_new_document_id.get(target, {}).get(old_id)
                    if new_doc is None:
                        new_num = doc_id_to_new_id.get(target, {}).get(old_id)
                        if new_num is not None:
                            for old_num, mapped in id_mapping.get(target, {}).items():
                                if mapped == new_num:
                                    new_doc = doc_id_mapping.get(target, {}).get(old_num)
                                    break
                else:
                    new_doc = doc_id_mapping.get(target, {}).get(old_id)
                if new_doc:
                    new_docs.append(new_doc)
                else:
                    logger.warning(f"Could not resolve {target} ID {old_id} for field {field_name}")
            if new_docs or len(old_ids) == 0:
                resolved[field_name] = new_docs
        return resolved

    def _get_endpoint(self, uid: str) -> str:
        """Return the REST collection id from the cached schema ``pluralName``."""
        if not self._schema_cache.has_schema(uid):
            raise ImportExportError(
                f"Schema with pluralName is required for {uid}",
                details={"uid": uid},
            )
        schema = self._schema_cache.get_schema(uid)
        try:
            return collection_endpoint(schema)
        except ValidationError as e:
            raise ImportExportError(
                f"Content type {uid} has no pluralName",
                details={"uid": uid},
            ) from e

    def import_from_jsonl(
        self,
        jsonl_path: str | Path,
        options: ImportOptions | None = None,
        media_dir: Path | str | None = None,
    ) -> ImportResult:
        """Import data from JSONL file with two-pass streaming.

        This method uses two-pass streaming for true O(1) memory usage:
        - Pass 1: Create, localize, skip, or update each row; store ID mappings
        - Pass 2: Re-read file to resolve relations using ID mappings

        Memory profile: O(entity_count x 2 ints) for ID mappings only,
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
        fail_conflicts: list[str] = []
        fail_conflict_keys: set[tuple[str, int]] = set()

        try:
            # ============================================================
            # Pass 1: Read metadata, import media, create entities
            # Store only ID mappings (O(entity_count x 2 ints))
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
                # Use separate reader to avoid consuming entity stream (Issue #30)
                media_maps = _MediaMaps(id_to_id={}, doc_to_doc={}, id_to_doc={})
                if options.import_media and media_dir:
                    if options.progress_callback:
                        options.progress_callback(10, 100, "Importing media files")

                    # Read media manifest with separate reader to preserve entity stream
                    with JSONLImportReader(jsonl_path) as media_reader:
                        media_reader.read_metadata()  # Skip metadata
                        media_files = media_reader.read_media_manifest()

                    if media_files:
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
                                    existing = self._find_media_by_hash(media.hash)
                                    if existing is not None:
                                        dest_id, dest_doc = existing
                                        self._record_media_mapping(
                                            media_maps, media, dest_id, dest_doc
                                        )
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
                                    uploaded = MediaHandler.upload_media_file(
                                        self.client, local_path, media
                                    )
                                    self._record_media_mapping(
                                        media_maps,
                                        media,
                                        uploaded.id,
                                        uploaded.document_id,
                                    )
                                    result.media_imported += 1
                                else:
                                    result.add_warning(f"Media file not found: {local_path}")
                                    result.media_skipped += 1
                            except StrapiError as e:
                                result.add_error(f"Failed to import media {media.id}: {e}")
                                result.media_skipped += 1

                # Step 3: Create entities - streaming with ID mapping only
                if options.progress_callback:
                    options.progress_callback(30, 100, "Creating entities (pass 1)")

                # Store only ID mappings: old_id -> new_id (O(entity_count x 2 ints))
                id_mappings: dict[str, dict[int, int]] = {}
                # Store document_id mappings for v5 endpoint updates
                doc_id_mappings: dict[str, dict[int, str]] = {}
                # Store reverse document_id mapping for v5 string relation resolution
                doc_id_to_new_id_mappings: dict[str, dict[str, int]] = {}
                doc_id_to_new_document_id_mappings: dict[str, dict[str, str]] = {}
                pending_publish: list[tuple[str, Any, str]] = []

                for entity in reader.iter_entities():
                    # Filter by content types if specified
                    if options.content_types and entity.content_type not in options.content_types:
                        continue

                    content_type = entity.content_type
                    if content_type not in id_mappings:
                        id_mappings[content_type] = {}
                        doc_id_mappings[content_type] = {}
                        doc_id_to_new_id_mappings[content_type] = {}
                        doc_id_to_new_document_id_mappings[content_type] = {}

                    try:
                        # Update media references
                        entity_data = entity.data
                        if media_maps.id_to_id or media_maps.doc_to_doc:
                            entity_data = MediaHandler.update_media_references(
                                entity.data,
                                media_maps.id_to_id,
                                media_maps.doc_to_doc,
                                media_maps.id_to_doc,
                            )

                        if options.dry_run:
                            result.entities_imported += 1
                            continue

                        self._import_one_entity(
                            entity,
                            endpoint=self._get_endpoint(content_type),
                            content_type=content_type,
                            entity_data=entity_data,
                            options=options,
                            pending_publish=pending_publish,
                            id_mapping=id_mappings,
                            doc_id_mapping=doc_id_mappings,
                            doc_id_to_new_id=doc_id_to_new_id_mappings,
                            doc_id_to_new_document_id=doc_id_to_new_document_id_mappings,
                            result=result,
                            fail_conflicts=fail_conflicts,
                            fail_conflict_keys=fail_conflict_keys,
                        )

                    except ImportExportError:
                        raise
                    except StrapiError as e:
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
                        if (entity.content_type, entity.id) in fail_conflict_keys:
                            continue

                        content_type = entity.content_type
                        endpoint = self._get_endpoint(content_type)

                        new_id = id_mappings.get(content_type, {}).get(entity.id)
                        if new_id is None:
                            continue

                        # Get schema from cache
                        try:
                            schema = self._schema_cache.get_schema(content_type)
                        except Exception as e:
                            result.add_error(
                                "Failed to load schema for "
                                f"{content_type} while importing relations: {e}"
                            )
                            continue

                        try:
                            applied, skipped = self._apply_entity_relations(
                                entity,
                                schema,
                                endpoint,
                                id_mappings,
                                doc_id_mappings,
                                doc_id_to_new_id_mappings,
                                doc_id_to_new_document_id_mappings,
                            )
                            if skipped:
                                result.add_error(
                                    "Skipped nested relations for "
                                    f"{content_type} {entity.id}: {', '.join(skipped)}"
                                )
                            if applied:
                                result.relations_imported += 1
                            elif entity.relations:
                                result.add_error(
                                    f"Could not write relations for {content_type} {entity.id}"
                                )
                        except StrapiError as e:
                            result.add_error(
                                f"Failed to import relations for {content_type} {entity.id}: {e}"
                            )

            self._publish_pending(pending_publish, options, result)

            if options.progress_callback:
                options.progress_callback(100, 100, "Import complete")

            # Copy local mappings to result for caller access
            result.id_mapping = id_mappings
            result.doc_id_mapping = doc_id_mappings
            result.doc_id_to_new_id = doc_id_to_new_id_mappings
            result.doc_id_to_new_document_id = doc_id_to_new_document_id_mappings

            self._raise_fail_conflicts(fail_conflicts, result)

            result.success = result.entities_failed == 0 and not result.errors
            return result

        except ImportExportError:
            raise
        except Exception as e:
            result.add_error(f"JSONL import failed: {e}")
            raise ImportExportError(f"JSONL import failed: {e}") from e
