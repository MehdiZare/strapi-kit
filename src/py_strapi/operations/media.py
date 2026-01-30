"""Media operations utilities for py-strapi.

This module provides shared utility functions for media upload, download,
and response normalization across sync and async clients.
"""

import json
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlparse

from py_strapi.models.response.media import MediaFile


def build_upload_payload(
    file_path: str | Path,
    ref: str | None = None,
    ref_id: str | int | None = None,
    field: str | None = None,
    folder: str | None = None,
    alternative_text: str | None = None,
    caption: str | None = None,
) -> dict[str, Any]:
    """Build multipart form data payload for file upload.

    Args:
        file_path: Path to file to upload
        ref: Reference model name (e.g., "api::article.article")
        ref_id: Reference document ID (numeric or string)
        field: Field name in reference model
        folder: Folder ID for organization
        alternative_text: Alt text for images
        caption: Caption text

    Returns:
        Dictionary with 'files' key and optional 'data' key for metadata

    Raises:
        FileNotFoundError: If file doesn't exist

    Example:
        >>> payload = build_upload_payload(
        ...     "image.jpg",
        ...     ref="api::article.article",
        ...     ref_id="123",
        ...     alternative_text="Hero image"
        ... )
        >>> # Returns: {"files": <file>, "data": {...}}
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

    # Build form data
    payload: dict[str, Any] = {
        "files": ("file", open(path, "rb"), None),  # Let httpx detect MIME type
    }

    # Add optional reference fields
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

    if data:
        payload["data"] = data

    return payload


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
