"""Base HTTP client for Strapi API communication.

This module provides the foundation for all HTTP operations with
automatic response format detection, error handling, and authentication.
"""

import logging
from typing import Any, Literal

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
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
from ..models.config import StrapiConfig
from ..models.response.normalized import (
    NormalizedCollectionResponse,
    NormalizedEntity,
    NormalizedSingleResponse,
)
from ..models.response.v4 import V4CollectionResponse, V4SingleResponse
from ..models.response.v5 import V5CollectionResponse, V5SingleResponse

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

    def __init__(self, config: StrapiConfig) -> None:
        """Initialize the base client.

        Args:
            config: Strapi configuration with URL, token, and options
        """
        self.config = config
        self.base_url = config.get_base_url()
        self.auth = APITokenAuth(config.get_api_token())

        # Validate authentication
        if not self.auth.validate_token():
            raise ValueError("API token is required and cannot be empty")

        # API version detection
        self._api_version: Literal["v4", "v5"] | None = (
            None if config.api_version == "auto" else config.api_version
        )

        logger.info(
            f"Initialized Strapi client for {self.base_url} "
            f"(version: {config.api_version})"
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
            raise ValidationError(
                f"Validation error: {error_message}", details=error_details
            )
        elif status_code == 409:
            raise ConflictError(f"Conflict: {error_message}", details=error_details)
        elif status_code == 429:
            retry_after = response.headers.get("Retry-After")
            retry_seconds = int(retry_after) if retry_after else None
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

        Returns:
            Configured tenacity retry decorator
        """
        retry_config = self.config.retry

        return retry(
            stop=stop_after_attempt(retry_config.max_attempts),
            wait=wait_exponential(
                multiplier=retry_config.exponential_base,
                min=retry_config.initial_wait,
                max=retry_config.max_wait,
            ),
            retry=retry_if_exception_type((ServerError, StrapiConnectionError)),
            reraise=True,
        )

    @property
    def api_version(self) -> Literal["v4", "v5"] | None:
        """Get the detected or configured API version.

        Returns:
            API version or None if not yet detected
        """
        return self._api_version

    def _parse_single_response(
        self, response_data: dict[str, Any]
    ) -> NormalizedSingleResponse:
        """Parse a single entity response into normalized format.

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
        # Detect API version from response
        api_version = self._detect_api_version(response_data)

        if api_version == "v4":
            # Parse as v4 and normalize
            v4_response = V4SingleResponse(**response_data)
            if v4_response.data:
                normalized_entity = NormalizedEntity.from_v4(v4_response.data)
            else:
                normalized_entity = None

            return NormalizedSingleResponse(data=normalized_entity, meta=v4_response.meta)
        else:
            # Parse as v5 and normalize
            v5_response = V5SingleResponse(**response_data)
            if v5_response.data:
                normalized_entity = NormalizedEntity.from_v5(v5_response.data)
            else:
                normalized_entity = None

            return NormalizedSingleResponse(data=normalized_entity, meta=v5_response.meta)

    def _parse_collection_response(
        self, response_data: dict[str, Any]
    ) -> NormalizedCollectionResponse:
        """Parse a collection response into normalized format.

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
        # Detect API version from response
        api_version = self._detect_api_version(response_data)

        if api_version == "v4":
            # Parse as v4 and normalize
            v4_response = V4CollectionResponse(**response_data)
            normalized_entities = [NormalizedEntity.from_v4(entity) for entity in v4_response.data]

            return NormalizedCollectionResponse(data=normalized_entities, meta=v4_response.meta)
        else:
            # Parse as v5 and normalize
            v5_response = V5CollectionResponse(**response_data)
            normalized_entities = [NormalizedEntity.from_v5(entity) for entity in v5_response.data]

            return NormalizedCollectionResponse(data=normalized_entities, meta=v5_response.meta)
