"""Streaming pagination utilities for large result sets.

This module provides generators that automatically handle pagination,
allowing memory-efficient iteration over large datasets.
"""

from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, Any

from ..exceptions import ValidationError
from ..models import StrapiQuery
from ..models.enums import DocumentStatus, PublicationState
from ..models.response.normalized import NormalizedEntity
from ..models.response.pagination import PaginationEchoMeta, assert_pagination_echo

if TYPE_CHECKING:
    from ..client.async_client import AsyncClient
    from ..client.sync_client import SyncClient


def _apply_stream_document_status(
    query: StrapiQuery,
    client: Any,
    document_status: DocumentStatus | None,
) -> tuple[StrapiQuery, bool]:
    """Apply the stream version contract unless the caller already set one.

    v5 / auto: ``status=``. Confirmed v4: ``publicationState=`` (preview for
    draft completeness, live for published). Never sends ``status=`` on a
    confirmed v4 client.

    Returns the query and whether this helper applied a default so a
    first-page ``ValidationError`` (Draft & Publish off) can drop it.
    """
    if document_status is None:
        return query, False
    if query.document_status is not None or query.publication_state is not None:
        return query, False
    version = client.api_version or client.config.api_version
    if version == "v4":
        state = (
            PublicationState.PREVIEW
            if document_status is DocumentStatus.DRAFT
            else PublicationState.LIVE
        )
        return query.with_publication_state(state), True
    return query.with_document_status(document_status), True


def _reconcile_v4_after_detect(
    caller_query: StrapiQuery,
    client: Any,
    document_status: DocumentStatus | None,
) -> tuple[StrapiQuery, bool]:
    """After the first page, drop ``status=`` if the client is now v4."""
    if document_status is None or client.api_version != "v4":
        return caller_query, False
    if caller_query.document_status is not None or caller_query.publication_state is not None:
        return caller_query, False
    return _apply_stream_document_status(caller_query.copy(), client, document_status)


def _should_stop_after_page(
    *,
    data_len: int,
    yielded: int,
    current_page: int,
    page_size: int,
    meta: PaginationEchoMeta | None,
) -> bool:
    """Return True when the stream is complete; raise if a page is truncated."""
    if data_len == 0:
        if current_page == 1:
            if meta is None:
                return True
            total = assert_pagination_echo(
                meta,
                requested_page=current_page,
                requested_page_size=page_size,
            )
            if total == 0:
                return True
            raise ValidationError(
                "Empty first page but pagination total is non-zero",
                details={"total": total, "page": current_page},
            )
        raise ValidationError(
            "Empty page before pagination total was reached",
            details={"page": current_page, "yielded": yielded},
        )
    total = assert_pagination_echo(
        meta,
        requested_page=current_page,
        requested_page_size=page_size,
    )
    return yielded >= total or current_page * page_size >= total


