"""Media file handling for export and import operations.

This module handles downloading media files during export and
uploading them during import.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from py_strapi.models.export_format import ExportedMediaFile
from py_strapi.models.response.media import MediaFile

if TYPE_CHECKING:
    from py_strapi.client.sync_client import SyncClient

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
                elif isinstance(media_data, dict) and "mime" in media_data:
                    # Single media file (has mime type)
                    if "id" in media_data:
                        media_ids.append(media_data["id"])
                elif isinstance(media_data, list):
                    # Multiple media files
                    for item in media_data:
                        if isinstance(item, dict) and "mime" in item and "id" in item:
                            media_ids.append(item["id"])

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

        # Generate safe filename
        filename = f"{media.id}_{media.name}"
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
                elif isinstance(media_data, dict) and "mime" in media_data:
                    # Single media file
                    old_id = media_data.get("id")
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
                        if isinstance(item, dict) and "mime" in item:
                            old_id = item.get("id")
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
