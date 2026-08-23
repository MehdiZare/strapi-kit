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
