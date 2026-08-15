"""Streaming pagination utilities for large result sets.

This module provides generators that automatically handle pagination,
allowing memory-efficient iteration over large datasets.
"""

from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING, Any

from ..exceptions import ValidationError
from ..models import StrapiQuery
from ..models.enums import DocumentStatus
from ..models.response.normalized import NormalizedEntity
from ..models.response.pagination import PaginationEchoMeta, assert_pagination_echo

if TYPE_CHECKING:
    from ..client.async_client import AsyncClient
    from ..client.sync_client import SyncClient


def _with_default_draft_status(
    query: StrapiQuery,
    client: Any,
    include_drafts: bool,
) -> tuple[StrapiQuery, bool]:
    """Apply ``status=draft`` for v5 completeness unless the caller set status.

    Returns the query and whether this helper added ``status=draft`` so a
    first-page ``ValidationError`` (Draft & Publish off) can drop it.
    """
    if not include_drafts:
        return query, False
    if query.document_status is not None or query.publication_state is not None:
        return query, False
    version = client.api_version or client.config.api_version
    if version == "v4":
        return query, False
    return query.with_document_status(DocumentStatus.DRAFT), True


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
    include_drafts: bool = True,
) -> Generator[NormalizedEntity, None, None]:
    """Stream entities from endpoint with automatic pagination.

    This generator automatically fetches pages as needed, yielding
    entities one at a time without loading the entire dataset into memory.

    On Strapi 5, omitted ``status=`` means published, which hides
    never-published documents. ``include_drafts=True`` (the default)
    sets ``status=draft`` unless the caller already set a document
    status or a v4 publication state. That requests the **draft
    version** of each document (published-plus-pending-edits, not a
    union of published and draft rows). Pass ``include_drafts=False``
    for published-only. Explicit ``api_version="v4"`` never sends
    ``status=`` (v4 uses ``publicationState``; that mapping is not
    applied here). ``api_version="auto"`` sends ``status=draft`` so
    the first page is complete on v5 before version detection.

    Each page is checked with :func:`assert_pagination_echo`. The
    stream stops after ``total`` items (or raises if the echo is
    missing, unreadable, silently capped, or a later page is empty
    while ``total`` is still unmet). An empty first page with
    ``total == 0`` is a complete empty collection. ``get_many()``
    itself does not call the helper. If the default ``status=draft``
    400s (Draft & Publish off), the first page is retried without
    ``status=``.

    Args:
        client: SyncClient instance
        endpoint: API endpoint (e.g., "articles")
        query: Optional query (filters, sorts, populate, etc.)
        page_size: Items per page (default: 100)
        include_drafts: If True (default), request ``status=draft`` on
            v5 so unpublished documents are included. This selects the
            draft version of each document.

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
    base_query, applied_default_draft = _with_default_draft_status(
        caller_query.copy(), client, include_drafts
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
    include_drafts: bool = True,
) -> AsyncGenerator[NormalizedEntity, None]:
    """Async version of stream_entities.

    This async generator automatically fetches pages as needed, yielding
    entities one at a time without loading the entire dataset into memory.

    On Strapi 5, ``include_drafts=True`` (default) sets ``status=draft``
    unless the caller already set a document status. See
    :func:`stream_entities`.

    Args:
        client: AsyncClient instance
        endpoint: API endpoint (e.g., "articles")
        query: Optional query (filters, sorts, populate, etc.)
        page_size: Items per page (default: 100)
        include_drafts: If True (default), request ``status=draft`` on
            v5 so unpublished documents are included. This selects the
            draft version of each document.

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
    base_query, applied_default_draft = _with_default_draft_status(
        caller_query.copy(), client, include_drafts
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

        if _should_stop_after_page(
            data_len=len(response.data),
            yielded=yielded,
            current_page=current_page,
            page_size=page_size,
            meta=response.meta,
        ):
            break

        current_page += 1
