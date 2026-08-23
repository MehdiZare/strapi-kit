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
        self._require_write_data_object(raw_response)
        return self._parse_single_response(raw_response)

    async def update(
        self,
        endpoint: str,
        data: dict[str, Any],
        query: StrapiQuery | None = None,
        headers: dict[str, str] | None = None,
        *,
        document_id: str | None = None,
        classify_write_404: bool = False,
    ) -> NormalizedSingleResponse:
        """Update an existing entity with typed, normalized response.

        Args:
            endpoint: API endpoint path (e.g., "articles/1" or "articles/abc123").
                When ``document_id`` is provided, this is the collection name
                (e.g., "articles").
            data: Entity data to update (wrapped in {"data": {...}} automatically)
            query: Optional query configuration (populate, fields, etc.)
            headers: Additional headers
            document_id: Optional document ID. When provided, ``endpoint`` is
                treated as the collection name and the ID is percent-encoded.
            classify_write_404: If True, a write ``NotFoundError`` is probed
                with the write's own query params, then ``status=draft``
                if the write was not already draft. A hit on the write's
                params remaps to ``AuthorizationError`` (token likely
                lacks Update/Publish). A draft-only document stays
                ``NotFoundError``. Default False keeps today's 404 mapping.

        Returns:
            Normalized single entity response

        Raises:
            ValidationError: If ``document_id`` is provided and collection or
                document ID is blank.

        Examples:
            >>> data = {"title": "Updated Title"}
            >>> response = await client.update("articles/1", data)
            >>> response = await client.update("articles", data, document_id="abc123")
            >>> updated = response.data
            >>> updated.attributes["title"]
            'Updated Title'
        """
        path = self._document_endpoint(endpoint, document_id)
        params = query.to_query_params() if query else None
        # Wrap data in Strapi format
        payload = {"data": data}
        try:
            raw_response = await self.put(path, json=payload, params=params, headers=headers)
        except NotFoundError as original:
            if classify_write_404:
                await self._classify_write_404(path, original, write_query=query)
            raise
        self._require_write_data_object(raw_response)
        return self._parse_single_response(raw_response)

    async def remove(
        self,
        endpoint: str,
        headers: dict[str, str] | None = None,
        *,
        document_id: str | None = None,
        classify_write_404: bool = False,
    ) -> NormalizedSingleResponse:
        """Delete an entity with typed, normalized response.

        Args:
            endpoint: API endpoint path (e.g., "articles/1" or "articles/abc123").
                When ``document_id`` is provided, this is the collection name
                (e.g., "articles").
            headers: Additional headers
            document_id: Optional document ID. When provided, ``endpoint`` is
                treated as the collection name and the ID is percent-encoded.
            classify_write_404: If True, a write ``NotFoundError`` is probed
                with omit-status (published), then ``status=draft``. A hit
                on the published probe remaps to ``AuthorizationError``.
                A draft-only document stays ``NotFoundError``. Default
                False keeps today's 404 mapping.

        Returns:
            Normalized single entity response (deleted entity)

        Raises:
            ValidationError: If ``document_id`` is provided and collection or
                document ID is blank.

        Examples:
            >>> response = await client.remove("articles/1")
            >>> response = await client.remove("articles", document_id="abc123")
            >>> deleted = response.data
            >>> deleted.id
            1
        """
        path = self._document_endpoint(endpoint, document_id)
        try:
            raw_response = await self.delete(path, headers=headers)
        except NotFoundError as original:
            if classify_write_404:
                await self._classify_write_404(path, original)
            raise
        return self._parse_single_response(raw_response)

    async def exists(self, collection: str, document_id: str) -> bool:
        """Return whether a document exists as published or draft.

        Strapi 5 omitted ``status=`` means published, so a draft-only
        document 404s on the default GET. A published miss is retried
        once with ``status=draft``. A draft ``ValidationError`` is absent
        only for unknown ``status`` / ``publicationState``. Other 400s
        (populate, filters) raise.
        Auth, 5xx, and network errors on either read raise. Collection
        must be a single path segment; ``document_id`` is percent-encoded
        via :meth:`document_path`. This check is not locale-scoped: a hit
        is the default published or draft version of the document.

        Args:
            collection: Collection API id (e.g. ``"articles"``)
            document_id: Strapi v5 ``documentId`` (or numeric id)

        Returns:
            True if a published or draft version is readable

        Raises:
            ValidationError: Draft probe 400 that is not an unknown
                ``status`` / ``publicationState``
        """
        endpoint = self._single_segment_document_path(collection, document_id)
        try:
            response = await self.get_one(endpoint)
            return self._entity_identifies_document(response.data)
        except NotFoundError:
            pass

        try:
            response = await self.get_one(endpoint, query=self._draft_status_query())
        except NotFoundError:
            return False
        except ValidationError as error:
            if is_unknown_status_param(error):
                return False
            raise
        return self._entity_identifies_document(response.data)

    async def _probe_document_entity(
        self, endpoint: str, query: StrapiQuery | None
    ) -> NormalizedEntity | None:
        """GET existence probe. HTTP 404 or an unidentified body is absent."""
        try:
            response = await self.get_one(endpoint, query=query)
        except NotFoundError:
            return None
        if self._entity_identifies_document(response.data):
            return response.data
        return None

    async def _classify_write_404(
        self,
        endpoint: str,
        original: NotFoundError,
        *,
        write_query: StrapiQuery | None = None,
    ) -> NoReturn:
        """Probe the write's own params, then draft; never mask the original error.

        A probe HTTP 404 is an answer (that variant is absent), not a
        failed probe. Other probe errors re-raise ``original``.
        """
        try:
            write_entity = await self._probe_document_entity(endpoint, write_query)
        except Exception:
            raise original from None
        if write_entity is not None:
            self._reraise_classified_write_404(original, write_entity)
        if self._write_query_is_draft(write_query):
            raise original
        try:
            await self._probe_document_entity(endpoint, self._draft_status_query())
        except Exception:
            raise original from None
        raise original

    async def publish(
        self,
        collection: str,
        document_id: str,
        query: StrapiQuery | None = None,
        headers: dict[str, str] | None = None,
    ) -> NormalizedSingleResponse:
        """Publish a Strapi v5 draft via stock REST.

        PUT ``/api/{collection}/{documentId}?status=published`` with
        ``{"data": {}}``. Stock Strapi 5 does not register
        ``POST /actions/publish``.

        Args:
            collection: Collection API id (e.g. ``"articles"``)
            document_id: Strapi v5 ``documentId``
            query: Optional query (populate / fields after publish)
            headers: Additional headers

        Returns:
            Normalized published entity
        """
        path, params = self._publish_put_args(collection, document_id, query)
        raw_response = await self.put(path, json={"data": {}}, params=params, headers=headers)
        self._require_write_data_object(raw_response)
        return self._parse_single_response(raw_response)

    async def unpublish(
        self,
        collection: str,
        document_id: str,
        query: StrapiQuery | None = None,
        headers: dict[str, str] | None = None,
    ) -> NormalizedSingleResponse:
        """Unpublish a Strapi v5 live document.

        POST ``/api/{collection}/{documentId}/actions/unpublish``.

        Stock Strapi 5 public REST does not register this route. This
        helper is for instances that add a custom document-action
        controller. There is no public REST unpublish.

        Args:
            collection: Collection API id (e.g. ``"articles"``)
            document_id: Strapi v5 ``documentId``
            query: Optional query (populate / fields after unpublish)
            headers: Additional headers

        Returns:
            Normalized unpublished entity
        """
        endpoint = self._document_action_endpoint(collection, document_id, DocumentAction.UNPUBLISH)
        params = query.to_query_params() if query else None
        raw_response = await self.post(endpoint, json={}, params=params, headers=headers)
        return self._parse_single_response(raw_response)

    async def discard_draft(
        self,
        collection: str,
        document_id: str,
        query: StrapiQuery | None = None,
        headers: dict[str, str] | None = None,
    ) -> NormalizedSingleResponse:
        """Discard a Strapi v5 draft and keep the published version.

        POST ``/api/{collection}/{documentId}/actions/discardDraft``.

        Stock Strapi 5 public REST does not register this route. This
        helper is for instances that add a custom document-action
        controller. There is no public REST discardDraft.

        Args:
            collection: Collection API id (e.g. ``"articles"``)
            document_id: Strapi v5 ``documentId``
            query: Optional query (populate / fields / locale)
            headers: Additional headers

        Returns:
            Normalized entity after the draft is discarded
        """
        endpoint = self._document_action_endpoint(
            collection, document_id, DocumentAction.DISCARD_DRAFT
        )
        params = query.to_query_params() if query else None
        raw_response = await self.post(endpoint, json={}, params=params, headers=headers)
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
            FileNotFoundError: If the local file does not exist.
            AuthenticationError: If the upload is unauthorized (401).
        