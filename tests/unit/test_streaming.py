"""Tests for streaming pagination."""

import httpx
import pytest
import respx

from strapi_kit import (
    AsyncClient,
    StrapiConfig,
    ValidationError,
    stream_entities,
    stream_entities_async,
)
from strapi_kit.client.sync_client import SyncClient
from strapi_kit.models import FilterBuilder, StrapiQuery


@pytest.fixture
def strapi_config() -> StrapiConfig:
    """Create test configuration."""
    return StrapiConfig(
        base_url="http://localhost:1337",
        api_token="test-token",
    )


# Sync Streaming Tests


@respx.mock
def test_stream_entities_single_page(strapi_config: StrapiConfig) -> None:
    """Test streaming with single page of results."""
    respx.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": 1, "documentId": "doc1", "title": "Article 1"},
                    {"id": 2, "documentId": "doc2", "title": "Article 2"},
                    {"id": 3, "documentId": "doc3", "title": "Article 3"},
                ],
                "meta": {
                    "pagination": {
                        "page": 1,
                        "pageSize": 100,
                        "pageCount": 1,
                        "total": 3,
                    }
                },
            },
        )
    )

    with SyncClient(strapi_config) as client:
        entities = list(stream_entities(client, "articles", page_size=100))

        assert len(entities) == 3
        assert entities[0].id == 1
        assert entities[1].id == 2
        assert entities[2].id == 3


@respx.mock
def test_stream_entities_multiple_pages(strapi_config: StrapiConfig) -> None:
    """Test streaming with multiple pages."""
    # Page 1
    respx.get(
        "http://localhost:1337/api/articles",
        params={"pagination[page]": 1, "pagination[pageSize]": 2, "pagination[withCount]": True},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": 1, "documentId": "doc1", "title": "Article 1"},
                    {"id": 2, "documentId": "doc2", "title": "Article 2"},
                ],
                "meta": {
                    "pagination": {
                        "page": 1,
                        "pageSize": 2,
                        "pageCount": 3,
                        "total": 5,
                    }
                },
            },
        )
    )

    # Page 2
    respx.get(
        "http://localhost:1337/api/articles",
        params={"pagination[page]": 2, "pagination[pageSize]": 2, "pagination[withCount]": True},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": 3, "documentId": "doc3", "title": "Article 3"},
                    {"id": 4, "documentId": "doc4", "title": "Article 4"},
                ],
                "meta": {
                    "pagination": {
                        "page": 2,
                        "pageSize": 2,
                        "pageCount": 3,
                        "total": 5,
                    }
                },
            },
        )
    )

    # Page 3
    respx.get(
        "http://localhost:1337/api/articles",
        params={"pagination[page]": 3, "pagination[pageSize]": 2, "pagination[withCount]": True},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": 5, "documentId": "doc5", "title": "Article 5"},
                ],
                "meta": {
                    "pagination": {
                        "page": 3,
                        "pageSize": 2,
                        "pageCount": 3,
                        "total": 5,
                    }
                },
            },
        )
    )

    with SyncClient(strapi_config) as client:
        entities = list(stream_entities(client, "articles", page_size=2))

        assert len(entities) == 5
        assert entities[0].id == 1
        assert entities[4].id == 5


@respx.mock
def test_stream_entities_empty_results(strapi_config: StrapiConfig) -> None:
    """Test streaming with no results."""
    respx.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [],
                "meta": {
                    "pagination": {
                        "page": 1,
                        "pageSize": 100,
                        "pageCount": 1,
                        "total": 0,
                    }
                },
            },
        )
    )

    with SyncClient(strapi_config) as client:
        entities = list(stream_entities(client, "articles"))

        assert len(entities) == 0


@respx.mock
def test_stream_entities_with_query_filters(strapi_config: StrapiConfig) -> None:
    """Test streaming with query filters."""
    # Mock any GET to articles endpoint (filters will be in query params)
    respx.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": 1, "documentId": "doc1", "title": "Article 1", "status": "published"},
                ],
                "meta": {
                    "pagination": {
                        "page": 1,
                        "pageSize": 100,
                        "pageCount": 1,
                        "total": 1,
                    }
                },
            },
        )
    )

    query = StrapiQuery().filter(FilterBuilder().eq("status", "published"))

    with SyncClient(strapi_config) as client:
        entities = list(stream_entities(client, "articles", query=query, page_size=100))

        assert len(entities) == 1
        assert entities[0].attributes["status"] == "published"


@respx.mock
def test_stream_entities_no_pagination_metadata(strapi_config: StrapiConfig) -> None:
    """Test streaming when response has no pagination metadata."""
    respx.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": 1, "documentId": "doc1", "title": "Article 1"},
                ],
            },
        )
    )

    with SyncClient(strapi_config) as client:
        entities = list(stream_entities(client, "articles"))

        # Should get results and stop (no pagination)
        assert len(entities) == 1


