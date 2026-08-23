"""Synchronous HTTP client for Strapi API.

This module provides blocking I/O operations for simpler scripts
and applications that don't require concurrency.
"""

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
from ..protocols import AuthProvider, ConfigProvider, HTTPClient, ResponseParser
from ..utils.rate_limiter import TokenBucketRateLimiter
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
        from strapi_kit import SyncClient, StrapiConfig

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
        self._client: HTTPClient | httpx.Client = http_client or self._create_default_http_client()
        self._owns_client = http_client is None

        # Initialize rate limiter if configured
        self._rate_limiter: TokenBucketRateLimiter | None = None
        if hasattr(config, "rate_limit_per_second") and config.rate_limit_per_second:
            self._rate_limiter = TokenBucketRateLimiter(rate=config.rate_limit_per_second)

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
        def _do_request() -> dict[str, Any]:
            """Internal request implementation with retry support."""
            # Apply rate limiting if configured
            if self._rate_limiter:
                self._rate_limiter.acquire()

            url = self._build_url(endpoint, api_prefix=api_prefix)
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

        return _do_request()  # type: ignore[no-any-return]

    def get(
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
        return self.request(
            HttpMethod.GET, endpoint, params=params, headers=headers, api_prefix=api_prefix
        )

    def post(
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
        return self.request(
            HttpMethod.POST,
            endpoint,
            params=params,
            json=json,
            headers=headers,
            api_prefix=api_prefix,
        )

    def put(
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
        return self.request(
            HttpMethod.PUT,
            endpoint,
            params=params,
            json=json,
            headers=headers,
            api_prefix=api_prefix,
        )

    def delete(
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
        return self.request(
            HttpMethod.DELETE, endpoint, params=params, headers=headers, api_prefix=api_prefix
        )

    def get_admin_information(self) -> AdminInformation:
        """GET ``{base}/admin/information`` (origin-rooted, no ``/api`` prefix).

        Use this to probe a Strapi instance. Content, Content-Type Builder, and
        upload endpoints remain under ``/api``. Default ``get("admin/information")``
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
            >>> info = client.get_admin_information()
            >>> info.strapi_version
            '5.11.0'
        """
        raw_response = self.get("admin/information", api_prefix=False)
        return AdminInformation.from_response(raw_response)
