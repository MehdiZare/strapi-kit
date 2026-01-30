"""Synchronous HTTP client for Strapi API.

This module provides blocking I/O operations for simpler scripts
and applications that don't require concurrency.
"""

import logging
from pathlib import Path
from typing import Any

import httpx

from ..exceptions import (
    ConnectionError as StrapiConnectionError,
)
from ..exceptions import (
    MediaError,
    TimeoutError as StrapiTimeoutError,
)
from ..models.config import StrapiConfig
from ..models.request.query import StrapiQuery
from ..models.response.media import MediaFile
from ..models.response.normalized import NormalizedCollectionResponse, NormalizedSingleResponse
from ..operations.media import build_media_download_url, build_upload_payload
from ..protocols import AuthProvider, ConfigProvider, HTTPClient, ResponseParser
from .base import BaseClient

logger = logging.getLogger(__name__)


class SyncClient(BaseClient):
    """Synchronous HTTP client for Strapi API.

    This client uses blocking I/O and is suitable for:
    - Simple scripts and utilities
    - Applications that process one request at a time
    - Environments where async/await is not needed

    Example:
        ```python
        from py_strapi import SyncClient, StrapiConfig

        config = StrapiConfig(
            base_url="http://localhost:1337",
            api_token="your-token"
        )

        with SyncClient(config) as client:
            response = client.get("articles")
            print(response)
        ```
    """

    def __init__(
        self,
        config: ConfigProvider,
        http_client: HTTPClient | None = None,
        auth: AuthProvider | None = None,
        parser: ResponseParser | None = None,
    ) -> None:
        """Initialize the synchronous client with dependency injection.

        Args:
            config: Configuration provider (typically StrapiConfig)
            http_client: HTTP client (defaults to httpx.Client with pooling)
            auth: Authentication provider (passed to BaseClient)
            parser: Response parser (passed to BaseClient)
        """
        super().__init__(config, auth=auth, parser=parser)

        # Dependency injection with default factory
        self._client: HTTPClient | httpx.Client = (
            http_client or self._create_default_http_client()
        )
        self._owns_client = http_client is None

    def _create_default_http_client(self) -> httpx.Client:
        """Create default HTTP client with connection pooling.

        Returns:
            Configured httpx.Client instance
        """
        return httpx.Client(
            timeout=self.config.timeout,
            verify=self.config.verify_ssl,
            limits=httpx.Limits(
                max_connections=self.config.max_connections,
                max_keepalive_connections=self.config.max_connections,
            ),
        )

    def __enter__(self) -> "SyncClient":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - closes the client."""
        self.close()

    def close(self) -> None:
        """Close the HTTP client and release connections.

        Only closes the client if it was created by this instance
        (not injected from outside).
        """
        if self._owns_client:
            self._client.close()
        logger.info("Closed synchronous Strapi client")

    def request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request to the Strapi API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            params: URL query parameters
            json: JSON request body
            headers: Additional headers

        Returns:
            Response JSON data

        Raises:
            StrapiError: On API errors
            ConnectionError: On connection failures
            TimeoutError: On request timeout
        """
        url = self._build_url(endpoint)
        request_headers = self._get_headers(headers)

        logger.debug(f"{method} {url} params={params}")

        try:
            response = self._client.request(
                method=method,
                url=url,
                params=params,
                json=json,
                headers=request_headers,
            )

            # Handle error responses
            if not response.is_success:
                self._handle_error_response(response)

            # Parse and return JSON
            data: dict[str, Any] = response.json()

            # Detect API version from response
            if data and isinstance(data, dict):
                self._detect_api_version(data)

            logger.debug(f"Response: {response.status_code}")
            return data

        except httpx.ConnectError as e:
            raise StrapiConnectionError(f"Failed to connect to {self.base_url}: {e}") from e
        except httpx.TimeoutException as e:
            raise StrapiTimeoutError(
                f"Request timed out after {self.config.timeout}s: {e}"
            ) from e

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make a GET request.

        Args:
            endpoint: API endpoint path
            params: URL query parameters
            headers: Additional headers

        Returns:
            Response JSON data
        """
        return self.request("GET", endpoint, params=params, headers=headers)

    def post(
        self,
        endpoint: str,
        json: dict[str, Any],
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make a POST request.

        Args:
            endpoint: API endpoint path
            json: JSON request body
            params: URL query parameters
            headers: Additional headers

        Returns:
            Response JSON data
        """
        return self.request("POST", endpoint, params=params, json=json, headers=headers)

    def put(
        self,
        endpoint: str,
        json: dict[str, Any],
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make a PUT request.

        Args:
            endpoint: API endpoint path
            json: JSON request body
            params: URL query parameters
            headers: Additional headers

        Returns:
            Response JSON data
        """
        return self.request("PUT", endpoint, params=params, json=json, headers=headers)

    def delete(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make a DELETE request.

        Args:
            endpoint: API endpoint path
            params: URL query parameters
            headers: Additional headers

        Returns:
            Response JSON data
        """
        return self.request("DELETE", endpoint, params=params, headers=headers)

    # Typed methods for normalized responses

    def get_one(
        self,
        endpoint: str,
        query: StrapiQuery | None = None,
        headers: dict[str, str] | None = None,
    ) -> NormalizedSingleResponse:
        """Get a single entity with typed, normalized response.

        Args:
            endpoint: API endpoint path (e.g., "articles/1" or "articles/abc123")
            query: Optional query configuration (populate, fields, locale, etc.)
            headers: Additional headers

        Returns:
            Normalized single entity response

        Examples:
            >>> from py_strapi.models import StrapiQuery, Populate
            >>> query = (StrapiQuery()
            ...     .populate_fields(["author", "category"])
            ...     .select(["title", "content"]))
            >>> response = client.get_one("articles/1", query=query)
            >>> article = response.data
            >>> article.attributes["title"]
            'My Article'
        """
        params = query.to_query_params() if query else None
        raw_response = self.get(endpoint, params=params, headers=headers)
        return self._parse_single_response(raw_response)

    def get_many(
        self,
        endpoint: str,
        query: StrapiQuery | None = None,
        headers: dict[str, str] | None = None,
    ) -> NormalizedCollectionResponse:
        """Get multiple entities with typed, normalized response.

        Args:
            endpoint: API endpoint path (e.g., "articles")
            query: Optional query configuration (filters, sort, pagination, etc.)
            headers: Additional headers

        Returns:
            Normalized collection response

        Examples:
            >>> from py_strapi.models import StrapiQuery, FilterBuilder, SortDirection
            >>> query = (StrapiQuery()
            ...     .filter(FilterBuilder().eq("status", "published"))
            ...     .sort_by("publishedAt", SortDirection.DESC)
            ...     .paginate(page=1, page_size=25)
            ...     .populate_fields(["author"]))
            >>> response = client.get_many("articles", query=query)
            >>> for article in response.data:
            ...     print(article.attributes["title"])
        """
        params = query.to_query_params() if query else None
        raw_response = self.get(endpoint, params=params, headers=headers)
        return self._parse_collection_response(raw_response)

    def create(
        self,
        endpoint: str,
        data: dict[str, Any],
        query: StrapiQuery | None = None,
        headers: dict[str, str] | None = None,
    ) -> NormalizedSingleResponse:
        """Create a new entity with typed, normalized response.

        Args:
            endpoint: API endpoint path (e.g., "articles")
            data: Entity data to create (wrapped in {"data": {...}} automatically)
            query: Optional query configuration (populate, fields, etc.)
            headers: Additional headers

        Returns:
            Normalized single entity response

        Examples:
            >>> data = {"title": "New Article", "content": "Article body"}
            >>> response = client.create("articles", data)
            >>> created = response.data
            >>> created.id
            42
        """
        params = query.to_query_params() if query else None
        # Wrap data in Strapi format
        payload = {"data": data}
        raw_response = self.post(endpoint, json=payload, params=params, headers=headers)
        return self._parse_single_response(raw_response)

    def update(
        self,
        endpoint: str,
        data: dict[str, Any],
        query: StrapiQuery | None = None,
        headers: dict[str, str] | None = None,
    ) -> NormalizedSingleResponse:
        """Update an existing entity with typed, normalized response.

        Args:
            endpoint: API endpoint path (e.g., "articles/1" or "articles/abc123")
            data: Entity data to update (wrapped in {"data": {...}} automatically)
            query: Optional query configuration (populate, fields, etc.)
            headers: Additional headers

        Returns:
            Normalized single entity response

        Examples:
            >>> data = {"title": "Updated Title"}
            >>> response = client.update("articles/1", data)
            >>> updated = response.data
            >>> updated.attributes["title"]
            'Updated Title'
        """
        params = query.to_query_params() if query else None
        # Wrap data in Strapi format
        payload = {"data": data}
        raw_response = self.put(endpoint, json=payload, params=params, headers=headers)
        return self._parse_single_response(raw_response)

    def remove(
        self,
        endpoint: str,
        headers: dict[str, str] | None = None,
    ) -> NormalizedSingleResponse:
        """Delete an entity with typed, normalized response.

        Args:
            endpoint: API endpoint path (e.g., "articles/1" or "articles/abc123")
            headers: Additional headers

        Returns:
            Normalized single entity response (deleted entity)

        Examples:
            >>> response = client.remove("articles/1")
            >>> deleted = response.data
            >>> deleted.id
            1
        """
        raw_response = self.delete(endpoint, headers=headers)
        return self._parse_single_response(raw_response)

    # Media Operations

    def upload_file(
        self,
        file_path: str | Path,
        *,
        ref: str | None = None,
        ref_id: str | int | None = None,
        field: str | None = None,
        folder: str | None = None,
        alternative_text: str | None = None,
        caption: str | None = None,
    ) -> MediaFile:
        """Upload a single file to Strapi media library.

        Args:
            file_path: Path to file to upload
            ref: Reference model name (e.g., "api::article.article")
            ref_id: Reference document ID (numeric or string)
            field: Field name in reference model
            folder: Folder ID for organization
            alternative_text: Alt text for images
            caption: Caption text

        Returns:
            MediaFile with upload details

        Raises:
            MediaError: On upload failure
            FileNotFoundError: If file doesn't exist

        Examples:
            >>> # Simple upload
            >>> media = client.upload_file("image.jpg")
            >>> media.name
            'image.jpg'

            >>> # Upload with metadata
            >>> media = client.upload_file(
            ...     "hero.jpg",
            ...     alternative_text="Hero image",
            ...     caption="Main article image"
            ... )

            >>> # Upload and attach to entity
            >>> media = client.upload_file(
            ...     "cover.jpg",
            ...     ref="api::article.article",
            ...     ref_id="abc123",
            ...     field="cover"
            ... )
        """
        try:
            # Build multipart payload
            payload = build_upload_payload(
                file_path,
                ref=ref,
                ref_id=ref_id,
                field=field,
                folder=folder,
                alternative_text=alternative_text,
                caption=caption,
            )

            # Build URL and headers
            url = self._build_url("upload")
            headers = self._build_upload_headers()

            # Make request with multipart data
            response = self._client.post(
                url,
                files={"files": payload["files"]},
                data=payload.get("data"),
                headers=headers,
            )

            # Handle errors
            if not response.is_success:
                self._handle_error_response(response)

            # Parse response (upload returns single file object, not wrapped in data)
            response_json = response.json()
            # Upload endpoint returns array with single file
            if isinstance(response_json, list) and response_json:
                return self._parse_media_response(response_json[0])
            else:
                return self._parse_media_response(response_json)

        except FileNotFoundError:
            raise
        except Exception as e:
            raise MediaError(f"File upload failed: {e}") from e

    def upload_files(
        self,
        file_paths: list[str | Path],
        **kwargs: Any,
    ) -> list[MediaFile]:
        """Upload multiple files sequentially.

        Args:
            file_paths: List of file paths to upload
            **kwargs: Same metadata options as upload_file

        Returns:
            List of MediaFile objects

        Raises:
            MediaError: On any upload failure (partial uploads NOT rolled back)

        Examples:
            >>> files = ["image1.jpg", "image2.jpg", "image3.jpg"]
            >>> media_list = client.upload_files(files)
            >>> len(media_list)
            3

            >>> # Upload with shared metadata
            >>> media_list = client.upload_files(
            ...     ["thumb1.jpg", "thumb2.jpg"],
            ...     folder="thumbnails"
            ... )
        """
        uploaded: list[MediaFile] = []

        for idx, file_path in enumerate(file_paths):
            try:
                media = self.upload_file(file_path, **kwargs)
                uploaded.append(media)
            except Exception as e:
                raise MediaError(
                    f"Batch upload failed at file {idx} ({file_path}): {e}. "
                    f"{len(uploaded)} files were uploaded successfully before failure."
                ) from e

        return uploaded

    def download_file(
        self,
        media_url: str,
        save_path: str | Path | None = None,
    ) -> bytes:
        """Download a media file from Strapi.

        Args:
            media_url: Media URL (relative /uploads/... or absolute)
            save_path: Optional path to save file (if None, returns bytes only)

        Returns:
            File content as bytes

        Raises:
            MediaError: On download failure

        Examples:
            >>> # Download to bytes
            >>> content = client.download_file("/uploads/image.jpg")
            >>> len(content)
            102400

            >>> # Download and save to file
            >>> content = client.download_file(
            ...     "/uploads/image.jpg",
            ...     save_path="downloaded_image.jpg"
            ... )
        """
        try:
            # Build full URL
            url = build_media_download_url(self.base_url, media_url)

            # Download with streaming for large files
            with self._client.stream("GET", url) as response:
                if not response.is_success:
                    self._handle_error_response(response)

                # Read content
                content = b"".join(response.iter_bytes())

                # Save to file if path provided
                if save_path:
                    path = Path(save_path)
                    path.write_bytes(content)
                    logger.info(f"Downloaded {len(content)} bytes to {save_path}")

                return content

        except Exception as e:
            raise MediaError(f"File download failed: {e}") from e

    def list_media(
        self,
        query: StrapiQuery | None = None,
    ) -> NormalizedCollectionResponse:
        """List media files from media library.

        Args:
            query: Optional query for filtering, sorting, pagination

        Returns:
            NormalizedCollectionResponse with MediaFile entities

        Examples:
            >>> # List all media
            >>> response = client.list_media()
            >>> for media in response.data:
            ...     print(media.attributes["name"])

            >>> # List with filters
            >>> from py_strapi.models import StrapiQuery, FilterBuilder
            >>> query = (StrapiQuery()
            ...     .filter(FilterBuilder().eq("mime", "image/jpeg"))
            ...     .paginate(page=1, page_size=10))
            >>> response = client.list_media(query)
        """
        params = query.to_query_params() if query else None
        raw_response = self.get("upload/files", params=params)
        return self._parse_media_list_response(raw_response)

    def get_media(
        self,
        media_id: str | int,
    ) -> MediaFile:
        """Get specific media file details.

        Args:
            media_id: Media file ID (numeric or documentId)

        Returns:
            MediaFile details

        Raises:
            NotFoundError: If media doesn't exist

        Examples:
            >>> media = client.get_media(42)
            >>> media.name
            'image.jpg'
            >>> media.url
            '/uploads/image.jpg'
        """
        raw_response = self.get(f"upload/files/{media_id}")
        return self._parse_media_response(raw_response)

    def delete_media(
        self,
        media_id: str | int,
    ) -> None:
        """Delete a media file.

        Args:
            media_id: Media file ID (numeric or documentId)

        Raises:
            NotFoundError: If media doesn't exist
            MediaError: On deletion failure

        Examples:
            >>> client.delete_media(42)
            >>> # File deleted successfully
        """
        try:
            self.delete(f"upload/files/{media_id}")
        except Exception as e:
            raise MediaError(f"Media deletion failed: {e}") from e

    def update_media(
        self,
        media_id: str | int,
        *,
        alternative_text: str | None = None,
        caption: str | None = None,
        name: str | None = None,
    ) -> MediaFile:
        """Update media file metadata.

        Args:
            media_id: Media file ID (numeric or documentId)
            alternative_text: New alt text
            caption: New caption
            name: New file name

        Returns:
            Updated MediaFile

        Raises:
            NotFoundError: If media doesn't exist
            MediaError: On update failure

        Examples:
            >>> media = client.update_media(
            ...     42,
            ...     alternative_text="Updated alt text",
            ...     caption="Updated caption"
            ... )
            >>> media.alternative_text
            'Updated alt text'
        """
        try:
            # Build update payload
            file_info: dict[str, Any] = {}
            if alternative_text is not None:
                file_info["alternativeText"] = alternative_text
            if caption is not None:
                file_info["caption"] = caption
            if name is not None:
                file_info["name"] = name

            # Make update request
            raw_response = self.put(
                f"upload/files/{media_id}",
                json={"fileInfo": file_info} if file_info else {},
            )
            return self._parse_media_response(raw_response)

        except Exception as e:
            raise MediaError(f"Media update failed: {e}") from e
