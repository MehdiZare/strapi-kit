"""Base HTTP client for Strapi API communication.

This module provides the foundation for all HTTP operations with
automatic response format detection, error handling, and authentication.
"""

import logging
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Literal, NoReturn
from urllib.parse import quote

if TYPE_CHECKING:
    from ..models.content_type import ComponentListItem, ContentTypeListItem
    from ..models.content_type import ContentTypeSchema as CTBContentTypeSchema

import httpx
from pydantic import ValidationError as PydanticValidationError
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
    ConfigurationError,
    ConflictError,
    MethodNotAllowedError,
    NotFoundError,
    RateLimitError,
    ServerError,
    StrapiError,
    UnstructuredResponseError,
    UnstructuredResponseReason,
    ValidationError,
)
from ..exceptions import (
    ConnectionError as StrapiConnectionError,
)
from ..models.enums import DocumentAction, DocumentStatus, HttpMethod
from ..models.request.query import StrapiQuery
from ..models.response.media import MediaFile
from ..models.response.normalized import (
    NormalizedCollectionResponse,
    NormalizedEntity,
    NormalizedSingleResponse,
)
from ..operations.media import normalize_media_response
from ..parsers import VersionDetectingParser
from ..protocols import AuthProvider, ConfigProvider, ResponseParser
from ..utils.endpoints import join_document_path
from ..utils.schema import (
    extract_content_type_options,
    extract_draft_and_publish,
    extract_info_from_schema,
)

logger = logging.getLogger(__name__)

