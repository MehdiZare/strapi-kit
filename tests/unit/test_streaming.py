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
from strapi_kit.models import DocumentStatus, FilterBuilder, PublicationState, StrapiQuery


@pytest.fixture
def strapi_config() -> StrapiConfig:
    """Create test configuration."""
    return StrapiConfig(
        base_url="http://localhost:1337",
        api_token="test-token",
    )


# Sync Streaming Tests


@pytest.mark.respx
def test_stream_entities_single_page(strapi_config: StrapiConfig, respx_mock: respx.Router) -> None:
    """Test streaming with single page of results."""
    respx_mock.get("http://localhost:1337/api/articles").mock(
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
        entities = list(stream_entities(client, "articles", page_size=100, include_drafts=False))

        assert len(entities) == 3
        assert entities[0].id == 1
        assert entities[1].id == 2
        assert entities[2].id == 3


@pytest.mark.respx
def test_stream_entities_multiple_pages(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Test streaming with multiple pages."""
    # Page 1
    respx_mock.get(
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
    respx_mock.get(
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
    respx_mock.get(
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
        entities = list(stream_entities(client, "articles", page_size=2, include_drafts=False))

        assert len(entities) == 5
        assert entities[0].id == 1
        assert entities[4].id == 5


@pytest.mark.respx
def test_stream_entities_empty_results(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Test streaming with no results."""
    respx_mock.get("http://localhost:1337/api/articles").mock(
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


@pytest.mark.respx
def test_stream_entities_with_query_filters(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Test streaming with query filters."""
    # Mock any GET to articles endpoint (filters will be in query params)
    respx_mock.get("http://localhost:1337/api/articles").mock(
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


@pytest.mark.respx
def test_stream_entities_no_pagination_metadata(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Missing pagination echo is a completeness error, not a silent stop."""
    respx_mock.get("http://localhost:1337/api/articles").mock(
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
        with pytest.raises(ValidationError, match="Pagination total is required"):
            list(stream_entities(client, "articles", include_drafts=False))


@pytest.mark.respx
def test_stream_entities_iteration_without_loading_all(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
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

    respx_mock.get("http://localhost:1337/api/articles").mock(side_effect=response_factory)

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


@pytest.mark.respx
async def test_async_stream_entities_single_page(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Test async streaming with single page."""
    respx_mock.get("http://localhost:1337/api/articles").mock(
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


@pytest.mark.respx
async def test_async_stream_entities_multiple_pages(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Test async streaming with multiple pages."""
    # Page 1
    respx_mock.get(
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
    respx_mock.get(
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
        async for entity in stream_entities_async(
            client, "articles", page_size=2, include_drafts=False
        ):
            entities.append(entity)

        assert len(entities) == 4
        assert entities[0].id == 1
        assert entities[3].id == 4


@pytest.mark.respx
async def test_async_stream_entities_empty_results(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Test async streaming with no results."""
    respx_mock.get("http://localhost:1337/api/articles").mock(
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


@pytest.mark.respx
def test_stream_continues_when_page_count_missing(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """A matching echo with total but no pageCount must not stop after page 1."""
    respx_mock.get(
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
                "meta": {"pagination": {"page": 1, "pageSize": 2, "total": 3}},
            },
        )
    )
    respx_mock.get(
        "http://localhost:1337/api/articles",
        params={"pagination[page]": 2, "pagination[pageSize]": 2, "pagination[withCount]": True},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 3, "documentId": "doc3", "title": "Article 3"}],
                "meta": {"pagination": {"page": 2, "pageSize": 2, "total": 3}},
            },
        )
    )

    with SyncClient(strapi_config) as client:
        entities = list(stream_entities(client, "articles", page_size=2, include_drafts=False))

    assert [entity.id for entity in entities] == [1, 2, 3]


@pytest.mark.respx
def test_stream_stops_on_total_when_page_count_is_low(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """pageCount must not win over total (#81)."""
    respx_mock.get(
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
                "meta": {"pagination": {"page": 1, "pageSize": 2, "pageCount": 1, "total": 3}},
            },
        )
    )
    respx_mock.get(
        "http://localhost:1337/api/articles",
        params={"pagination[page]": 2, "pagination[pageSize]": 2, "pagination[withCount]": True},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 3, "documentId": "doc3", "title": "Article 3"}],
                "meta": {"pagination": {"page": 2, "pageSize": 2, "pageCount": 1, "total": 3}},
            },
        )
    )

    with SyncClient(strapi_config) as client:
        entities = list(stream_entities(client, "articles", page_size=2, include_drafts=False))

    assert [entity.id for entity in entities] == [1, 2, 3]


@pytest.mark.respx
def test_stream_capped_page_size_raises(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Echo pageSize smaller than the requested window is a completeness error."""
    respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 1, "documentId": "doc1", "title": "Article 1"}],
                "meta": {"pagination": {"page": 1, "pageSize": 25, "pageCount": 4, "total": 100}},
            },
        )
    )

    with SyncClient(strapi_config) as client:
        with pytest.raises(ValidationError, match="pageSize"):
            list(stream_entities(client, "articles", page_size=100, include_drafts=False))


@pytest.mark.respx
def test_stream_defaults_to_status_draft(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """v5 stream/export completeness requests status=draft by default."""
    route = respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 1, "documentId": "doc1", "title": "Draft"}],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )

    with SyncClient(strapi_config) as client:
        entities = list(stream_entities(client, "articles"))

    assert len(entities) == 1
    assert route.calls.last.request.url.params["status"] == "draft"


@pytest.mark.respx
def test_stream_include_drafts_false_omits_status(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Opt out keeps published-only REST (omitted status=)."""
    route = respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 1, "documentId": "doc1", "title": "Live"}],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )

    with SyncClient(strapi_config) as client:
        list(stream_entities(client, "articles", include_drafts=False))

    assert "status" not in route.calls.last.request.url.params


@pytest.mark.respx
def test_stream_does_not_override_caller_document_status(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """An explicit with_document_status is left alone."""
    route = respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 1, "documentId": "doc1", "title": "Live"}],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )
    query = StrapiQuery().with_document_status(DocumentStatus.PUBLISHED)

    with SyncClient(strapi_config) as client:
        list(stream_entities(client, "articles", query=query))

    assert route.calls.last.request.url.params["status"] == "published"


@pytest.mark.respx
def test_stream_does_not_mutate_caller_query(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Default status=draft is applied to a copy, not the caller's query."""
    respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 1, "documentId": "doc1", "title": "Draft"}],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )
    query = StrapiQuery()

    with SyncClient(strapi_config) as client:
        list(stream_entities(client, "articles", query=query))

    assert "status" not in query.to_query_params()


