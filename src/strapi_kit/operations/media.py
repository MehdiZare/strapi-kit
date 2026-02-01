"""Media operations utilities for strapi-kit.

This module provides shared utility functions for media upload, download,
and response normalization across sync and async clients.
"""

import json
from pathlib import Path
from typing import IO, Any, Literal
from urllib.parse import urljoin, urlparse

from strapi_kit.models.response.media import MediaFile


class UploadPayload:
    """Container for upload payload with proper file handle management.

    This class ensures file handles are properly closed after upload operations,
    preventing resource leaks in batch operations or error scenarios.

    Usage:
        Use as a context manager to ensure proper cleanup:

        >>> with build_upload_payload("image.jpg") as payload:
        ...     files = {"files": payload.files_tuple}
        ...     data = payload.data
        ...     # Make HTTP request
    """

    def __init__(
        self,
        file_path: Path,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Initialize upload payload.

        Args:
            file_path: Path to the file to upload
            data: Optional metadata dictionary
        """
        self._file_path = file_path
        self._data = data
        self._file_handle: IO[bytes] | None = None

    @property
    def files_tuple(self) -> tuple[str, IO[bytes], None]:
        """Get the files tuple for httpx multipart upload.

        Returns:
            Tuple of (filename, file_handle, content_type)
            Content type is None to let httpx auto-detect MIME type.

        Raises:
            RuntimeError: If accessed outside of context manager
        """
        if self._file_handle is None:
            raise RuntimeError("UploadPayload must be used as a context manager")
        return ("file", self._file_handle, None)

    @property
    def data(self) -> dict[str, Any] | None:
        """Get the metadata dictionary."""
        return self._data

    def __enter__(self) -> "UploadPayload":
        """Open file handle on context entry."""
        self._file_handle = open(self._file_path, "rb")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close file handle on context exit."""
        if self._file_handle is not None:
            self._file_handle.close()
            self._file_handle = None


def build_upload_payload(
    file_path: str | Path,
    ref: str | None = None,
    ref_id: str | int | None = None,
    field: str | None = None,
    folder: str | None = None,
    alternative_text: str | None = None,
    caption: str | None = None,
) -> UploadPayload:
    """Build multipart form data payload for file upload.

    Returns an UploadPayload context manager that properly handles file
    lifecycle to prevent resource leaks.

    Args:
        file_path: Path to file to upload
        ref: Reference model name (e.g., "api::article.article")
        ref_id: Reference document ID (numeric or string)
        field: Field name in reference model
        folder: Folder ID for organization
        alternative_text: Alt text for images
        caption: Caption text

    Returns:
        UploadPayload context manager with file handle management

    Raises:
        FileNotFoundError: If file doesn't exist

    Example:
        >>> with build_upload_payload(
        ...     "image.jpg",
        ...     ref="api::article.article",
        ...     ref_id="123",
        ...     alternative_text="Hero image"
        ... ) as payload:
        ...     # Use payload.files_tuple and payload.data for upload
        ...     pass
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Build metadata dict (fileInfo in Strapi API)
    file_info: dict[str, Any] = {}
    if alternative_text is not None:
        file_info["alternativeText"] = alternative_text
    if caption is not None:
        file_info["caption"] = caption

    # Build form data metadata
    data: dict[str, Any] = {}
    if ref is not None:
        data["ref"] = ref
    if ref_id is not None:
        data["refId"] = str(ref_id)
    if field is not None:
        data["field"] = field
    if folder is not None:
        data["folder"] = folder
    if file_info:
        # httpx multipart requires JSON string for nested objects
        data["fileInfo"] = json.dumps(file_info)

    return UploadPayload(path, data if data else None)


def normalize_media_response(
    response_data: dict[str, Any],
    api_version: Literal["v4", "v5"],
) -> MediaFile:
    """Normalize v4/v5 media response to MediaFile model.

    Handles both nested attributes (v4) and flattened (v5) response structures.

    Args:
        response_data: Raw API response data
        api_version: Detected API version ("v4" or "v5")

    Returns:
        Validated MediaFile instance

    Example:
        >>> # v5 response (flattened)
        >>> v5_data = {
        ...     "id": 1,
        ...     "documentId": "abc123",
        ...     "name": "image.jpg",
        ...     "url": "/uploads/image.jpg"
        ... }
        >>> media = normalize_media_response(v5_data, "v5")

        >>> # v4 response (nested attributes)
        >>> v4_data = {
        ...     "id": 1,
        ...     "attributes": {
        ...         "name": "image.jpg",
        ...         "url": "/uploads/image.jpg"
        ...     }
        ... }
        >>> media = normalize_media_response(v4_data, "v4")
    """
    if api_version == "v4":
        # v4: nested structure with id at top level, rest in attributes
        if "attributes" in response_data:
            # Flatten attributes to top level
            flattened = {"id": response_data["id"], **response_data["attributes"]}
            return MediaFile.model_validate(flattened)
        else:
            # Already flattened or invalid
            return MediaFile.model_validate(response_data)
    else:
        # v5: already flattened with documentId
        return MediaFile.model_validate(response_data)


def build_media_download_url(base_url: str, media_url: str) -> str:
    """Construct full URL for media download.

    Handles both relative paths (/uploads/...) and absolute URLs.

    Args:
        base_url: Strapi instance base URL (e.g., "http://localhost:1337")
        media_url: Media URL from API response (relative or absolute)

    Returns:
        Full absolute URL for download

    Example:
        >>> build_media_download_url(
        ...     "http://localhost:1337",
        ...     "/uploads/image.jpg"
        ... )
        'http://localhost:1337/uploads/image.jpg'

        >>> build_media_download_url(
        ...     "http://localhost:1337",
        ...     "https://cdn.example.com/image.jpg"
        ... )
        'https://cdn.example.com/image.jpg'
    """
    # Check if URL is already absolute
    parsed = urlparse(media_url)
    if parsed.scheme:  # Has http:// or https://
        return media_url

    # Relative URL - join with base_url
    # Ensure base_url doesn't have trailing slash for proper joining
    base = base_url.rstrip("/")
    return urljoin(base, media_url)
