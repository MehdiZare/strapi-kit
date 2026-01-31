"""Base HTTP client for Strapi API communication.

This module provides the foundation for all HTTP operations with
automatic response format detection, error handling, and authentication.
"""

import logging
from typing import Any, Literal

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from ..auth.api_token import APITokenAuth
from ..exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    RateLimitError,
    ServerError,
    StrapiError,
    ValidationError,
)
from ..exceptions import (
    ConnectionError as StrapiConnectionError,
)
from ..models.response.media import MediaFile
from ..models.response.normalized import (
    NormalizedCollectionResponse,
    NormalizedSingleResponse,
)
from ..operations.media import normalize_media_response
from ..parsers import VersionDetectingParser
from ..protocols import AuthProvider, ConfigProvider, ResponseParser

logger = logging.getLogger(__name__)


class BaseClient:
    """Base HTTP client for Strapi API operations.

    This class provides the foundation for both synchronous and asynchronous
    clients with:
    - Authentication via API tokens
    - Automatic Strapi version detection (v4 vs v5)
    - Error handling and exception mapping
    - Request/response logging
    - Connection pooling

    Not intended to be used directly - use SyncClient or AsyncClient instead.
    """

    def __init__(
        self,
        config: ConfigProvider,
        auth: AuthProvider | None = None,
        parser: ResponseParser | None = None,
    ) -> None:
        """Initialize the base client with dependency injection.

        Args:
            config: Configuration provider (typically StrapiConfig)
            auth: Authentication provider (defaults to APITokenAuth)
            parser: Response parser (defaults to VersionDetectingParser)

        Raises:
            ValueError: If authentication token is invalid
        """
        self.config: ConfigProvider = config
        self.base_url = config.get_base_url()

        # Dependency injection with sensible defaults
        self.auth: AuthProvider = auth or APITokenAuth(config.get_api_token())
        self.parser: ResponseParser = parser or VersionDetectingParser(
            default_version=None if config.api_version == "auto" else config.api_version
        )

        # Validate authentication
        if not self.auth.validate_token():
            raise ValueError("API token is required and cannot be empty")

        # API version detection (for backward compatibility)
        self._api_version: Literal["v4", "v5"] | None = (
            None if config.api_version == "auto" else config.api_version
        )

        logger.info(
            f"Initialized Strapi client for {self.base_url} (version: {config.api_version})"
        )

    def _get_headers(self, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
        """Build request headers with authentication.

        Args:
            extra_headers: Additional headers to include

        Returns:
            Complete headers dictionary
        """
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **self.auth.get_headers(),
        }

        if extra_headers:
            headers.update(extra_headers)

        return headers

    def _build_url(self, endpoint: str) -> str:
        """Build full URL for an endpoint.

        Args:
            endpoint: API endpoint path (e.g., "articles" or "/api/articles")

        Returns:
            Complete URL
        """
        # Remove leading and trailing slashes from endpoint
        endpoint = endpoint.strip("/")

        # Ensure /api prefix for content endpoints
        if not endpoint.startswith("api/"):
            endpoint = f"api/{endpoint}"

        return f"{self.base_url}/{endpoint}"

    def _detect_api_version(self, response_data: dict[str, Any]) -> Literal["v4", "v5"]:
        """Detect Strapi API version from response structure.

        Args:
            response_data: Response JSON data

        Returns:
            Detected API version
        """
        # If already detected or configured, use that
        if self._api_version:
            return self._api_version

        # V4: data.attributes structure
        # V5: flattened data with documentId
        if isinstance(response_data.get("data"), dict):
            data = response_data["data"]
            if "attributes" in data:
                self._api_version = "v4"
                logger.info("Detected Strapi v4 API format")
            elif "documentId" in data:
                self._api_version = "v5"
                logger.info("Detected Strapi v5 API format")
            else:
                # Default to v4 if uncertain
                self._api_version = "v4"
                logger.warning("Could not detect API version, defaulting to v4")
        elif isinstance(response_data.get("data"), list) and response_data["data"]:
            # Check first item in list
            first_item = response_data["data"][0]
            if "attributes" in first_item:
                self._api_version = "v4"
                logger.info("Detected Strapi v4 API format")
            elif "documentId" in first_item:
                self._api_version = "v5"
                logger.info("Detected Strapi v5 API format")
            else:
                self._api_version = "v4"
                logger.warning("Could not detect API version, defaulting to v4")
        else:
            # No data field or empty - default to v4
            self._api_version = "v4"

        return self._api_version

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Handle HTTP error responses by raising appropriate exceptions.

        Args:
            response: HTTPX response object

        Raises:
            Appropriate StrapiError subclass based on status code
        """
        status_code = response.status_code

        # Try to extract error details from response
        try:
            error_data = response.json()
            error_message = error_data.get("error", {}).get("message", response.text)
            error_details = error_data.get("error", {}).get("details", {})
        except Exception:
            error_message = response.text or f"HTTP {status_code}"
            error_details = {}

        # Map status codes to exceptions
        if status_code == 401:
            raise AuthenticationError(
                f"Authentication failed: {error_message}", details=error_details
            )
        elif status_code == 403:
            raise AuthorizationError(
                f"Authorization failed: {error_message}", details=error_details
            )
        elif status_code == 404:
            raise NotFoundError(f"Resource not found: {error_message}", details=error_details)
        elif status_code == 400:
            raise ValidationError(f"Validation error: {error_message}", details=error_details)
        elif status_code == 409:
            raise ConflictError(f"Conflict: {error_message}", details=error_details)
        elif status_code == 429:
            retry_after = response.headers.get("Retry-After")
            # RFC 7231: Retry-After can be numeric seconds or HTTP-date string
            retry_seconds: int | None = None
            if retry_after:
                try:
                    retry_seconds = int(retry_after)
                except ValueError:
                    # HTTP-date format (e.g., "Wed, 21 Oct 2015 07:28:00 GMT")
                    # Fall back to default retry behavior
                    retry_seconds = None
            raise RateLimitError(
                f"Rate limit exceeded: {error_message}",
                retry_after=retry_seconds,
                details=error_details,
            )
        elif 500 <= status_code < 600:
            raise ServerError(
                f"Server error: {error_message}",
                status_code=status_code,
                details=error_details,
            )
        else:
            raise StrapiError(
                f"Unexpected error (HTTP {status_code}): {error_message}",
                details=error_details,
            )

    def _create_retry_decorator(self) -> Any:
        """Create a retry decorator based on configuration.

        The decorator retries on:
        - Server errors (5xx) and connection issues
        - Rate limit errors (429) with retry_after support
        - Configured status codes from retry_on_status

        Returns:
            Configured tenacity retry decorator
        """
        retry_config = self.config.retry

        def should_retry_exception(exception: BaseException) -> bool:
            """Determine if exception should trigger retry."""
            # Always retry connection issues
            if isinstance(exception, StrapiConnectionError):
                return True

            # Retry RateLimitError with exponential backoff
            if isinstance(exception, RateLimitError):
                return True

            # Check if exception has status_code matching retry_on_status
            # This includes ServerError if its status code is in retry_on_status
            if hasattr(exception, "status_code"):
                return exception.status_code in retry_config.retry_on_status

            return False

        def wait_strategy(retry_state):  # type: ignore[no-untyped-def]
            """Custom wait strategy that respects retry_after."""
            exception = retry_state.outcome.exception()

            # If RateLimitError with retry_after, use that value
            if isinstance(exception, RateLimitError) and exception.retry_after:
                return exception.retry_after

            # Otherwise use exponential backoff
            return wait_exponential(
                multiplier=retry_config.exponential_base,
                min=retry_config.initial_wait,
                max=retry_config.max_wait,
            )(retry_state)

        return retry(
            stop=stop_after_attempt(retry_config.max_attempts),
            wait=wait_strategy,
            retry=retry_if_exception(should_retry_exception),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )

    @property
    def api_version(self) -> Literal["v4", "v5"] | None:
        """Get the detected or configured API version.

        Returns:
            API version or None if not yet detected
        """
        return self._api_version

    def _parse_single_response(self, response_data: dict[str, Any]) -> NormalizedSingleResponse:
        """Parse a single entity response into normalized format.

        Delegates to the injected parser for actual parsing logic.

        Args:
            response_data: Raw JSON response from Strapi

        Returns:
            Normalized single entity response

        Examples:
            >>> response_data = {"data": {"id": 1, "documentId": "abc", ...}}
            >>> normalized = client._parse_single_response(response_data)
            >>> normalized.data.id
            1
        """
        # Delegate to injected parser
        return self.parser.parse_single(response_data)

    def _parse_collection_response(
        self, response_data: dict[str, Any]
    ) -> NormalizedCollectionResponse:
        """Parse a collection response into normalized format.

        Delegates to the injected parser for actual parsing logic.

        Args:
            response_data: Raw JSON response from Strapi

        Returns:
            Normalized collection response

        Examples:
            >>> response_data = {"data": [{"id": 1, ...}, {"id": 2, ...}]}
            >>> normalized = client._parse_collection_response(response_data)
            >>> len(normalized.data)
            2
        """
        # Delegate to injected parser
        return self.parser.parse_collection(response_data)

    def _build_upload_headers(self) -> dict[str, str]:
        """Build headers for multipart file upload.

        Omits Content-Type header to let httpx set the multipart boundary automatically.

        Returns:
            Headers dictionary without Content-Type
        """
        headers = {
            "Accept": "application/json",
            **self.auth.get_headers(),
        }
        return headers

    def _parse_media_response(self, response_data: dict[str, Any]) -> MediaFile:
        """Parse media upload/download response into MediaFile model.

        Automatically detects v4/v5 format and normalizes the response.

        Args:
            response_data: Raw JSON response from Strapi media endpoint

        Returns:
            Validated MediaFile instance

        Examples:
            >>> # v5 response
            >>> response_data = {
            ...     "id": 1,
            ...     "documentId": "abc123",
            ...     "name": "image.jpg",
            ...     "url": "/uploads/image.jpg",
            ...     ...
            ... }
            >>> media = client._parse_media_response(response_data)
            >>> media.name
            'image.jpg'
        """
        api_version = self._detect_api_version({"data": response_data})
        return normalize_media_response(response_data, api_version)

    def _parse_media_list_response(
        self, response_data: dict[str, Any] | list[dict[str, Any]]
    ) -> NormalizedCollectionResponse:
        """Parse media library list response into normalized collection.

        Media list responses may be in standard Strapi collection format
        or a raw array (depending on Strapi version/plugin).

        Args:
            response_data: Raw JSON response from media list endpoint
                          (may be dict with "data" key or raw array)

        Returns:
            Normalized collection response with MediaFile entities

        Examples:
            >>> # Standard format
            >>> response_data = {
            ...     "data": [
            ...         {"id": 1, "name": "image1.jpg", ...},
            ...         {"id": 2, "name": "image2.jpg", ...}
            ...     ],
            ...     "meta": {"pagination": {...}}
            ... }
            >>> result = client._parse_media_list_response(response_data)
            >>> len(result.data)
            2

            >>> # Raw array format (Strapi Upload plugin)
            >>> response_data = [{"id": 1, "name": "image.jpg", ...}]
            >>> result = client._parse_media_list_response(response_data)
            >>> len(result.data)
            1
        """
        # Handle raw array response (Strapi Upload plugin may return this)
        if isinstance(response_data, list):
            response_data = {"data": response_data, "meta": {}}

        # Media list follows standard collection format
        return self._parse_collection_response(response_data)