# Per-task HTTP status for UnstructuredResponseError. Instance state would
# race when one AsyncClient is used concurrently.
_response_status_code: ContextVar[int | None] = ContextVar(
    "strapi_kit_response_status_code", default=None
)


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
            ConfigurationError: If authentication token is invalid
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
            raise ConfigurationError("API token is required and cannot be empty")

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

    def _build_url(self, endpoint: str, *, api_prefix: bool = True) -> str:
        """Build full URL for an endpoint.

        Content, Content-Type Builder, and upload routes stay under ``/api``.
        Admin routes such as ``/admin/information`` are origin-rooted; pass
        ``api_prefix=False`` to skip the default prefix.

        Args:
            endpoint: API endpoint path (e.g., "articles", "/api/articles",
                or "/admin/information")
            api_prefix: When True (default), prefix the path with ``api/``
                unless it already starts with ``api/``. When False, join the
                stripped path to the origin as-is.

        Returns:
            Complete URL
        """
        # Remove leading and trailing slashes from endpoint
        endpoint = endpoint.strip("/")

        # Ensure /api prefix for content endpoints unless explicitly opted out
        if api_prefix and not endpoint.startswith("api/"):
            endpoint = f"api/{endpoint}"

        return f"{self.base_url}/{endpoint}"

    @staticmethod
    def document_path(collection: str, document_id: str) -> str:
        """Build a collection/document path with a percent-encoded document ID.

        The collection name is stripped of leading/trailing slashes and left
        unencoded (it comes from ``pluralName``, not user data). ``document_id``
        is encoded with ``quote(..., safe="")`` so characters such as ``/``,
        ``?``, ``#``, and ``%`` cannot change the request path.

        Args:
            collection: Collection plural name (e.g., ``"articles"``).
            document_id: Document ID or numeric id as a string.

        Returns:
            Path of the form ``{collection}/{encoded_document_id}``.

        Raises:
            ValidationError: If ``collection`` or ``document_id`` is blank.

        Examples:
            >>> BaseClient.document_path("articles", "abc123")
            'articles/abc123'
            >>> BaseClient.document_path("/articles/", "a/b?x=1")
            'articles/a%2Fb%3Fx%3D1'
        """
        return join_document_path(collection, document_id)

    def _document_endpoint(self, endpoint: str, document_id: str | None) -> str:
        """Resolve a typed CRUD path, encoding ``document_id`` when provided.

        Args:
            endpoint: Full path (e.g., ``"articles/abc"``) or collection name
                when ``document_id`` is set.
            document_id: Optional document ID. When provided, ``endpoint`` is
                treated as the collection name.

        Returns:
            Endpoint path to pass to HTTP helpers.

        Raises:
            ValidationError: If ``document_id`` is provided and collection or
                document ID is blank.
        """
        if document_id is None:
            return endpoint
        return self.document_path(endpoint, document_id)

    def _single_segment_document_path(self, collection: str, document_id: str) -> str:
        """Build ``document_path`` after requiring a single collection segment.

        Used by ``exists()`` and ``publish()`` so lookups and stock REST
        publish share the CRUD encoder and cannot walk out of the collection
        via ``/`` or ``\\`` in the name.
        """
        collection_name = collection.strip().strip("/")
        if not collection_name:
            raise ValidationError("collection is required")
        if "/" in collection_name or "\\" in collection_name:
            raise ValidationError("collection must be a single path segment")
        return self.document_path(collection_name, document_id)

    def _document_action_endpoint(
        self,
        collection: str,
        document_id: str,
        action: DocumentAction,
    ) -> str:
        """Build a Strapi v5 document-action path.

        Uses :meth:`document_path` so action helpers and typed CRUD share one
        document-ID encoder. Collection must be a single path segment.
        """
        collection_name = collection.strip().strip("/")
        if not collection_name:
            raise ValidationError("collection is required")
        if "/" in collection_name or "\\" in collection_name:
            raise ValidationError("collection must be a single path segment")
        encoded_collection = quote(collection_name, safe="")
        return f"{self.document_path(encoded_collection, document_id)}/actions/{action.value}"

    def _draft_status_query(self) -> StrapiQuery:
        """Query that requests the Strapi 5 draft version (``status=draft``)."""
        return StrapiQuery().with_document_status(DocumentStatus.DRAFT)

    def _write_query_is_draft(self, query: StrapiQuery | None) -> bool:
        """Return True when the write already addressed ``status=draft``."""
        return query is not None and query.document_status is DocumentStatus.DRAFT

    def _entity_identifies_document(self, entity: NormalizedEntity | None) -> bool:
        """Return True if a GET body identifies a document (``documentId`` or ``id``)."""
        if entity is None:
            return False
        return entity.document_id is not None or entity.id is not None

    def _authorization_error_for_write_404(self, original: NotFoundError) -> AuthorizationError:
        """Map a write 404 to AuthorizationError when the document is readable."""
        status_code = original.status_code if original.status_code is not None else 404
        details = dict(original.details)
        details["status_code"] = status_code
        details["classified_from"] = "write_404"
        return AuthorizationError(
            "document exists; token likely lacks Update/Publish.",
            details=details,
            status_code=status_code,
        )

    def _reraise_classified_write_404(
        self,
        original: NotFoundError,
        probe_entity: NormalizedEntity | None,
    ) -> NoReturn:
        """Raise AuthorizationError if the write-params probe found a document.

        A hit on the same query the write used means the addressed variant
        is readable, so the write 404 was permission / routing — not a
        missing published version. Otherwise re-raise the original 404.
        """
        if self._entity_identifies_document(probe_entity):
            raise self._authorization_error_for_write_404(original) from original
        raise original

    def _parse_success_response(self, response: httpx.Response, *, method: str) -> dict[str, Any]:
        """Parse a 2xx response body.

        Empty DELETE bodies (any 2xx) are success with ``{}``. JSON
        objects and arrays are success (Upload ``GET /upload/files`` is a
        raw array). Other empty or scalar 2xx bodies — including 204 on
        POST/PUT/GET — raise :class:`UnstructuredResponseError`.
        """
        verb = method.upper()
        _response_status_code.set(response.status_code)
        empty = response.status_code == 204 or not response.content
        if empty:
            if verb == HttpMethod.DELETE:
                logger.debug(f"Response: {response.status_code} (no content)")
                return {}
            raise UnstructuredResponseError(
                f"Successful HTTP {response.status_code} returned an empty body",
                details={"method": verb, "body_preview": ""},
                status_code=response.status_code,
                reason=UnstructuredResponseReason.EMPTY_BODY,
            )

        try:
            data: Any = response.json()
        except ValueError as json_error:
            content_type = response.headers.get("content-type", "unknown")
            body_preview = response.text[:500] if response.text else ""
            raise UnstructuredResponseError(
                f"Successful HTTP {response.status_code} returned non-JSON "
                f"(content-type: {content_type})",
                details={"method": verb, "body_preview": body_preview},
                status_code=response.status_code,
                reason=UnstructuredResponseReason.NON_JSON,
            ) from json_error

        if isinstance(data, list):
            return {"data": data}
        if not isinstance(data, dict):
            body_preview = response.text[:500] if response.text else ""
            raise UnstructuredResponseError(
                f"Successful HTTP {response.status_code} returned non-object JSON",
                details={
                    "method": verb,
                    "body_preview": body_preview,
                    "parsed_type": type(data).__name__,
                },
                status_code=response.status_code,
                reason=UnstructuredResponseReason.NON_OBJECT,
            )
        return data

    def _detect_api_version(self, response_data: dict[str, Any]) -> Literal["v4", "v5"]:
        """Detect Strapi API version from response structure.

        Only caches the version when detection is definitive (attributes or documentId found).
        Ambiguous responses return v4 as fallback without caching.

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
                return self._api_version
            elif "documentId" in data:
                self._api_version = "v5"
                logger.info("Detected Strapi v5 API format")
                return self._api_version
            else:
                # Ambiguous - don't cache, return v4 as fallback
                logger.warning("Could not detect API version, using v4 fallback (not cached)")
                return "v4"
        elif isinstance(response_data.get("data"), list) and response_data["data"]:
            # Check first item in list
            first_item = response_data["data"][0]
            if "attributes" in first_item:
                self._api_version = "v4"
                logger.info("Detected Strapi v4 API format")
                return self._api_version
            elif "documentId" in first_item:
                self._api_version = "v5"
                logger.info("Detected Strapi v5 API format")
                return self._api_version
            else:
                # Ambiguous - don't cache, return v4 as fallback
                logger.warning("Could not detect API version, using v4 fallback (not cached)")
                return "v4"
        else:
            # No data field or empty - don't cache, return v4 as fallback
            return "v4"

    def reset_version_detection(self) -> None:
        """Reset the cached API version detection.

        Call this if you need to re-detect the API version, for example
        after changing the Strapi instance or during testing.
        """
        self._api_version = None
        logger.info("Reset API version detection cache")

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

        # Map status codes to exceptions. Every HTTP error carries status_code
        # so callers can classify without parsing the message string.
        if status_code == 401:
            raise AuthenticationError(
                f"Authentication failed: {error_message}",
                details=error_details,
                status_code=status_code,
            )
        elif status_code == 403:
            raise AuthorizationError(
                f"Authorization failed: {error_message}",
                details=error_details,
                status_code=status_code,
            )
        elif status_code == 404:
            raise NotFoundError(
                f"Resource not found: {error_message}",
                details=error_details,
                status_code=status_code,
            )
        elif status_code in {400, 422}:
            raise ValidationError(
                f"Validation error: {error_message}",
                details=error_details,
                status_code=status_code,
            )
        elif status_code == 405:
            raise MethodNotAllowedError(
                f"Method not allowed: {error_message}",
                details=error_details,
                status_code=status_code,
            )
        elif status_code == 409:
            raise ConflictError(
                f"Conflict: {error_message}",
                details=error_details,
                status_code=status_code,
            )
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
                status_code=status_code,
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
        try:
            return self.parser.parse_single(response_data)
        except PydanticValidationError as e:
            raise UnstructuredResponseError(
                "Successful response did not match a single-entity document",
                details={"errors": e.errors()},
                status_code=_response_status_code.get(),
                reason=UnstructuredResponseReason.UNPARSEABLE_ENTITY,
            ) from e

    def _require_write_data_object(self, response_data: dict[str, Any]) -> None:
        """Raise if a typed write response has no JSON ``data`` object.

        Stock REST create/update/publish bodies are ``{"data": {...}}``.
        A 2xx ``{}`` or ``{"ok": true}`` must not look like a successful
        entity write (no ``documentId``). Collection ``{"data": []}`` is
        not a write body.
        """
        data = response_data.get("data")
        if isinstance(data, dict):
            return
        raise UnstructuredResponseError(
            "Successful write returned no data object",
            details={
                "has_data": "data" in response_data,
                "parsed_type": type(data).__name__,
            },
            status_code=_response_status_code.get(),
            reason=UnstructuredResponseReason.MISSING_DATA,
        )

    def _publish_put_args(
        self,
        collection: str,
        document_id: str,
        query: StrapiQuery | None,
    ) -> tuple[str, dict[str, Any]]:
        """Build stock REST publish path and query (PUT + ``status=published``)."""
        path = self._single_segment_document_path(collection, document_id)
        publish_query = query.copy() if query is not None else StrapiQuery()
        publish_query = publish_query.with_document_status(DocumentStatus.PUBLISHED)
        return path, publish_query.to_query_params()

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

        For v4 responses with nested attributes, this method flattens each
        item before passing to the collection parser to ensure consistent
        handling with single media responses.

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

        # For v4, flatten nested attributes to match v5 format before parsing
        if isinstance(response_data.get("data"), list):
            data_items = response_data["data"]
            if data_items and isinstance(data_items[0], dict) and "attributes" in data_items[0]:
                # v4 format - flatten each item
                flattened_items = []
                for item in data_items:
                    if "attributes" in item:
                        flattened = {"id": item["id"], **item["attributes"]}
                        flattened_items.append(flattened)
                    else:
                        flattened_items.append(item)
                response_data = {"data": flattened_items, "meta": response_data.get("meta", {})}

        # Media list follows standard collection format
        return self._parse_collection_response(response_data)

    def _normalize_content_type_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Normalize content type item - flatten v5 schema to v4 format.

        Strapi v5 returns content types with a nested 'schema' structure:
        {"uid": "...", "apiID": "...", "schema": {"kind": "...", "info": {...}, ...}}

        Or with flat schema properties (actual v5 API - Issue #28):
        {"uid": "...", "apiID": "...", "schema": {"kind": "...", "displayName": "...", ...}}

        This method flattens names/attributes to v4 format and retains Draft &
        Publish sources (``options``, ``schema.draftAndPublish``,
        ``schema.options.draftAndPublish``, top-level item flag):
        {"uid": "...", "kind": "...", "info": {...}, "attributes": {...},
         "options": {...} | None, "draftAndPublish": True | False | None}

        ``draftAndPublish`` is ``None`` when the flag is absent. Absence is not
        ``False``. ``publishedAt`` is never used to infer Draft & Publish.

        Args:
            item: Raw content type item from API response

        Returns:
            Normalized content type item in v4-compatible format
        """
        if "schema" in item and isinstance(item["schema"], dict):
            schema = item["schema"]
            return {
                "uid": item.get("uid", ""),
                "kind": schema.get("kind", "collectionType"),
                "info": extract_info_from_schema(schema),
                "attributes": schema.get("attributes", {}),
                "pluginOptions": schema.get("pluginOptions"),
                "options": extract_content_type_options(item),
                "draftAndPublish": extract_draft_and_publish(item),
            }
        return item

    def _normalize_component_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Normalize component item - flatten v5 schema to v4 format.

        Strapi v5 returns components with a nested 'schema' structure:
        {"uid": "...", "category": "...", "schema": {"info": {...}, "attributes": {...}}}

        Or with flat schema properties (actual v5 API - Issue #28):
        {"uid": "...", "category": "...", "schema": {"displayName": "...", "attributes": {...}}}

        This method flattens it to v4 format:
        {"uid": "...", "category": "...", "info": {...}, "attributes": {...}}

        Args:
            item: Raw component item from API response

        Returns:
            Normalized component item in v4-compatible format
        """
        if "schema" in item and isinstance(item["schema"], dict):
            schema = item["schema"]
            return {
                "uid": item.get("uid", ""),
                "category": item.get("category", schema.get("category", "")),
                "info": extract_info_from_schema(schema),
                "attributes": schema.get("attributes", {}),
            }
        return item

    def _parse_content_types_response(
        self,
        response_data: dict[str, Any],
        include_plugins: bool = False,
        *,
        skip_unparsable: bool = False,
    ) -> list["ContentTypeListItem"]:
        """Parse content-type-builder content types response.

        Automatically normalizes v5 nested schema format to v4 flat format.

        Args:
            response_data: Raw JSON response from content-type-builder
            include_plugins: Whether to include plugin content types
            skip_unparsable: If True, log and skip items that fail Pydantic
                validation. If False (default), raise ValidationError.

        Returns:
            List of ContentTypeListItem instances

        Raises:
            ValidationError: If ``data`` is not a list, an item is not an
                object, or an item cannot be parsed — unless skip_unparsable
                is True (list items only)
        """
        from ..models.content_type import ContentTypeListItem

        data = response_data.get("data", [])
        if data is None:
            data = []
        if not isinstance(data, list):
            raise ValidationError(
                "Invalid content types response: 'data' must be a list",
                details={"data_type": type(data).__name__},
            )

        result = []

        for index, item in enumerate(data):
            if not isinstance(item, dict):
                if skip_unparsable:
                    logger.warning(
                        "Failed to parse content type: expected object at index %s",
                        index,
                    )
                    continue
                raise ValidationError(
                    "Failed to parse content type: <unknown>",
                    details={"index": index, "item_type": type(item).__name__},
                )

            uid_raw = item.get("uid")
            uid = uid_raw if isinstance(uid_raw, str) else ""
            # Filter out plugin content types if not requested
            if not include_plugins and uid.startswith("plugin::"):
                continue

            try:
                normalized_item = self._normalize_content_type_item(item)
                content_type = ContentTypeListItem.model_validate(normalized_item)
                result.append(content_type)
            except PydanticValidationError as e:
                if skip_unparsable:
                    logger.warning(f"Failed to parse content type: {uid}", exc_info=e)
                    continue
                raise ValidationError(
                    f"Failed to parse content type: {uid or '<unknown>'}",
                    details={"uid": uid or None, "errors": e.errors()},
                ) from e

        return result

    def _parse_components_response(
        self,
        response_data: dict[str, Any],
        *,
        skip_unparsable: bool = False,
    ) -> list["ComponentListItem"]:
        """Parse content-type-builder components response.

        Automatically normalizes v5 nested schema format to v4 flat format.

        Args:
            response_data: Raw JSON response from content-type-builder
            skip_unparsable: If True, log and skip items that fail Pydantic
                validation. If False (default), raise ValidationError.

        Returns:
            List of ComponentListItem instances

        Raises:
            ValidationError: If ``data`` is not a list, an item is not an
                object, or an item cannot be parsed — unless skip_unparsable
                is True (list items only)
        """
        from ..models.content_type import ComponentListItem

        data = response_data.get("data", [])
        if data is None:
            data = []
        if not isinstance(data, list):
            raise ValidationError(
                "Invalid components response: 'data' must be a list",
                details={"data_type": type(data).__name__},
            )

        result = []

        for index, item in enumerate(data):
            if not isinstance(item, dict):
                if skip_unparsable:
                    logger.warning(
                        "Failed to parse component: expected object at index %s",
                        index,
                    )
                    continue
                raise ValidationError(
                    "Failed to parse component: <unknown>",
                    details={"index": index, "item_type": type(item).__name__},
                )

            uid_raw = item.get("uid")
            uid = uid_raw if isinstance(uid_raw, str) else ""
            try:
                normalized_item = self._normalize_component_item(item)
                component = ComponentListItem.model_validate(normalized_item)
                result.append(component)
            except PydanticValidationError as e:
                if skip_unparsable:
                    logger.warning(f"Failed to parse component: {uid}", exc_info=e)
                    continue
                raise ValidationError(
                    f"Failed to parse component: {uid or '<unknown>'}",
                    details={"uid": uid or None, "errors": e.errors()},
                ) from e

        return result

    def _parse_content_type_schema_response(
        self,
        response_data: dict[str, Any],
    ) -> "CTBContentTypeSchema":
        """Parse content-type-builder single content type schema response.

        Automatically normalizes v5 nested schema format to v4 flat format.

        Args:
            response_data: Raw JSON response from content-type-builder

        Returns:
            CTBContentTypeSchema instance

        Raises:
            ValidationError: If response cannot be parsed
        """
        from ..models.content_type import ContentTypeSchema as CTBContentTypeSchema

        data = response_data.get("data", response_data)
        if not isinstance(data, dict):
            raise ValidationError(
                "Invalid content type schema response",
                details={"data_type": type(data).__name__},
            )
        try:
            normalized_data = self._normalize_content_type_item(data)
            return CTBContentTypeSchema.model_validate(normalized_data)
        except PydanticValidationError as e:
            raise ValidationError(
                "Invalid content type schema response",
                details={"errors": e.errors()},
            ) from e
