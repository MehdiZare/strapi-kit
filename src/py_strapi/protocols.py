"""Protocol definitions for dependency injection.

This module defines interfaces for core components, enabling:
- Dependency injection
- Easy mocking in tests
- Loose coupling between components
- Custom implementations
"""

from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

import httpx

from .models.response.normalized import (
    NormalizedCollectionResponse,
    NormalizedSingleResponse,
)

if TYPE_CHECKING:
    from .models.schema import ContentTypeSchema


@runtime_checkable
class AuthProvider(Protocol):
    """Protocol for authentication providers.

    Implementations must provide methods to generate auth headers
    and validate credentials.
    """

    def get_headers(self) -> dict[str, str]:
        """Get authentication headers for HTTP requests.

        Returns:
            Dictionary with authentication headers (e.g., Authorization: Bearer ...)
        """
        ...

    def validate_token(self) -> bool:
        """Validate that authentication credentials are valid.

        Returns:
            True if credentials are valid, False otherwise
        """
        ...


@runtime_checkable
class HTTPClient(Protocol):
    """Protocol for synchronous HTTP clients.

    Defines the interface for making HTTP requests in sync mode.
    """

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make an HTTP request.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            url: Full URL to request
            params: URL query parameters
            json: JSON request body
            headers: HTTP headers

        Returns:
            HTTP response object
        """
        ...

    def post(
        self,
        url: str,
        *,
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make a POST request with multipart data.

        Args:
            url: Full URL to request
            files: Files for multipart upload
            data: Form data
            headers: HTTP headers

        Returns:
            HTTP response object
        """
        ...

    def stream(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> Any:
        """Stream an HTTP request.

        Args:
            method: HTTP method
            url: Full URL to request
            **kwargs: Additional request parameters

        Returns:
            Context manager for streaming response
        """
        ...

    def close(self) -> None:
        """Close the HTTP client and release resources."""
        ...


@runtime_checkable
class AsyncHTTPClient(Protocol):
    """Protocol for asynchronous HTTP clients.

    Defines the interface for making HTTP requests in async mode.
    """

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make an async HTTP request.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            url: Full URL to request
            params: URL query parameters
            json: JSON request body
            headers: HTTP headers

        Returns:
            HTTP response object
        """
        ...

    async def post(
        self,
        url: str,
        *,
        files: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make an async POST request with multipart data.

        Args:
            url: Full URL to request
            files: Files for multipart upload
            data: Form data
            headers: HTTP headers

        Returns:
            HTTP response object
        """
        ...

    def stream(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> Any:
        """Stream an async HTTP request.

        Args:
            method: HTTP method
            url: Full URL to request
            **kwargs: Additional request parameters

        Returns:
            Async context manager for streaming response.
            Note: httpx.AsyncClient.stream() is NOT an async method itself -
            it returns an async context manager directly. Use with `async with`.
        """
        ...

    async def aclose(self) -> None:
        """Close the HTTP client and release resources."""
        ...


@runtime_checkable
class ResponseParser(Protocol):
    """Protocol for response parsers.

    Implementations must handle parsing of Strapi responses
    into normalized format.
    """

    def parse_single(self, response_data: dict[str, Any]) -> NormalizedSingleResponse:
        """Parse a single entity response.

        Args:
            response_data: Raw JSON response from Strapi

        Returns:
            Normalized single entity response
        """
        ...

    def parse_collection(self, response_data: dict[str, Any]) -> NormalizedCollectionResponse:
        """Parse a collection response.

        Args:
            response_data: Raw JSON response from Strapi

        Returns:
            Normalized collection response
        """
        ...


@runtime_checkable
class ConfigProvider(Protocol):
    """Protocol for configuration providers.

    Defines the interface for accessing client configuration.
    This allows for alternative config sources (files, databases, etc.)
    while maintaining type safety.
    """

    def get_base_url(self) -> str:
        """Get the base URL of the Strapi instance.

        Returns:
            Base URL (without trailing slash)
        """
        ...

    def get_api_token(self) -> str:
        """Get the API token for authentication.

        Returns:
            API token string
        """
        ...

    @property
    def api_version(self) -> Literal["v4", "v5", "auto"]:
        """Get the configured API version.

        Returns:
            API version ("v4", "v5", or "auto")
        """
        ...

    @property
    def timeout(self) -> float:
        """Get request timeout in seconds.

        Returns:
            Timeout value
        """
        ...

    @property
    def max_connections(self) -> int:
        """Get maximum concurrent connections.

        Returns:
            Max connections count
        """
        ...

    @property
    def verify_ssl(self) -> bool:
        """Get SSL verification setting.

        Returns:
            Whether to verify SSL certificates
        """
        ...

    @property
    def retry(self) -> Any:
        """Get retry configuration.

        Returns:
            Retry config object
        """
        ...


@runtime_checkable
class SchemaProvider(Protocol):
    """Protocol for content type schema providers.

    Defines the interface for accessing and caching content type schemas.
    Enables proper relation resolution during export/import operations.
    """

    def get_schema(self, content_type: str) -> "ContentTypeSchema":
        """Get schema for a content type.

        Args:
            content_type: Content type UID (e.g., "api::article.article")

        Returns:
            Content type schema
        """
        ...

    def cache_schema(self, content_type: str, schema: "ContentTypeSchema") -> None:
        """Cache schema for a content type.

        Args:
            content_type: Content type UID
            schema: Schema to cache
        """
        ...

    def clear_cache(self) -> None:
        """Clear all cached schemas."""
        ...

    def has_schema(self, content_type: str) -> bool:
        """Check if schema is cached.

        Args:
            content_type: Content type UID

        Returns:
            True if schema is cached, False otherwise
        """
        ...
