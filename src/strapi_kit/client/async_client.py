"""Asynchronous HTTP client for Strapi API.

This module provides non-blocking I/O operations for high-concurrency
applications and batch operations.
"""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..models.content_type import ComponentListItem, ContentTypeListItem
    from ..models.content_type import ContentTypeSchema as CTBContentTypeSchema

import httpx

from ..exceptions import (
    ConnectionError as StrapiConnectionError,
)
from ..exceptions import (
    FormatError,
    MediaError,
    StrapiError,
)
from ..exceptions import (
    TimeoutError as StrapiTimeoutError,
)
from ..models.bulk import BulkOperationFailure, BulkOperationResult
from ..models.request.query import StrapiQuery
from ..models.response.media import MediaFile
from ..models.response.normalized import (
    NormalizedCollectionResponse,
    NormalizedEntity,
    NormalizedSingleResponse,
)
from ..operations.media import build_media_download_url, build_upload_payload
from ..protocols import AsyncHTTPClient, AuthProvider, ConfigProvider, ResponseParser
from ..utils.rate_limiter import AsyncTokenBucketRateLimiter
from .base import BaseClient

logger = logging.getLogger(__name__)


class AsyncClient(BaseClient):
    """Asynchronous HTTP client for Strapi API.

    This client uses non-blocking I/O and is suitable for:
    - High-concurrency applications
    - Batch operations on many documents
    - Applications using async/await patterns

    Example:
        ```python
        import asyncio
        from strapi_kit import AsyncClient, StrapiConfig

        async def main():
            config = StrapiConfig(
                base_url="http://localhost:1337",
                api_token="your-token"
            )

            async with AsyncClient(config) as client:
                response = await client.get("articles")
                print(response)

        asyncio.run(main())
        ```
    """

    def __init__(
        self,
        config: ConfigProvider,
        http_client: AsyncHTTPClient | None = None,
        auth: AuthProvider | None = None,
        parser: ResponseParser | None = None,
    ) -> None:
        """Initialize the asynchronous client with dependency injection.

        Args:
            config: Configuration provider (typically StrapiConfig)
            http_client: Async HTTP client (defaults to httpx.AsyncClient with pooling)
            auth: Authentication provider (passed to BaseClient)
            parser: Response parser (passed to BaseClient)
        """
        super().__init__(config, auth=auth, parser=parser)

        # Dependency injection with default factory
        self._client: AsyncHTTPClient | httpx.AsyncClient = (
            http_client or self._create_default_http_client()
        )
        self._owns_client = http_client is None

        # Initialize rate limiter if configured
        self._rate_limiter: AsyncTokenBucketRateLimiter | None = None
        if hasattr(config, "rate_limit_per_second") and config.rate_limit_per_second:
            self._rate_limiter = AsyncTokenBucketRateLimiter(rate=config.rate_limit_per_second)

    def _create_default_http_client(self) -> httpx.AsyncClient:
        """Create default async HTTP client with connection pooling.

        Returns:
            Configured httpx.AsyncClient instance
        """
        return httpx.AsyncClient(
            timeout=self.config.timeout,
            verify=self.config.verify_ssl,
            limits=httpx.Limits(
                max_connections=self.config.max_connections,
                max_keepalive_connections=self.config.max_connections,
            ),
        )

    async def __aenter__(self) -> "AsyncClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit - closes the client."""
        await self.close()

    async def close(self) -> None:
        """Close the HTTP client and release connections.

        Only closes the client if it was created by this instance
        (not injected from outside).
        """
        if self._owns_client:
            await self._client.aclose()
        logger.info("Closed asynchronous Strapi client")

    async def request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request to the Strapi API with automatic retry.

        Retries are automatically applied based on the retry configuration:
        - Server errors (5xx)
        - Connection failures
        - Rate limit errors (429) with retry_after support
        - Configured status codes from retry_on_status

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            params: URL query parameters
            json: JSON request body
            headers: Additional headers

        Returns:
            Response JSON data

        Raises:
            StrapiError: On API errors (after retries exhausted)
            ConnectionError: On connection failures (after retries exhausted)
            TimeoutError: On request timeout (after retries exhausted)
        """
        # Create retry-wrapped version of internal request
        retry_decorator = self._create_retry_decorator()

        @retry_decorator  # type: ignore[untyped-decorator]
        async def _do_request() -> dict[str, Any]:
            """Internal async request implementation with retry support."""
            # Apply rate limiting if configured
            if self._rate_limiter:
                await self._rate_limiter.acquire()

            url = self._build_url(endpoint)
            request_headers = self._get_headers(headers)

            logger.debug(f"{method} {url} params={params}")

            try:
                response = await self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json,
                    headers=request_headers,
                )

                # Handle error responses
                if not response.is_success:
                    self._handle_error_response(response)

                # Handle 204 No Content (common for DELETE operations)
                if response.status_code == 204 or not response.content:
                    logger.debug(f"Response: {response.status_code} (no content)")
                    return {}

                # Parse and return JSON with proper error handling for non-JSON responses
                try:
                    data: dict[str, Any] = response.json()
                except Exception as json_error:
                    content_type = response.headers.get("content-type", "unknown")
                    body_preview = response.text[:500] if response.text else ""
                    raise FormatError(
                        f"Received non-JSON response (content-type: {content_type})",
                        details={"body_preview": body_preview},
                    ) from json_error

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

        return await _do_request()  # type: ignore[no-any-return]

    async def get(
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
        return await self.request("GET", endpoint, params=params, headers=headers)

    async def post(
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
        return await self.request("POST", endpoint, params=params, json=json, headers=headers)

    async def put(
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
        return await self.request("PUT", endpoint, params=params, json=json, headers=headers)

    async def delete(
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
        return await self.request("DELETE", endpoint, params=params, headers=headers)

    # Typed methods for normalized responses

    async def get_one(
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
            >>> from strapi_kit.models import StrapiQuery, Populate
            >>> query = (StrapiQuery()
            ...     .populate_fields(["author", "category"])
            ...     .select(["title", "content"]))
            >>> response = await client.get_one("articles/1", query=query)
            >>> article = response.data
            >>> article.attributes["title"]
            'My Article'
        """
        params = query.to_query_params() if query else None
        raw_response = await self.get(endpoint, params=params, headers=headers)
        return self._parse_single_response(raw_response)

    async def get_many(
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
            >>> from strapi_kit.models import StrapiQuery, FilterBuilder, SortDirection
            >>> query = (StrapiQuery()
            ...     .filter(FilterBuilder().eq("status", "published"))
            ...     .sort_by("publishedAt", SortDirection.DESC)
            ...     .paginate(page=1, page_size=25)
            ...     .populate_fields(["author"]))
            >>> response = await client.get_many("articles", query=query)
            >>> for article in response.data:
            ...     print(article.attributes["title"])
        """
        params = query.to_query_params() if query else None
        raw_response = await self.get(endpoint, params=params, headers=headers)
        return self._parse_collection_response(raw_response)

    async def create(
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
            >>> response = await client.create("articles", data)
            >>> created = response.data
            >>> created.id
            42
        """
        params = query.to_query_params() if query else None
        # Wrap data in Strapi format
        payload = {"data": data}
        raw_response = await self.post(endpoint, json=payload, params=params, headers=headers)
        return self._parse_single_response(raw_response)

    async def update(
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
            >>> response = await client.update("articles/1", data)
            >>> updated = response.data
            >>> updated.attributes["title"]
            'Updated Title'
        """
        params = query.to_query_params() if query else None
        # Wrap data in Strapi format
        payload = {"data": data}
        raw_response = await self.put(endpoint, json=payload, params=params, headers=headers)
        return self._parse_single_response(raw_response)

    async def remove(
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
            >>> response = await client.remove("articles/1")
            >>> deleted = response.data
            >>> deleted.id
            1
        """
        raw_response = await self.delete(endpoint, headers=headers)
        return self._parse_single_response(raw_response)

    # Media Operations

    async def upload_file(
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
            >>> media = await client.upload_file("image.jpg")
            >>> media.name
            'image.jpg'

            >>> # Upload with metadata
            >>> media = await client.upload_file(
            ...     "hero.jpg",
            ...     alternative_text="Hero image",
            ...     caption="Main article image"
            ... )

            >>> # Upload and attach to entity
            >>> media = await client.upload_file(
            ...     "cover.jpg",
            ...     ref="api::article.article",
            ...     ref_id="abc123",
            ...     field="cover"
            ... )
        """
        try:
            # Build multipart payload with context manager to ensure file handle cleanup
            with build_upload_payload(
                file_path,
                ref=ref,
                ref_id=ref_id,
                field=field,
                folder=folder,
                alternative_text=alternative_text,
                caption=caption,
            ) as payload:
                # Build URL and headers
                url = self._build_url("upload")
                headers = self._build_upload_headers()

                # Make async request with multipart data
                response = await self._client.post(
                    url,
                    files={"files": payload.files_tuple},
                    data=payload.data,
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

    async def upload_files(
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
            >>> media_list = await client.upload_files(files)
            >>> len(media_list)
            3

            >>> # Upload with shared metadata
            >>> media_list = await client.upload_files(
            ...     ["thumb1.jpg", "thumb2.jpg"],
            ...     folder="thumbnails"
            ... )
        """
        uploaded: list[MediaFile] = []

        for idx, file_path in enumerate(file_paths):
            try:
                media = await self.upload_file(file_path, **kwargs)
                uploaded.append(media)
            except Exception as e:
                raise MediaError(
                    f"Batch upload failed at file {idx} ({file_path}): {e}. "
                    f"{len(uploaded)} files were uploaded successfully before failure."
                ) from e

        return uploaded

    async def download_file(
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
            >>> content = await client.download_file("/uploads/image.jpg")
            >>> len(content)
            102400

            >>> # Download and save to file
            >>> content = await client.download_file(
            ...     "/uploads/image.jpg",
            ...     save_path="downloaded_image.jpg"
            ... )
        """
        try:
            # Build full URL
            url = build_media_download_url(self.base_url, media_url)

            # Download with async streaming for large files
            async with self._client.stream("GET", url) as response:
                if not response.is_success:
                    self._handle_error_response(response)

                if save_path:
                    # Stream directly to disk for memory efficiency
                    # Note: Using sync file I/O here as aiofiles is not a dependency
                    # The streaming download itself is async which is the main benefit
                    path = Path(save_path)
                    total_bytes = 0
                    with open(path, "wb") as f:
                        async for chunk in response.aiter_bytes():
                            f.write(chunk)
                            total_bytes += len(chunk)
                    logger.info(f"Downloaded {total_bytes} bytes to {save_path}")
                    # Read back for API compatibility
                    return path.read_bytes()
                else:
                    # Buffer in memory (original behavior for in-memory use)
                    chunks = []
                    async for chunk in response.aiter_bytes():
                        chunks.append(chunk)
                    return b"".join(chunks)

        except StrapiError:
            raise  # Preserve specific error types (NotFoundError, etc.)
        except Exception as e:
            raise MediaError(f"File download failed: {e}") from e

    async def list_media(
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
            >>> response = await client.list_media()
            >>> for media in response.data:
            ...     print(media.attributes["name"])

            >>> # List with filters
            >>> from strapi_kit.models import StrapiQuery, FilterBuilder
            >>> query = (StrapiQuery()
            ...     .filter(FilterBuilder().eq("mime", "image/jpeg"))
            ...     .paginate(page=1, page_size=10))
            >>> response = await client.list_media(query)
        """
        params = query.to_query_params() if query else None
        raw_response = await self.get("upload/files", params=params)
        return self._parse_media_list_response(raw_response)

    async def get_media(
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
            >>> media = await client.get_media(42)
            >>> media.name
            'image.jpg'
            >>> media.url
            '/uploads/image.jpg'
        """
        raw_response = await self.get(f"upload/files/{media_id}")
        return self._parse_media_response(raw_response)

    async def delete_media(
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
            >>> await client.delete_media(42)
            >>> # File deleted successfully
        """
        try:
            await self.delete(f"upload/files/{media_id}")
        except StrapiError:
            raise  # Preserve specific error types (NotFoundError, etc.)
        except Exception as e:
            raise MediaError(f"Media deletion failed: {e}") from e

    async def update_media(
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
            >>> media = await client.update_media(
            ...     42,
            ...     alternative_text="Updated alt text",
            ...     caption="Updated caption"
            ... )
            >>> media.alternative_text
            'Updated alt text'
        """
        import json as json_module

        try:
            # Ensure API version is detected before choosing endpoint
            # When api_version="auto" and no prior API call, _api_version is None
            if self._api_version is None:
                await self.get_media(media_id)  # Triggers version detection

            # Build update payload
            file_info: dict[str, Any] = {}
            if alternative_text is not None:
                file_info["alternativeText"] = alternative_text
            if caption is not None:
                file_info["caption"] = caption
            if name is not None:
                file_info["name"] = name

            headers = self._build_upload_headers()

            # v4 uses PUT /api/upload/files/:id
            # v5 uses POST /api/upload?id=x with form-data
            if self._api_version == "v4":
                url = self._build_url(f"upload/files/{media_id}")
                response = await self._client.request(
                    method="PUT",
                    url=url,
                    json={"fileInfo": file_info} if file_info else {},
                    headers=self._get_headers(),
                )
            else:
                # v5 or auto (default to v5 behavior)
                url = f"{self._build_url('upload')}?id={media_id}"
                response = await self._client.post(
                    url,
                    data={"fileInfo": json_module.dumps(file_info)} if file_info else {},
                    headers=headers,
                )

            # Handle errors
            if not response.is_success:
                self._handle_error_response(response)

            # Parse response
            response_json = response.json()
            if isinstance(response_json, list) and response_json:
                return self._parse_media_response(response_json[0])
            else:
                return self._parse_media_response(response_json)

        except StrapiError:
            raise  # Preserve specific error types (NotFoundError, etc.)
        except Exception as e:
            raise MediaError(f"Media update failed: {e}") from e

    # Bulk Operations

    async def bulk_create(
        self,
        endpoint: str,
        items: list[dict[str, Any]],
        *,
        batch_size: int = 10,
        max_concurrency: int = 5,
        query: StrapiQuery | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> BulkOperationResult:
        """Create multiple entities in concurrent batches.

        Args:
            endpoint: API endpoint (e.g., "articles")
            items: List of entity data dicts
            batch_size: Items per batch wave (default: 10). Controls memory usage
                by limiting how many tasks are active at once.
            max_concurrency: Max parallel requests within each batch (default: 5)
            query: Optional query
            progress_callback: Optional callback(completed, total)

        Returns:
            BulkOperationResult with successes and failures

        Example:
            >>> items = [
            ...     {"title": "Article 1", "content": "..."},
            ...     {"title": "Article 2", "content": "..."},
            ... ]
            >>> result = await client.bulk_create("articles", items, batch_size=20, max_concurrency=10)
            >>> print(f"Created {result.succeeded}/{result.total}")
        """
        successes: list[NormalizedEntity] = []
        failures: list[BulkOperationFailure] = []
        completed = 0

        async def create_one(idx: int, item: dict[str, Any], semaphore: asyncio.Semaphore) -> None:
            nonlocal completed

            async with semaphore:
                try:
                    response = await self.create(endpoint, item, query=query)

                    if response.data:
                        successes.append(response.data)
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(items))

                except StrapiError as e:
                    failures.append(
                        BulkOperationFailure(
                            index=idx,
                            item=item,
                            error=str(e),
                            exception=e,
                        )
                    )
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(items))

        # Process items in batches to control memory usage
        for batch_start in range(0, len(items), batch_size):
            batch = items[batch_start : batch_start + batch_size]
            semaphore = asyncio.Semaphore(max_concurrency)

            # Create tasks for this batch only
            tasks = [create_one(batch_start + i, item, semaphore) for i, item in enumerate(batch)]

            # Execute batch with gather
            await asyncio.gather(*tasks, return_exceptions=False)

        return BulkOperationResult(
            successes=successes,
            failures=failures,
            total=len(items),
            succeeded=len(successes),
            failed=len(failures),
        )

    async def bulk_update(
        self,
        endpoint: str,
        updates: list[tuple[str | int, dict[str, Any]]],
        *,
        batch_size: int = 10,
        max_concurrency: int = 5,
        query: StrapiQuery | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> BulkOperationResult:
        """Update multiple entities in concurrent batches.

        Args:
            endpoint: API endpoint (e.g., "articles")
            updates: List of (id, data) tuples
            batch_size: Items per batch wave (default: 10). Controls memory usage
                by limiting how many tasks are active at once.
            max_concurrency: Max parallel requests within each batch (default: 5)
            query: Optional query
            progress_callback: Optional callback(completed, total)

        Returns:
            BulkOperationResult

        Example:
            >>> updates = [
            ...     (1, {"title": "Updated Title 1"}),
            ...     (2, {"title": "Updated Title 2"}),
            ... ]
            >>> result = await client.bulk_update("articles", updates, batch_size=20)
            >>> print(f"Updated {result.succeeded}/{result.total}")
        """
        successes: list[NormalizedEntity] = []
        failures: list[BulkOperationFailure] = []
        completed = 0

        async def update_one(
            idx: int, entity_id: str | int, data: dict[str, Any], semaphore: asyncio.Semaphore
        ) -> None:
            nonlocal completed

            async with semaphore:
                try:
                    response = await self.update(f"{endpoint}/{entity_id}", data, query=query)

                    if response.data:
                        successes.append(response.data)
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(updates))

                except StrapiError as e:
                    failures.append(
                        BulkOperationFailure(
                            index=idx,
                            item={"id": entity_id, "data": data},
                            error=str(e),
                            exception=e,
                        )
                    )
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(updates))

        # Process updates in batches to control memory usage
        for batch_start in range(0, len(updates), batch_size):
            batch = updates[batch_start : batch_start + batch_size]
            semaphore = asyncio.Semaphore(max_concurrency)

            # Create tasks for this batch only
            tasks = [
                update_one(batch_start + i, entity_id, data, semaphore)
                for i, (entity_id, data) in enumerate(batch)
            ]

            # Execute batch with gather
            await asyncio.gather(*tasks, return_exceptions=False)

        return BulkOperationResult(
            successes=successes,
            failures=failures,
            total=len(updates),
            succeeded=len(successes),
            failed=len(failures),
        )

    async def bulk_delete(
        self,
        endpoint: str,
        ids: list[str | int],
        *,
        batch_size: int = 10,
        max_concurrency: int = 5,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> BulkOperationResult:
        """Delete multiple entities in concurrent batches.

        Args:
            endpoint: API endpoint (e.g., "articles")
            ids: List of entity IDs (numeric or documentId)
            batch_size: Items per batch wave (default: 10). Controls memory usage
                by limiting how many tasks are active at once.
            max_concurrency: Max parallel requests within each batch (default: 5)
            progress_callback: Optional callback(completed, total)

        Returns:
            BulkOperationResult

        Example:
            >>> ids = [1, 2, 3, 4, 5]
            >>> result = await client.bulk_delete("articles", ids, batch_size=20)
            >>> print(f"Deleted {result.succeeded} articles")
        """
        successes: list[NormalizedEntity] = []
        failures: list[BulkOperationFailure] = []
        completed = 0
        success_count = 0

        async def delete_one(idx: int, entity_id: str | int, semaphore: asyncio.Semaphore) -> None:
            nonlocal completed, success_count

            async with semaphore:
                try:
                    response = await self.remove(f"{endpoint}/{entity_id}")

                    # DELETE may return 204 No Content with no data
                    # Count as success when no exception is raised
                    success_count += 1
                    if response.data:
                        successes.append(response.data)
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(ids))

                except StrapiError as e:
                    failures.append(
                        BulkOperationFailure(
                            index=idx,
                            item={"id": entity_id},
                            error=str(e),
                            exception=e,
                        )
                    )
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(ids))

        # Process deletes in batches to control memory usage
        for batch_start in range(0, len(ids), batch_size):
            batch = ids[batch_start : batch_start + batch_size]
            semaphore = asyncio.Semaphore(max_concurrency)

            # Create tasks for this batch only
            tasks = [
                delete_one(batch_start + i, entity_id, semaphore)
                for i, entity_id in enumerate(batch)
            ]

            # Execute batch with gather
            await asyncio.gather(*tasks, return_exceptions=False)

        return BulkOperationResult(
            successes=successes,
            failures=failures,
            total=len(ids),
            succeeded=success_count,
            failed=len(failures),
        )

    # Content-Type Builder API

    async def get_content_types(
        self,
        *,
        include_plugins: bool = False,
    ) -> list["ContentTypeListItem"]:
        """List all content types from Content-Type Builder API.

        Retrieves schema information for all content types defined in Strapi.

        Args:
            include_plugins: Whether to include plugin content types
                            (e.g., users-permissions). Defaults to False.

        Returns:
            List of ContentTypeListItem with uid, kind, info, and attributes

        Examples:
            >>> # Get only API content types
            >>> content_types = await client.get_content_types()
            >>> for ct in content_types:
            ...     print(f"{ct.uid}: {ct.info.display_name}")
            api::article.article: Article
            api::category.category: Category

            >>> # Include plugin content types
            >>> all_types = await client.get_content_types(include_plugins=True)
            >>> plugin_types = [ct for ct in all_types if ct.uid.startswith("plugin::")]
        """

        raw_response = await self.get("content-type-builder/content-types")
        return self._parse_content_types_response(raw_response, include_plugins)

    async def get_components(self) -> list["ComponentListItem"]:
        """List all components from Content-Type Builder API.

        Retrieves schema information for all components defined in Strapi.

        Returns:
            List of ComponentListItem with uid, category, info, and attributes

        Examples:
            >>> components = await client.get_components()
            >>> for comp in components:
            ...     print(f"{comp.category}/{comp.uid}: {comp.info.display_name}")
            shared/shared.seo: SEO
            blocks/blocks.hero: Hero Section
        """

        raw_response = await self.get("content-type-builder/components")
        return self._parse_components_response(raw_response)

    async def get_content_type_schema(self, uid: str) -> "CTBContentTypeSchema":
        """Get full schema for a specific content type.

        Retrieves detailed schema information including all field configurations.

        Args:
            uid: Content type UID (e.g., "api::article.article")

        Returns:
            CTBContentTypeSchema with complete field definitions

        Raises:
            NotFoundError: If content type doesn't exist

        Examples:
            >>> schema = await client.get_content_type_schema("api::article.article")
            >>> schema.info.display_name
            'Article'
            >>> schema.attributes["title"]["type"]
            'string'
            >>> schema.is_relation_field("author")
            True
            >>> schema.get_relation_target("author")
            'api::author.author'
        """

        raw_response = await self.get(f"content-type-builder/content-types/{uid}")
        return self._parse_content_type_schema_response(raw_response)
