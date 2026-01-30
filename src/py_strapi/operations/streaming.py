"""Streaming pagination utilities for large result sets.

This module provides generators that automatically handle pagination,
allowing memory-efficient iteration over large datasets.
"""

from collections.abc import AsyncGenerator, Generator
from typing import TYPE_CHECKING

from ..models import StrapiQuery
from ..models.response.normalized import NormalizedEntity

if TYPE_CHECKING:
    from ..client.async_client import AsyncClient
    from ..client.sync_client import SyncClient


def stream_entities(
    client: "SyncClient",
    endpoint: str,
    query: StrapiQuery | None = None,
    page_size: int = 100,
) -> Generator[NormalizedEntity, None, None]:
    """Stream entities from endpoint with automatic pagination.

    This generator automatically fetches pages as needed, yielding
    entities one at a time without loading the entire dataset into memory.

    Args:
        client: SyncClient instance
        endpoint: API endpoint (e.g., "articles")
        query: Optional query (filters, sorts, populate, etc.)
        page_size: Items per page (default: 100)

    Yields:
        NormalizedEntity objects one at a time

    Example:
        >>> with SyncClient(config) as client:
        ...     for article in stream_entities(client, "articles", page_size=50):
        ...         print(article.attributes["title"])
        ...         # Process one at a time without loading all into memory
    """
    current_page = 1

    # Build base query
    if query is None:
        query = StrapiQuery()

    while True:
        # Update pagination for current page
        page_query = query.paginate(page=current_page, page_size=page_size)

        # Fetch page
        response = client.get_many(endpoint, query=page_query)

        # Yield each entity
        yield from response.data

        # Check if more pages exist
        if response.meta and response.meta.pagination:
            total_pages = response.meta.pagination.page_count
            if total_pages and current_page >= total_pages:
                break
        else:
            # No pagination metadata, assume single page
            break

        current_page += 1


async def stream_entities_async(
    client: "AsyncClient",
    endpoint: str,
    query: StrapiQuery | None = None,
    page_size: int = 100,
) -> AsyncGenerator[NormalizedEntity, None]:
    """Async version of stream_entities.

    This async generator automatically fetches pages as needed, yielding
    entities one at a time without loading the entire dataset into memory.

    Args:
        client: AsyncClient instance
        endpoint: API endpoint (e.g., "articles")
        query: Optional query (filters, sorts, populate, etc.)
        page_size: Items per page (default: 100)

    Yields:
        NormalizedEntity objects one at a time

    Example:
        >>> async with AsyncClient(config) as client:
        ...     async for article in stream_entities_async(client, "articles"):
        ...         print(article.attributes["title"])
        ...         # Process asynchronously without loading all into memory
    """
    current_page = 1

    # Build base query
    if query is None:
        query = StrapiQuery()

    while True:
        # Update pagination for current page
        page_query = query.paginate(page=current_page, page_size=page_size)

        # Fetch page
        response = await client.get_many(endpoint, query=page_query)

        # Yield each entity
        for entity in response.data:
            yield entity

        # Check if more pages exist
        if response.meta and response.meta.pagination:
            total_pages = response.meta.pagination.page_count
            if total_pages and current_page >= total_pages:
                break
        else:
            # No pagination metadata, assume single page
            break

        current_page += 1