@respx.mock
def test_stream_entities_iteration_without_loading_all(strapi_config: StrapiConfig) -> None:
    """Test that streaming doesn't load all data at once (generator behavior)."""
    call_count = 0

    def response_factory(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        page = int(request.url.params.get("pagination[page]", 1))

        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": page, "documentId": f"doc{page}", "title": f"Article {page}"},
                ],
                "meta": {
                    "pagination": {
                        "page": page,
                        "pageSize": 1,
                        "pageCount": 3,
                        "total": 3,
                    }
                },
            },
        )

    respx.get("http://localhost:1337/api/articles").mock(side_effect=response_factory)

    with SyncClient(strapi_config) as client:
        gen = stream_entities(client, "articles", page_size=1)

        # First next() should fetch first page
        first = next(gen)
        assert call_count == 1
        assert first.id == 1

        # Second next() should fetch second page
        second = next(gen)
        assert call_count == 2
        assert second.id == 2

        # Third next() should fetch third page
        third = next(gen)
        assert call_count == 3
        assert third.id == 3


# Async Streaming Tests


@pytest.mark.asyncio
@respx.mock
async def test_async_stream_entities_single_page(strapi_config: StrapiConfig) -> None:
    """Test async streaming with single page."""
    respx.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": 1, "documentId": "doc1", "title": "Article 1"},
                    {"id": 2, "documentId": "doc2", "title": "Article 2"},
                ],
                "meta": {
                    "pagination": {
                        "page": 1,
                        "pageSize": 100,
                        "pageCount": 1,
                        "total": 2,
                    }
                },
            },
        )
    )

    async with AsyncClient(strapi_config) as client:
        entities = []
        async for entity in stream_entities_async(client, "articles"):
            entities.append(entity)

        assert len(entities) == 2
        assert entities[0].id == 1
        assert entities[1].id == 2


@pytest.mark.asyncio
@respx.mock
async def test_async_stream_entities_multiple_pages(strapi_config: StrapiConfig) -> None:
    """Test async streaming with multiple pages."""
    # Page 1
    respx.get(
        "http://localhost:1337/api/articles",
        params={"pagination[page]": 1, "pagination[pageSize]": 2, "pagination[withCount]": True},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": 1, "documentId": "doc1", "title": "Article 1"},
                    {"id": 2, "documentId": "doc2", "title": "Article 2"},
                ],
                "meta": {
                    "pagination": {
                        "page": 1,
                        "pageSize": 2,
                        "pageCount": 2,
                        "total": 4,
                    }
                },
            },
        )
    )

    # Page 2
    respx.get(
        "http://localhost:1337/api/articles",
        params={"pagination[page]": 2, "pagination[pageSize]": 2, "pagination[withCount]": True},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": 3, "documentId": "doc3", "title": "Article 3"},
                    {"id": 4, "documentId": "doc4", "title": "Article 4"},
                ],
                "meta": {
                    "pagination": {
                        "page": 2,
                        "pageSize": 2,
                        "pageCount": 2,
                        "total": 4,
                    }
                },
            },
        )
    )

    async with AsyncClient(strapi_config) as client:
        entities = []
        async for entity in stream_entities_async(client, "articles", page_size=2):
            entities.append(entity)

        assert len(entities) == 4
        assert entities[0].id == 1
        assert entities[3].id == 4


@pytest.mark.asyncio
@respx.mock
async def test_async_stream_entities_empty_results(strapi_config: StrapiConfig) -> None:
    """Test async streaming with no results."""
    respx.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [],
                "meta": {
                    "pagination": {
                        "page": 1,
                        "pageSize": 100,
                        "pageCount": 1,
                        "total": 0,
                    }
                },
            },
        )
    )

    async with AsyncClient(strapi_config) as client:
        entities = []
        async for entity in stream_entities_async(client, "articles"):
            entities.append(entity)

        assert len(entities) == 0


# Page size validation tests


def test_stream_entities_page_size_zero_raises_error(strapi_config: StrapiConfig) -> None:
    """Test that page_size=0 raises ValidationError."""
    with SyncClient(strapi_config) as client:
        with pytest.raises(ValidationError, match="page_size must be >= 1"):
            list(stream_entities(client, "articles", page_size=0))


def test_stream_entities_page_size_negative_raises_error(strapi_config: StrapiConfig) -> None:
    """Test that negative page_size raises ValidationError."""
    with SyncClient(strapi_config) as client:
        with pytest.raises(ValidationError, match="page_size must be >= 1"):
            list(stream_entities(client, "articles", page_size=-5))


@pytest.mark.asyncio
async def test_async_stream_entities_page_size_zero_raises_error(
    strapi_config: StrapiConfig,
) -> None:
    """Test that page_size=0 raises ValidationError for async."""
    async with AsyncClient(strapi_config) as client:
        with pytest.raises(ValidationError, match="page_size must be >= 1"):
            async for _ in stream_entities_async(client, "articles", page_size=0):
                pass


@pytest.mark.asyncio
async def test_async_stream_entities_page_size_negative_raises_error(
    strapi_config: StrapiConfig,
) -> None:
    """Test that negative page_size raises ValidationError for async."""
    async with AsyncClient(strapi_config) as client:
        with pytest.raises(ValidationError, match="page_size must be >= 1"):
            async for _ in stream_entities_async(client, "articles", page_size=-10):
                pass