@pytest.mark.respx
def test_stream_v4_never_sends_status(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Explicit v4 clients omit status= even when include_drafts is True."""
    v4_config = StrapiConfig(
        base_url=strapi_config.base_url,
        api_token=strapi_config.api_token,
        api_version="v4",
    )
    route = respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 1,
                        "attributes": {"title": "Live"},
                    }
                ],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )

    with SyncClient(v4_config) as client:
        list(stream_entities(client, "articles"))

    assert "status" not in route.calls.last.request.url.params


@pytest.mark.respx
def test_stream_does_not_override_caller_publication_state(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """A v4 publicationState query must not mix with default status=draft."""
    route = respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 1,
                        "attributes": {"title": "Preview"},
                    }
                ],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )
    query = StrapiQuery().with_publication_state(PublicationState.PREVIEW)

    with SyncClient(strapi_config) as client:
        list(stream_entities(client, "articles", query=query))

    params = route.calls.last.request.url.params
    assert params["publicationState"] == "preview"
    assert "status" not in params


@pytest.mark.respx
async def test_async_stream_defaults_to_status_draft(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Async streamer uses the same v5 completeness default."""
    route = respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 1, "documentId": "doc1", "title": "Draft"}],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )

    async with AsyncClient(strapi_config) as client:
        entities = [entity async for entity in stream_entities_async(client, "articles")]

    assert len(entities) == 1
    assert route.calls.last.request.url.params["status"] == "draft"


@pytest.mark.respx
def test_stream_empty_later_page_raises(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """An empty page 2 must not silently truncate a collection."""
    respx_mock.get(
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
                "meta": {"pagination": {"page": 1, "pageSize": 2, "pageCount": 3, "total": 5}},
            },
        )
    )
    respx_mock.get(
        "http://localhost:1337/api/articles",
        params={"pagination[page]": 2, "pagination[pageSize]": 2, "pagination[withCount]": True},
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [],
                "meta": {"pagination": {"page": 2, "pageSize": 2, "pageCount": 3, "total": 5}},
            },
        )
    )

    with SyncClient(strapi_config) as client:
        with pytest.raises(ValidationError, match="Empty page"):
            list(stream_entities(client, "articles", page_size=2, include_drafts=False))


@pytest.mark.respx
def test_stream_empty_first_page_with_nonzero_total_raises(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Empty first page + total>0 is a completeness error, not an empty collection."""
    respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 5, "total": 500}},
            },
        )
    )

    with SyncClient(strapi_config) as client:
        with pytest.raises(ValidationError, match="Empty first page"):
            list(stream_entities(client, "articles", include_drafts=False))


@pytest.mark.respx
def test_stream_retries_without_status_when_draft_param_rejected(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Draft & Publish off: drop default status=draft and retry the first page."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("status") == "draft":
            return httpx.Response(
                400,
                json={"error": {"message": "Invalid key status", "name": "ValidationError"}},
            )
        return httpx.Response(
            200,
            json={
                "data": [{"id": 1, "documentId": "doc1", "title": "Live"}],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )

    route = respx_mock.get("http://localhost:1337/api/articles").mock(side_effect=handler)

    with SyncClient(strapi_config) as client:
        entities = list(stream_entities(client, "articles"))

    assert len(entities) == 1
    assert route.call_count == 2
    assert route.calls[0].request.url.params["status"] == "draft"
    assert "status" not in route.calls[1].request.url.params