def stream_entities(
    client: "SyncClient",
    endpoint: str,
    query: StrapiQuery | None = None,
    page_size: int = 100,
    *,
    document_status: DocumentStatus | None = DocumentStatus.DRAFT,
) -> Generator[NormalizedEntity, None, None]:
    """Stream entities from endpoint with automatic pagination.

    This generator automatically fetches pages as needed, yielding
    entities one at a time without loading the entire dataset into memory.

    ``document_status`` defaults to :attr:`DocumentStatus.DRAFT` so
    unpublished documents are not skipped. On v5 that is ``status=draft``
    (the **draft version** of each document, not a published∪draft
    union). On a confirmed v4 client it is ``publicationState=preview``.
    Pass ``document_status=None`` to omit both params (v5 published-only).
    ``DocumentStatus.PUBLISHED`` sends ``status=published`` / v4
    ``publicationState=live``. A caller query that already set
    ``status=`` or ``publicationState=`` is left alone.

    ``api_version="auto"`` may send ``status=draft`` on the first page
    before detection. After a v4 detect, later pages use
    ``publicationState`` and never ``status=``. If the applied default
    400s (Draft & Publish off), the first page is retried without it.

    Each page is checked with :func:`assert_pagination_echo`. The
    stream stops after ``total`` items (or raises if the echo is
    missing, unreadable, silently capped, or a later page is empty
    while ``total`` is still unmet). An empty first page with
    ``total == 0`` is a complete empty collection. ``get_many()``
    itself does not call the helper.

    Args:
        client: SyncClient instance
        endpoint: API endpoint (e.g., "articles")
        query: Optional query (filters, sorts, populate, etc.)
        page_size: Items per page (default: 100)
        document_status: Version to request. Default draft completeness.
            ``None`` omits ``status=`` / ``publicationState=``.

    Yields:
        NormalizedEntity objects one at a time

    Raises:
        ValidationError: If page_size < 1, or if pagination echo is
            missing, capped, or unreadable.

    Example:
        >>> with SyncClient(config) as client:
        ...     for article in stream_entities(client, "articles", page_size=50):
        ...         print(article.attributes["title"])
        ...         # Process one at a time without loading all into memory
    """
    if page_size < 1:
        raise ValidationError("page_size must be >= 1")

    current_page = 1
    yielded = 0

    # Build base query - create copy to avoid mutating caller's query
    caller_query = query.copy() if query is not None else StrapiQuery()
    base_query, applied_default_draft = _apply_stream_document_status(
        caller_query.copy(), client, document_status
    )

    while True:
        # Update pagination for current page on a copy
        page_query = base_query.copy().paginate(page=current_page, page_size=page_size)

        try:
            response = client.get_many(endpoint, query=page_query)
        except ValidationError:
            if current_page == 1 and applied_default_draft:
                # D&P-off / unknown status= — retry without the default.
                base_query = caller_query.copy()
                applied_default_draft = False
                continue
            raise

        yield from response.data
        yielded += len(response.data)

        if current_page == 1 and applied_default_draft:
            reconciled, still_applied = _reconcile_v4_after_detect(
                caller_query.copy(), client, document_status
            )
            base_query = reconciled
            applied_default_draft = still_applied

        if _should_stop_after_page(
            data_len=len(response.data),
            yielded=yielded,
            current_page=current_page,
            page_size=page_size,
            meta=response.meta,
        ):
            break

        current_page += 1


async def stream_entities_async(
    client: "AsyncClient",
    endpoint: str,
    query: StrapiQuery | None = None,
    page_size: int = 100,
    *,
    document_status: DocumentStatus | None = DocumentStatus.DRAFT,
) -> AsyncGenerator[NormalizedEntity, None]:
    """Async version of stream_entities.

    This async generator automatically fetches pages as needed, yielding
    entities one at a time without loading the entire dataset into memory.

    See :func:`stream_entities` for the ``document_status`` contract.

    Args:
        client: AsyncClient instance
        endpoint: API endpoint (e.g., "articles")
        query: Optional query (filters, sorts, populate, etc.)
        page_size: Items per page (default: 100)
        document_status: Version to request. Default draft completeness.
            ``None`` omits ``status=`` / ``publicationState=``.

    Yields:
        NormalizedEntity objects one at a time

    Raises:
        ValidationError: If page_size < 1, or if pagination echo is
            missing, capped, or unreadable.

    Example:
        >>> async with AsyncClient(config) as client:
        ...     async for article in stream_entities_async(client, "articles"):
        ...         print(article.attributes["title"])
        ...         # Process asynchronously without loading all into memory
    """
    if page_size < 1:
        raise ValidationError("page_size must be >= 1")

    current_page = 1
    yielded = 0

    # Build base query - create copy to avoid mutating caller's query
    caller_query = query.copy() if query is not None else StrapiQuery()
    base_query, applied_default_draft = _apply_stream_document_status(
        caller_query.copy(), client, document_status
    )

    while True:
        # Update pagination for current page on a copy
        page_query = base_query.copy().paginate(page=current_page, page_size=page_size)

        try:
            response = await client.get_many(endpoint, query=page_query)
        except ValidationError:
            if current_page == 1 and applied_default_draft:
                base_query = caller_query.copy()
                applied_default_draft = False
                continue
            raise

        for entity in response.data:
            yield entity
        yielded += len(response.data)

        if current_page == 1 and applied_default_draft:
            reconciled, still_applied = _reconcile_v4_after_detect(
                caller_query.copy(), client, document_status
            )
            base_query = reconciled
            applied_default_draft = still_applied

        if _should_stop_after_page(
            data_len=len(response.data),
            yielded=yielded,
            current_page=current_page,
            page_size=page_size,
            meta=response.meta,
        ):
            break

        current_page += 1
