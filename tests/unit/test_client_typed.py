"""Tests for typed client methods with normalized responses."""


import httpx
import pytest
import respx

from py_strapi.client.async_client import AsyncClient
from py_strapi.client.sync_client import SyncClient
from py_strapi.models import FilterBuilder, SortDirection, StrapiQuery
from py_strapi.models.config import StrapiConfig


@pytest.fixture
def strapi_config() -> StrapiConfig:
    """Create test Strapi configuration."""
    return StrapiConfig(base_url="http://localhost:1337", api_token="test-token-12345678")


@pytest.fixture
def mock_v4_single_response() -> dict:
    """Mock v4 single entity response."""
    return {
        "data": {
            "id": 1,
            "attributes": {
                "title": "Test Article",
                "content": "Article content",
                "views": 100,
                "createdAt": "2024-01-01T00:00:00.000Z",
                "updatedAt": "2024-01-02T00:00:00.000Z",
                "publishedAt": "2024-01-03T00:00:00.000Z",
                "locale": "en",
            },
        },
        "meta": {},
    }


@pytest.fixture
def mock_v5_single_response() -> dict:
    """Mock v5 single entity response."""
    return {
        "data": {
            "id": 1,
            "documentId": "abc123",
            "title": "Test Article",
            "content": "Article content",
            "views": 100,
            "createdAt": "2024-01-01T00:00:00.000Z",
            "updatedAt": "2024-01-02T00:00:00.000Z",
            "publishedAt": "2024-01-03T00:00:00.000Z",
            "locale": "en",
        },
        "meta": {},
    }


@pytest.fixture
def mock_v4_collection_response() -> dict:
    """Mock v4 collection response."""
    return {
        "data": [
            {
                "id": 1,
                "attributes": {
                    "title": "First Article",
                    "content": "Content 1",
                    "createdAt": "2024-01-01T00:00:00.000Z",
                },
            },
            {
                "id": 2,
                "attributes": {
                    "title": "Second Article",
                    "content": "Content 2",
                    "createdAt": "2024-01-02T00:00:00.000Z",
                },
            },
        ],
        "meta": {"pagination": {"page": 1, "pageSize": 25, "pageCount": 1, "total": 2}},
    }


@pytest.fixture
def mock_v5_collection_response() -> dict:
    """Mock v5 collection response."""
    return {
        "data": [
            {
                "id": 1,
                "documentId": "abc123",
                "title": "First Article",
                "content": "Content 1",
                "createdAt": "2024-01-01T00:00:00.000Z",
            },
            {
                "id": 2,
                "documentId": "def456",
                "title": "Second Article",
                "content": "Content 2",
                "createdAt": "2024-01-02T00:00:00.000Z",
            },
        ],
        "meta": {"pagination": {"page": 1, "pageSize": 25, "pageCount": 1, "total": 2}},
    }


class TestSyncClientTyped:
    """Tests for typed sync client methods."""

    @respx.mock
    def test_get_one_v4(self, strapi_config: StrapiConfig, mock_v4_single_response: dict) -> None:
        """Test get_one with v4 response."""
        respx.get("http://localhost:1337/api/articles/1").mock(
            return_value=httpx.Response(200, json=mock_v4_single_response)
        )

        with SyncClient(strapi_config) as client:
            response = client.get_one("articles/1")

        assert response.data is not None
        assert response.data.id == 1
        assert response.data.document_id is None  # v4 doesn't have document_id
        assert response.data.attributes["title"] == "Test Article"
        assert response.data.attributes["content"] == "Article content"
        assert response.data.attributes["views"] == 100

    @respx.mock
    def test_get_one_v5(self, strapi_config: StrapiConfig, mock_v5_single_response: dict) -> None:
        """Test get_one with v5 response."""
        respx.get("http://localhost:1337/api/articles/1").mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        with SyncClient(strapi_config) as client:
            response = client.get_one("articles/1")

        assert response.data is not None
        assert response.data.id == 1
        assert response.data.document_id == "abc123"
        assert response.data.attributes["title"] == "Test Article"
        assert response.data.attributes["content"] == "Article content"

    @respx.mock
    def test_get_one_with_query(
        self, strapi_config: StrapiConfig, mock_v5_single_response: dict
    ) -> None:
        """Test get_one with query parameters."""
        query = StrapiQuery().populate_fields(["author"]).select(["title", "content"])

        respx.get("http://localhost:1337/api/articles/1").mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        with SyncClient(strapi_config) as client:
            response = client.get_one("articles/1", query=query)

        assert response.data is not None
        assert response.data.attributes["title"] == "Test Article"

    @respx.mock
    def test_get_many_v4(
        self, strapi_config: StrapiConfig, mock_v4_collection_response: dict
    ) -> None:
        """Test get_many with v4 response."""
        respx.get("http://localhost:1337/api/articles").mock(
            return_value=httpx.Response(200, json=mock_v4_collection_response)
        )

        with SyncClient(strapi_config) as client:
            response = client.get_many("articles")

        assert len(response.data) == 2
        assert response.data[0].id == 1
        assert response.data[0].attributes["title"] == "First Article"
        assert response.data[1].id == 2
        assert response.data[1].attributes["title"] == "Second Article"

        # Check pagination metadata
        assert response.meta is not None
        assert response.meta.pagination is not None
        assert response.meta.pagination.total == 2

    @respx.mock
    def test_get_many_v5(
        self, strapi_config: StrapiConfig, mock_v5_collection_response: dict
    ) -> None:
        """Test get_many with v5 response."""
        respx.get("http://localhost:1337/api/articles").mock(
            return_value=httpx.Response(200, json=mock_v5_collection_response)
        )

        with SyncClient(strapi_config) as client:
            response = client.get_many("articles")

        assert len(response.data) == 2
        assert response.data[0].document_id == "abc123"
        assert response.data[1].document_id == "def456"

    @respx.mock
    def test_get_many_with_complex_query(
        self, strapi_config: StrapiConfig, mock_v5_collection_response: dict
    ) -> None:
        """Test get_many with complex query."""
        query = (
            StrapiQuery()
            .filter(FilterBuilder().eq("status", "published").gt("views", 100))
            .sort_by("publishedAt", SortDirection.DESC)
            .paginate(page=1, page_size=25)
            .populate_fields(["author", "category"])
        )

        respx.get("http://localhost:1337/api/articles").mock(
            return_value=httpx.Response(200, json=mock_v5_collection_response)
        )

        with SyncClient(strapi_config) as client:
            response = client.get_many("articles", query=query)

        assert len(response.data) == 2

    @respx.mock
    def test_create(self, strapi_config: StrapiConfig, mock_v5_single_response: dict) -> None:
        """Test create entity."""
        respx.post("http://localhost:1337/api/articles").mock(
            return_value=httpx.Response(201, json=mock_v5_single_response)
        )

        with SyncClient(strapi_config) as client:
            data = {"title": "New Article", "content": "New content"}
            response = client.create("articles", data)

        assert response.data is not None
        assert response.data.id == 1
        assert response.data.attributes["title"] == "Test Article"

    @respx.mock
    def test_update(self, strapi_config: StrapiConfig, mock_v5_single_response: dict) -> None:
        """Test update entity."""
        respx.put("http://localhost:1337/api/articles/1").mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        with SyncClient(strapi_config) as client:
            data = {"title": "Updated Title"}
            response = client.update("articles/1", data)

        assert response.data is not None
        assert response.data.id == 1

    @respx.mock
    def test_remove(self, strapi_config: StrapiConfig, mock_v5_single_response: dict) -> None:
        """Test delete entity."""
        respx.delete("http://localhost:1337/api/articles/1").mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        with SyncClient(strapi_config) as client:
            response = client.remove("articles/1")

        assert response.data is not None
        assert response.data.id == 1


