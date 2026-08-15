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
from ..utils.pagination import assert_pagination_echo

if TYPE_CHECKING:
    from ..client.async_client import AsyncClient
    from ..client.sync_client import SyncClient


def _with_default_draft_status(
    query: StrapiQuery,
    client: Any,
    include_drafts: bool,
) -> StrapiQuery:
    """Apply ``status=draft`` for v5 completeness unless the caller set status."""
    if not include_drafts:
        return query
    if query._document_status is not None or query._publication_state is not None:
        return query
    version = client.api_version or client.config.api_version
    if version == "v4":
        return query
    return query.with_document_status(DocumentStatus.DRAFT)


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
    status or a v4 publication state. Pass ``include_drafts=False``
    for published-only. v4 clients never send ``status=``.

    Each page is checked with :func:`assert_pagination_echo`. The
    stream stops after ``total`` items (or raises if the echo is
    missing, unreadable, or silently capped). ``get_many()`` itself
    does not call the helper.

    Args:
        client: SyncClient instance
        endpoint: API endpoint (e.g., "articles")
        query: Optional query (filters, sorts, populate, etc.)
        page_size: Items per page (default: 100)
        include_drafts: If True (default), request ``status=draft`` on
            v5 so unpublished documents are included.

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
    base_query = query.copy() if query is not None else StrapiQuery()
    base_query = _with_default_draft_status(base_query, client, include_drafts)

    while True:
        # Update pagination for current page on a copy
        page_query = base_query.copy().paginate(page=current_page, page_size=page_size)

        # Fetch page
        response = client.get_many(endpoint, query=page_query)

        # Yield each entity
        yield from response.data
        yielded += len(response.data)

        if not response.data:
            break

        total = assert_pagination_echo(
            response.meta,
            requested_page=current_page,
            requested_page_size=page_size,
        )
        if yielded >= total or current_page * page_size >= total:
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
            v5 so unpublished documents are included.

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
    base_query = query.copy() if query is not None else StrapiQuery()
    base_query = _with_default_draft_status(base_query, client, include_drafts)

    while True:
        # Update pagination for current page on a copy
        page_query = base_query.copy().paginate(page=current_page, page_size=page_size)

        # Fetch page
        response = await client.get_many(endpoint, query=page_query)

        # Yield each entity
        for entity in response.data:
            yield entity
        yielded += len(response.data)

        if not response.data:
            break

        total = assert_pagination_echo(
            response.meta,
            requested_page=current_page,
            requested_page_size=page_size,
        )
        if yielded >= total or current_page * page_size >= total:
            break

        current_page += 1
