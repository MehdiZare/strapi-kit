"""Media file handling for export and import operations.

This module handles downloading media files during export and
uploading them during import.
"""

import logging
import re
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING, Any

from strapi_kit.models.export_format import ExportedMediaFile
from strapi_kit.models.response.media import MediaFile

if TYPE_CHECKING:
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
        - Single media: {"data": {"id": 1}}
        - Multiple media: {"data": [{"id": 1}, {"id": 2}]}

        Args:
            data: Entity attributes dictionary

        Returns:
            List of media file IDs found in the data

        Example:
            >>> data = {
            ...     "title": "Article",
            ...     "cover": {"data": {"id": 5}},
            ...     "gallery": {"data": [{"id": 10}, {"id": 11}]}
            ... }
            >>> MediaHandler.extract_media_references(data)
            [5, 10, 11]
        """
        media_ids: list[int] = []

        for field_value in data.values():
            if isinstance(field_value, dict) and "data" in field_value:
                media_data = field_value["data"]

                if media_data is None:
                    continue
                elif isinstance(media_data, dict) and MediaHandler._is_media(media_data):
                    # Single media file (v4 or v5 format)
                    media_id = MediaHandler._get_media_id(media_data)
                    if media_id is not None:
                        media_ids.append(media_id)
                elif isinstance(media_data, list):
                    # Multiple media files
                    for item in media_data:
                        if isinstance(item, dict) and MediaHandler._is_media(item):
                            media_id = MediaHandler._get_media_id(item)
                            if media_id is not None:
                                media_ids.append(media_id)

        return media_ids

    @staticmethod
    def download_media_file(
        client: "SyncClient",
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
            url=media.url,
            name=media.name,
            mime=media.mime,
            size=size_in_bytes,
            hash=media.hash or "",
            local_path=str(local_path.name),
        )

    @staticmethod
    def upload_media_file(
        client: "SyncClient",
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
    ) -> dict[str, Any]:
        """Update media IDs in entity data using mapping.

        Args:
            data: Entity attributes dictionary
            media_id_mapping: Mapping of old media IDs to new IDs

        Returns:
            Updated data with new media IDs

        Example:
            >>> data = {"cover": {"data": {"id": 5}}}
            >>> mapping = {5: 50}
            >>> updated = MediaHandler.update_media_references(data, mapping)
            >>> updated["cover"]["data"]["id"]
            50
        """
        updated_data = {}

        for field_name, field_value in data.items():
            if isinstance(field_value, dict) and "data" in field_value:
                media_data = field_value["data"]

                if media_data is None:
                    updated_data[field_name] = field_value
                elif isinstance(media_data, dict) and MediaHandler._is_media(media_data):
                    # Single media file (v4 or v5 format)
                    old_id = MediaHandler._get_media_id(media_data)
                    if old_id and old_id in media_id_mapping:
                        # Update with new ID
                        updated_media = media_data.copy()
                        updated_media["id"] = media_id_mapping[old_id]
                        updated_data[field_name] = {"data": updated_media}
                    else:
                        updated_data[field_name] = field_value
                elif isinstance(media_data, list):
                    # Multiple media files
                    updated_list = []
                    for item in media_data:
                        if isinstance(item, dict) and MediaHandler._is_media(item):
                            old_id = MediaHandler._get_media_id(item)
                            if old_id and old_id in media_id_mapping:
                                updated_item = item.copy()
                                updated_item["id"] = media_id_mapping[old_id]
                                updated_list.append(updated_item)
                            else:
                                updated_list.append(item)
                        else:
                            updated_list.append(item)
                    updated_data[field_name] = {"data": updated_list}
                else:
                    updated_data[field_name] = field_value
            else:
                updated_data[field_name] = field_value

        return updated_data