class TestAsyncClientTyped:
    """Tests for typed async client methods."""

    @respx.mock
    async def test_get_one_v4(
        self, strapi_config: StrapiConfig, mock_v4_single_response: dict
    ) -> None:
        """Test async get_one with v4 response."""
        respx.get("http://localhost:1337/api/articles/1").mock(
            return_value=httpx.Response(200, json=mock_v4_single_response)
        )

        async with AsyncClient(strapi_config) as client:
            response = await client.get_one("articles/1")

        assert response.data is not None
        assert response.data.id == 1
        assert response.data.attributes["title"] == "Test Article"

    @respx.mock
    async def test_get_one_v5(
        self, strapi_config: StrapiConfig, mock_v5_single_response: dict
    ) -> None:
        """Test async get_one with v5 response."""
        respx.get("http://localhost:1337/api/articles/1").mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        async with AsyncClient(strapi_config) as client:
            response = await client.get_one("articles/1")

        assert response.data is not None
        assert response.data.id == 1
        assert response.data.document_id == "abc123"

    @respx.mock
    async def test_get_many_v5(
        self, strapi_config: StrapiConfig, mock_v5_collection_response: dict
    ) -> None:
        """Test async get_many with v5 response."""
        respx.get("http://localhost:1337/api/articles").mock(
            return_value=httpx.Response(200, json=mock_v5_collection_response)
        )

        async with AsyncClient(strapi_config) as client:
            response = await client.get_many("articles")

        assert len(response.data) == 2
        assert response.data[0].document_id == "abc123"

    @respx.mock
    async def test_get_many_with_query(
        self, strapi_config: StrapiConfig, mock_v5_collection_response: dict
    ) -> None:
        """Test async get_many with query."""
        query = (
            StrapiQuery()
            .filter(FilterBuilder().eq("status", "published"))
            .paginate(page=1, page_size=10)
        )

        respx.get("http://localhost:1337/api/articles").mock(
            return_value=httpx.Response(200, json=mock_v5_collection_response)
        )

        async with AsyncClient(strapi_config) as client:
            response = await client.get_many("articles", query=query)

        assert len(response.data) == 2

    @respx.mock
    async def test_create(self, strapi_config: StrapiConfig, mock_v5_single_response: dict) -> None:
        """Test async create entity."""
        respx.post("http://localhost:1337/api/articles").mock(
            return_value=httpx.Response(201, json=mock_v5_single_response)
        )

        async with AsyncClient(strapi_config) as client:
            data = {"title": "New Article", "content": "New content"}
            response = await client.create("articles", data)

        assert response.data is not None
        assert response.data.id == 1

    @respx.mock
    async def test_update(self, strapi_config: StrapiConfig, mock_v5_single_response: dict) -> None:
        """Test async update entity."""
        respx.put("http://localhost:1337/api/articles/1").mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        async with AsyncClient(strapi_config) as client:
            data = {"title": "Updated Title"}
            response = await client.update("articles/1", data)

        assert response.data is not None

    @respx.mock
    async def test_remove(self, strapi_config: StrapiConfig, mock_v5_single_response: dict) -> None:
        """Test async delete entity."""
        respx.delete("http://localhost:1337/api/articles/1").mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        async with AsyncClient(strapi_config) as client:
            response = await client.remove("articles/1")

        assert response.data is not None
