"""Asynchronous HTTP client for Strapi API.

This module provides non-blocking I/O operations for high-concurrency
applications and batch operations.
"""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

if TYPE_CHECKING:
    from ..models.content_type import ComponentListItem, ContentTypeListItem
    from ..models.content_type import ContentTypeSchema as CTBContentTypeSchema

import httpx

from ..exceptions import (
    AuthenticationError,
    AuthorizationError,
    MediaError,
    NotFoundError,
    ServerError,
    StrapiError,
    ValidationError,
    is_unknown_status_param,
)
from ..exceptions import (
    ConnectionError as StrapiConnectionError,
)
from ..exceptions import (
    TimeoutError as StrapiTimeoutError,
)
from ..models.bulk import BulkOperationFailure, BulkOperationResult
from ..models.enums import DocumentAction, HttpMethod
from ..models.request.query import StrapiQuery
from ..models.response.admin import AdminInformation
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
        *,
        api_prefix: bool = True,
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
            api_prefix: When True (default), prefix the path with ``/api``.
                Set False for origin-rooted routes such as ``/admin/information``.

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

            url = self._build_url(endpoint, api_prefix=api_prefix)
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

                data = self._parse_success_response(response, method=method)
                # Origin-rooted routes are not content-API payloads.
                if api_prefix and data and isinstance(data, dict):
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
        *,
        api_prefix: bool = True,
    ) -> dict[str, Any]:
        """Make a GET request.

        Args:
            endpoint: API endpoint path
            params: URL query parameters
            headers: Additional headers
            api_prefix: When True (default), prefix the path with ``/api``.

        Returns:
            Response JSON data
        """
        return await self.request(
            HttpMethod.GET, endpoint, params=params, headers=headers, api_prefix=api_prefix
        )

    async def post(
        self,
        endpoint: str,
        json: dict[str, Any],
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        *,
        api_prefix: bool = True,
    ) -> dict[str, Any]:
        """Make a POST request.

        Args:
            endpoint: API endpoint path
            json: JSON request body
            params: URL query parameters
            headers: Additional headers
            api_prefix: When True (default), prefix the path with ``/api``.

        Returns:
            Response JSON data
        """
        return await self.request(
            HttpMethod.POST,
            endpoint,
            params=params,
            json=json,
            headers=headers,
            api_prefix=api_prefix,
        )

    async def put(
        self,
        endpoint: str,
        json: dict[str, Any],
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        *,
        api_prefix: bool = True,
    ) -> dict[str, Any]:
        """Make a PUT request.

        Args:
            endpoint: API endpoint path
            json: JSON request body
            params: URL query parameters
            headers: Additional headers
            api_prefix: When True (default), prefix the path with ``/api``.

        Returns:
            Response JSON data
        """
        return await self.request(
            HttpMethod.PUT,
            endpoint,
            params=params,
            json=json,
            headers=headers,
            api_prefix=api_prefix,
        )

    async def delete(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        *,
        api_prefix: bool = True,
    ) -> dict[str, Any]:
        """Make a DELETE request.

        Args:
            endpoint: API endpoint path
            params: URL query parameters
            headers: Additional headers
            api_prefix: When True (default), prefix the path with ``/api``.

        Returns:
            Response JSON data
        """
        return await self.request(
            HttpMethod.DELETE, endpoint, params=params, headers=headers, api_prefix=api_prefix
        )

    async def get_admin_information(self) -> AdminInformation:
        """GET ``{base}/admin/information`` (origin-rooted, no ``/api`` prefix).

        Use this to probe a Strapi instance. Content, Content-Type Builder, and
        upload endpoints remain under ``/api``. Default ``get(\"admin/information\")``
        still prefixes ``/api`` for backward compatibility.

        Version is read from ``strapiVersion`` or ``data.strapiVersion``. A
        missing version is still a successful probe.

        Returns:
            Structured admin information including the raw JSON payload.

        Raises:
            AuthenticationError: If the request is unauthorized (401)
            AuthorizationError: If the token lacks permission (403)
            NotFoundError: If the endpoint does not exist (404)
            UnstructuredResponseError: If a 2xx body is empty, non-JSON, or not an object
            StrapiError: On other API errors

        Examples:
            >>> info = await client.get_admin_information()
            >>> info.strapi_version
            '5.11.0'
        """
        raw_response = await self.get("admin/information", api_prefix=False)
        return AdminInformation.from_response(raw_response)

    # Typed methods for normalized responses

    async def get_one(
        self,
        endpoint: str,
        query: StrapiQuery | None = None,
        headers: dict[str, str] | None = None,
        *,
        document_id: str | None = None,
    ) -> NormalizedSingleResponse:
        """Get a single entity with typed, normalized response.

        Args:
            endpoint: API endpoint path (e.g., "articles/1" or "articles/abc123").
                When ``document_id`` is provided, this is the collection name
                (e.g., "articles").
            query: Optional query configuration (populate, fields, locale, etc.)
            headers: Additional headers
            document_id: Optional document ID. When provided, ``endpoint`` is
                treated as the collection name and the ID is percent-encoded.

        Returns:
            Normalized single entity response

        Raises:
            ValidationError: If ``document_id`` is provided and collection or
                document ID is blank.

        Examples:
            >>> from strapi_kit.models import StrapiQuery, Populate
            >>> query = (StrapiQuery()
            ...     .populate_fields(["author", "category"])
            ...     .select(["title", "content"]))
            >>> response = await client.get_one("articles/1", query=query)
            >>> response = await client.get_one("articles", document_id="abc123")
            >>> article = response.data
            >>> article.attributes["title"]
            'My Article'
        """
        path = self._document_endpoint(endpoint, document_id)
        params = query.to_query_params() if query else None
        raw_response = await self.get(path, params=params, headers=headers)
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
            query: Optional query c