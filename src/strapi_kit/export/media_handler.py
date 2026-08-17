"""Media file handling for export and import operations.

This module handles downloading media files during export and
uploading them during import.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, Any

from strapi_kit.models.export_format import ExportedMediaFile
from strapi_kit.models.request.media_write import MediaWriteId, media_write
from strapi_kit.models.response.media import MediaFile
from strapi_kit.models.schema import ContentTypeSchema, FieldType

if TYPE_CHECKING:
    from strapi_kit.cache.schema_cache import InMemorySchemaCache
    from strapi_kit.client.sync_client import SyncClient

logger = logging.getLogger(__name__)


class MediaHandler:
    """Handles media file operations for export/import.

    This class provides utilities for:
    - Extracting media references from entity data
    - Downloading media files during export
    - Uploading media files during import
    - Updating entity references with new media IDs
    """

    @staticmethod
    def _is_media(item: dict[str, Any]) -> bool:
        """Check if item is media (v4 or v5 format).

        v4 format: {"id": 1, "attributes": {"mime": "image/jpeg", ...}}
        v5 format: {"id": 1, "mime": "image/jpeg", ...}

        Args:
            item: Dictionary to check

        Returns:
            True if item is a media object
        """
        # v5 format: mime at top level
        if "mime" in item:
            return True
        # v4 format: mime nested in attributes
        if "attributes" in item and isinstance(item["attributes"], dict):
            return "mime" in item["attributes"]
        return False

    @staticmethod
    def _is_media_data_wrapper(value: Any) -> bool:
        """True for v4 ``{"data": media|null|[media, ...]}`` wrappers."""
        if value is None:
            return True
        if isinstance(value, dict):
            return MediaHandler._is_media(value)
        if isinstance(value, list):
            return not value or all(
                isinstance(item, dict) and MediaHandler._is_media(item) for item in value
            )
        return False

    @staticmethod
    def _get_media_id(item: dict[str, Any]) -> int | None:
        """Extract ID from media item (v4 or v5 format).

        Args:
            item: Media dictionary

        Returns:
            Media ID or None if not found
        """
        return item.get("id")

    @staticmethod
    def _sanitize_filename(name: str, max_length: int = 200) -> str:
        """Sanitize filename to prevent path traversal and other issues.

        Removes or replaces dangerous characters and path components that
        could be used for path traversal attacks.

        Args:
            name: Original filename from media
            max_length: Maximum length for the filename

        Returns:
            Sanitized filename safe for filesystem use

        Examples:
            >>> MediaHandler._sanitize_filename("../../../etc/passwd")
            '______etc_passwd'
            >>> MediaHandler._sanitize_filename("image<script>.jpg")
            'image_script_.jpg'
            >>> MediaHandler._sanitize_filename("")
            'unnamed'
        """
        if not name or not name.strip():
            return "unnamed"

        # Normalize unicode characters
        name = unicodedata.normalize("NFKC", name)

        # Remove null bytes
        name = name.replace("\x00", "")

        # Replace path traversal sequences first
        name = name.replace("..", "_")

        # Replace dangerous characters: / \ : * ? " < > |
        name = re.sub(r'[/\\:*?"<>|]', "_", name)

        # Remove leading/trailing dots and spaces (problematic on Windows)
        name = name.strip(". ")

        # Handle empty result after stripping
        if not name:
            return "unnamed"

        # Truncate while preserving extension
        if len(name) > max_length:
            parts = name.rsplit(".", 1)
            if len(parts) == 2 and len(parts[1]) <= 10:
                # Has reasonable extension, preserve it
                ext_with_dot = "." + parts[1]
                base_max = max_length - len(ext_with_dot)
                name = parts[0][:base_max] + ext_with_dot
            else:
                name = name[:max_length]

        return name or "unnamed"

    @staticmethod
    def extract_media_references(data: dict[str, Any]) -> list[int]:
        """Extract media file IDs from entity data.

        Searches for media references in various Strapi formats:
        - v4 wrapper: ``{"data": {"id": 1, "attributes": {"mime": ...}}}``
        - Flat v5 file: ``{"id": 1, "mime": "image/jpeg", "url": "..."}``
        - Lists of either shape (including ``{"data": [...]}``)

        Args:
            data: Entity attributes dictionary

        Returns:
            List of media file IDs found in the data

        Example:
            >>> data = {
            ...     "title": "Article",
            ...     "cover": {"id": 5, "mime": "image/jpeg", "url": "/uploads/a.jpg"},
            ...     "gallery": {"data": [
            ...         {"id": 10, "mime": "image/jpeg"},
            ...         {"id": 11, "mime": "image/png"},
            ...     ]},
            ... }
            >>> MediaHandler.extract_media_references(data)
            [5, 10, 11]
        """
        media_ids: list[int] = []
        for field_value in data.values():
            MediaHandler._collect_media_ids(field_value, media_ids)
        return media_ids

    @staticmethod
    def _collect_media_ids(value: Any, media_ids: list[int]) -> None:
        """Collect media IDs from a field value (flat v5, v4 wrapper, or list)."""
        if isinstance(value, dict):
            if MediaHandler._is_media(value):
                media_id = MediaHandler._get_media_id(value)
                if media_id is not None:
                    media_ids.append(media_id)
                return
            for nested in value.values():
                MediaHandler._collect_media_ids(nested, media_ids)
            return
        if isinstance(value, list):
            for item in value:
                MediaHandler._collect_media_ids(item, media_ids)

    @staticmethod
    def download_media_file(
        client: SyncClient,
        media: MediaFile,
        output_dir: Path,
    ) -> Path:
        """Download a media file to local directory.

        Args:
            client: Strapi client
            media: Media file metadata
            output_dir: Directory to save file to

        Returns:
            Path where file was saved

        Example:
            >>> output_dir = Path("export/media")
            >>> local_path = MediaHandler.download_media_file(
            ...     client, media, output_dir
            ... )
        """
        # Create output directory if needed
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate safe filename with sanitization
        safe_name = MediaHandler._sanitize_filename(media.name)
        filename = f"{media.id}_{safe_name}"
        output_path = output_dir / filename

        # Download file
        client.download_file(media.url, save_path=str(output_path))

        logger.info(f"Downloaded media file: {filename}")
        return output_path

    @staticmethod
    def create_media_export(media: MediaFile, local_path: Path) -> ExportedMediaFile:
        """Create export metadata for a media file.

        Args:
            media: Media file metadata from Strapi
            local_path: Local path where file is saved

        Returns:
            ExportedMediaFile with metadata
        """
        # MediaFile.size is in KB, ExportedMediaFile.size expects bytes
        size_in_bytes = int(media.size * 1024) if media.size else 0
        return ExportedMediaFile(
            id=media.id,
            document_id=media.document_id,
            url=media.url,
            name=media.name,
            mime=media.mime,
            size=size_in_bytes,
            hash=media.hash or "",
            local_path=str(local_path.name),
        )

    @staticmethod
    def upload_media_file(
        client: SyncClient,
        file_path: Path,
        original_metadata: ExportedMediaFile,
    ) -> MediaFile:
        """Upload a media file to Strapi.

        Args:
            client: Strapi client
            file_path: Path to local file
            original_metadata: Original media metadata from export

        Returns:
            Uploaded media file metadata with new ID

        Example:
            >>> file_path = Path("export/media/5_image.jpg")
            >>> uploaded = MediaHandler.upload_media_file(
            ...     client, file_path, exported_media
            ... )
            >>> print(f"Old ID: {exported_media.id}, New ID: {uploaded.id}")
        """
        # Upload file with original metadata
        uploaded = client.upload_file(
            str(file_path),
            alternative_text=original_metadata.name,
            caption=original_metadata.name,
        )

        logger.info(
            f"Uploaded media file: {original_metadata.name} "
            f"(old ID: {original_metadata.id}, new ID: {uploaded.id})"
        )
        return uploaded

    @staticmethod
    def update_media_references(
        data: dict[str, Any],
        media_id_mapping: dict[int, int],
        media_doc_mapping: dict[str, str] | None = None,
        id_to_dest_doc: dict[int, str] | None = None,
        *,
        schema: ContentTypeSchema | None = None,
        schema_cache: InMemorySchemaCache | None = None,
    ) -> dict[str, Any]:
        """Convert media populate objects to dest write ids.

        Prefers destination ``documentId`` when the upload (or hash match)
        recorded one. Falls back to the remapped numeric id. Unmapped
        one-side files become ``None``; unmapped many-side entries are
        omitted. Source ``mime`` / ``url`` / ``documentId`` blobs are
        not written.

        When ``schema`` is provided, remaps ``FieldType.MEDIA`` fields and
        media nested in resolved components / dynamic zones. Unknown
        fields and unresolved component / dynamic-zone schemas fall back
        to the ``mime`` heuristic. Resolved ``FieldType.RELATION`` values
        are left unchanged. Without a schema the heuristic is used for
        every field.

        Args:
            data: Entity attributes dictionary
            media_id_mapping: Mapping of old media IDs to new IDs
            media_doc_mapping: Optional old file documentId → dest documentId
            id_to_dest_doc: Optional old numeric id → dest documentId
            schema: Optional content-type schema for a typed walk
            schema_cache: Component cache used with ``schema``

        Returns:
            Updated data with media fields as dest ids
        """
        docs = media_doc_mapping or {}
        id_docs = id_to_dest_doc or {}
        if schema is not None:
            return MediaHandler._remap_with_schema(
                data, schema, schema_cache, media_id_mapping, docs, id_docs
            )
        updated_data = {}
        for field_name, field_value in data.items():
            updated_data[field_name] = MediaHandler._remap_media_value(
                field_value, media_id_mapping, docs, id_docs
            )
        return updated_data

    @staticmethod
    def _remap_with_schema(
        data: dict[str, Any],
        schema: ContentTypeSchema,
        schema_cache: InMemorySchemaCache | None,
        media_id_mapping: dict[int, int],
        media_doc_mapping: dict[str, str],
        id_to_dest_doc: dict[int, str],
    ) -> dict[str, Any]:
        """Remap schema-declared media fields; heuristic if schema is missing."""
        updated: dict[str, Any] = {}
        for field_name, field_value in data.items():
            field_schema = schema.fields.get(field_name)
            if field_schema is None:
                updated[field_name] = MediaHandler._remap_media_value(
                    field_value, media_id_mapping, media_doc_mapping, id_to_dest_doc
                )
                continue
            if field_schema.type == FieldType.MEDIA:
                updated[field_name] = MediaHandler._media_field_to_write(
                    field_value, media_id_mapping, media_doc_mapping, id_to_dest_doc
                )
                continue
            if field_schema.type == FieldType.COMPONENT:
                component_schema = (
                    MediaHandler._component_schema(schema_cache, field_schema.component)
                    if field_schema.component
                    else None
                )
                if component_schema is None:
                    updated[field_name] = MediaHandler._remap_media_value(
                        field_value, media_id_mapping, media_doc_mapping, id_to_dest_doc
                    )
                elif isinstance(field_value, list):
                    updated[field_name] = [
                        MediaHandler._remap_with_schema(
                            item,
                            component_schema,
                            schema_cache,
                            media_id_mapping,
                            media_doc_mapping,
                            id_to_dest_doc,
                        )
                        if isinstance(item, dict)
                        else item
                        for item in field_value
                    ]
                elif isinstance(field_value, dict):
                    updated[field_name] = MediaHandler._remap_with_schema(
                        field_value,
                        component_schema,
                        schema_cache,
                        media_id_mapping,
                        media_doc_mapping,
                        id_to_dest_doc,
                    )
                else:
                    updated[field_name] = field_value
                continue
            if field_schema.type == FieldType.DYNAMIC_ZONE and isinstance(field_value, list):
                remapped_zone: list[Any] = []
                for item in field_value:
                    if not isinstance(item, dict):
                        remapped_zone.append(item)
                        continue
                    uid = item.get("__component")
                    dz_schema = (
                        MediaHandler._component_schema(schema_cache, uid)
                        if isinstance(uid, str)
                        else None
                    )
                    if dz_schema is None:
                        remapped_zone.append(
                            MediaHandler._remap_media_value(
                                item, media_id_mapping, media_doc_mapping, id_to_dest_doc
                            )
                        )
                        continue
                    remapped_item = MediaHandler._remap_with_schema(
                        item,
                        dz_schema,
                        schema_cache,
                        media_id_mapping,
                        media_doc_mapping,
                        id_to_dest_doc,
                    )
                    remapped_item["__component"] = uid
                    remapped_zone.append(remapped_item)
                updated[field_name] = remapped_zone
                continue
            updated[field_name] = field_value
        return updated

    @staticmethod
    def _component_schema(
        schema_cache: InMemorySchemaCache | None, component_uid: str
    ) -> ContentTypeSchema | None:
        if schema_cache is None:
            return None
        try:
            return schema_cache.get_component_schema(component_uid)
        except Exception:  # noqa: BLE001 - missing dest component is not a media error
            return None

    @staticmethod
    def _media_field_to_write(
        value: Any,
        media_id_mapping: dict[int, int],
        media_doc_mapping: dict[str, str],
        id_to_dest_doc: dict[int, str],
    ) -> Any:
        """Convert one MEDIA field value to a dest write id or list."""
        if value is None:
            return None
        if isinstance(value, dict):
            if "data" in value and "documentId" not in value and "document_id" not in value:
                return MediaHandler._media_field_to_write(
                    value.get("data"), media_id_mapping, media_doc_mapping, id_to_dest_doc
                )
            dest = MediaHandler._dest_media_id(
                value, media_id_mapping, media_doc_mapping, id_to_dest_doc
            )
            return media_write(file_ids=[] if dest is None else [dest], multiple=False)
        if isinstance(value, list):
            dests: list[MediaWriteId] = []
            for item in value:
                remapped = MediaHandler._media_field_to_write(
                    item, media_id_mapping, media_doc_mapping, id_to_dest_doc
                )
                if remapped is None:
                    continue
                if isinstance(remapped, list):
                    dests.extend(remapped)
                elif isinstance(remapped, str) or (
                    isinstance(remapped, int) and not isinstance(remapped, bool)
                ):
                    dests.append(remapped)
            return media_write(file_ids=dests, multiple=True)
        return value

    @staticmethod
    def _dest_media_id(
        item: dict[str, Any],
        media_id_mapping: dict[int, int],
        media_doc_mapping: dict[str, str],
        id_to_dest_doc: dict[int, str],
    ) -> MediaWriteId | None:
        """Resolve a populate media object to a dest write id."""
        raw_doc = item.get("documentId", item.get("document_id"))
        if isinstance(raw_doc, str) and raw_doc.strip():
            source_doc = raw_doc.strip()
            if source_doc in media_doc_mapping:
                return media_doc_mapping[source_doc]
        old_id = MediaHandler._get_media_id(item)
        if old_id is not None:
            if old_id in id_to_dest_doc:
                return id_to_dest_doc[old_id]
            if old_id in media_id_mapping:
                return media_id_mapping[old_id]
        return None

    @staticmethod
    def _remap_media_value(
        value: Any,
        media_id_mapping: dict[int, int],
        media_doc_mapping: dict[str, str],
        id_to_dest_doc: dict[int, str],
    ) -> Any:
        """Replace media populate objects with dest write ids."""
        if isinstance(value, dict):
            if MediaHandler._is_media(value):
                dest = MediaHandler._dest_media_id(
                    value, media_id_mapping, media_doc_mapping, id_to_dest_doc
                )
                return media_write(file_ids=[] if dest is None else [dest], multiple=False)
            inner = value.get("data")
            if (
                "data" in value
                and "documentId" not in value
                and "document_id" not in value
                and MediaHandler._is_media_data_wrapper(inner)
            ):
                remapped = MediaHandler._remap_media_value(
                    inner, media_id_mapping, media_doc_mapping, id_to_dest_doc
                )
                # Unwrap v4 {"data": media} into a write value.
                return remapped
            return {
                key: MediaHandler._remap_media_value(
                    nested, media_id_mapping, media_doc_mapping, id_to_dest_doc
                )
                for key, nested in value.items()
            }
        if isinstance(value, list):
            if value and all(
                isinstance(item, dict) and MediaHandler._is_media(item) for item in value
            ):
                dests: list[MediaWriteId] = []
                for item in value:
                    dest = MediaHandler._dest_media_id(
                        item, media_id_mapping, media_doc_mapping, id_to_dest_doc
                    )
                    if dest is not None:
                        dests.append(dest)
                return media_write(file_ids=dests, multiple=True)
            return [
                MediaHandler._remap_media_value(
                    item, media_id_mapping, media_doc_mapping, id_to_dest_doc
                )
                for item in value
            ]
        return value
