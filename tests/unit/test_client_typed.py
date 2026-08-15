"""Tests for typed client methods with normalized responses."""

import httpx
import pytest
import respx

from strapi_kit.client.async_client import AsyncClient
from strapi_kit.client.base import BaseClient
from strapi_kit.client.sync_client import SyncClient
from strapi_kit.exceptions import ValidationError
from strapi_kit.models import FilterBuilder, SortDirection, StrapiQuery
from strapi_kit.models.config import StrapiConfig
from strapi_kit.models.enums import DocumentAction

# documentId with path/query/space/percent chars — must be fully encoded
SPECIAL_DOCUMENT_ID = "a/b?c d%"
ENCODED_DOCUMENT_ID = "a%2Fb%3Fc%20d%25"
ENCODED_DOCUMENT_URL = f"http://localhost:1337/api/articles/{ENCODED_DOCUMENT_ID}"


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

    @pytest.mark.respx
    def test_get_one_v4(
        self, strapi_config: StrapiConfig, mock_v4_single_response: dict, respx_mock: respx.Router
    ) -> None:
        """Test get_one with v4 response."""
        respx_mock.get("http://localhost:1337/api/articles/1").mock(
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

    @pytest.mark.respx
    def test_get_one_v5(
        self, strapi_config: StrapiConfig, mock_v5_single_response: dict, respx_mock: respx.Router
    ) -> None:
        """Test get_one with v5 response."""
        respx_mock.get("http://localhost:1337/api/articles/1").mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        with SyncClient(strapi_config) as client:
            response = client.get_one("articles/1")

        assert response.data is not None
        assert response.data.id == 1
        assert response.data.document_id == "abc123"
        assert response.data.attributes["title"] == "Test Article"
        assert response.data.attributes["content"] == "Article content"

    @pytest.mark.respx
    def test_get_one_with_query(
        self, strapi_config: StrapiConfig, mock_v5_single_response: dict, respx_mock: respx.Router
    ) -> None:
        """Test get_one with query parameters."""
        query = StrapiQuery().populate_fields(["author"]).select(["title", "content"])

        respx_mock.get("http://localhost:1337/api/articles/1").mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        with SyncClient(strapi_config) as client:
            response = client.get_one("articles/1", query=query)

        assert response.data is not None
        assert response.data.attributes["title"] == "Test Article"

    @pytest.mark.respx
    def test_get_many_v4(
        self,
        strapi_config: StrapiConfig,
        mock_v4_collection_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test get_many with v4 response."""
        respx_mock.get("http://localhost:1337/api/articles").mock(
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

    @pytest.mark.respx
    def test_get_many_v5(
        self,
        strapi_config: StrapiConfig,
        mock_v5_collection_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test get_many with v5 response."""
        respx_mock.get("http://localhost:1337/api/articles").mock(
            return_value=httpx.Response(200, json=mock_v5_collection_response)
        )

        with SyncClient(strapi_config) as client:
            response = client.get_many("articles")

        assert len(response.data) == 2
        assert response.data[0].document_id == "abc123"
        assert response.data[1].document_id == "def456"

    @pytest.mark.respx
    def test_get_many_with_complex_query(
        self,
        strapi_config: StrapiConfig,
        mock_v5_collection_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test get_many with complex query."""
        query = (
            StrapiQuery()
            .filter(FilterBuilder().eq("status", "published").gt("views", 100))
            .sort_by("publishedAt", SortDirection.DESC)
            .paginate(page=1, page_size=25)
            .populate_fields(["author", "category"])
        )

        respx_mock.get("http://localhost:1337/api/articles").mock(
            return_value=httpx.Response(200, json=mock_v5_collection_response)
        )

        with SyncClient(strapi_config) as client:
            response = client.get_many("articles", query=query)

        assert len(response.data) == 2

    @pytest.mark.respx
    def test_create(
        self, strapi_config: StrapiConfig, mock_v5_single_response: dict, respx_mock: respx.Router
    ) -> None:
        """Test create entity."""
        respx_mock.post("http://localhost:1337/api/articles").mock(
            return_value=httpx.Response(201, json=mock_v5_single_response)
        )

        with SyncClient(strapi_config) as client:
            data = {"title": "New Article", "content": "New content"}
            response = client.create("articles", data)

        assert response.data is not None
        assert response.data.id == 1
        assert response.data.attributes["title"] == "Test Article"

    @pytest.mark.respx
    def test_update(
        self, strapi_config: StrapiConfig, mock_v5_single_response: dict, respx_mock: respx.Router
    ) -> None:
        """Test update entity."""
        respx_mock.put("http://localhost:1337/api/articles/1").mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        with SyncClient(strapi_config) as client:
            data = {"title": "Updated Title"}
            response = client.update("articles/1", data)

        assert response.data is not None
        assert response.data.id == 1

    @pytest.mark.respx
    def test_remove(
        self, strapi_config: StrapiConfig, mock_v5_single_response: dict, respx_mock: respx.Router
    ) -> None:
        """Test delete entity."""
        respx_mock.delete("http://localhost:1337/api/articles/1").mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        with SyncClient(strapi_config) as client:
            response = client.remove("articles/1")

        assert response.data is not None
        assert response.data.id == 1


class TestAsyncClientTyped:
    """Tests for typed async client methods."""

    @pytest.mark.respx
    async def test_get_one_v4(
        self, strapi_config: StrapiConfig, mock_v4_single_response: dict, respx_mock: respx.Router
    ) -> None:
        """Test async get_one with v4 response."""
        respx_mock.get("http://localhost:1337/api/articles/1").mock(
            return_value=httpx.Response(200, json=mock_v4_single_response)
        )

        async with AsyncClient(strapi_config) as client:
            response = await client.get_one("articles/1")

        assert response.data is not None
        assert response.data.id == 1
        assert response.data.attributes["title"] == "Test Article"

    @pytest.mark.respx
    async def test_get_one_v5(
        self, strapi_config: StrapiConfig, mock_v5_single_response: dict, respx_mock: respx.Router
    ) -> None:
        """Test async get_one with v5 response."""
        respx_mock.get("http://localhost:1337/api/articles/1").mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        async with AsyncClient(strapi_config) as client:
            response = await client.get_one("articles/1")

        assert response.data is not None
        assert response.data.id == 1
        assert response.data.document_id == "abc123"

    @pytest.mark.respx
    async def test_get_many_v5(
        self,
        strapi_config: StrapiConfig,
        mock_v5_collection_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test async get_many with v5 response."""
        respx_mock.get("http://localhost:1337/api/articles").mock(
            return_value=httpx.Response(200, json=mock_v5_collection_response)
        )

        async with AsyncClient(strapi_config) as client:
            response = await client.get_many("articles")

        assert len(response.data) == 2
        assert response.data[0].document_id == "abc123"

    @pytest.mark.respx
    async def test_get_many_with_query(
        self,
        strapi_config: StrapiConfig,
        mock_v5_collection_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test async get_many with query."""
        query = (
            StrapiQuery()
            .filter(FilterBuilder().eq("status", "published"))
            .paginate(page=1, page_size=10)
        )

        respx_mock.get("http://localhost:1337/api/articles").mock(
            return_value=httpx.Response(200, json=mock_v5_collection_response)
        )

        async with AsyncClient(strapi_config) as client:
            response = await client.get_many("articles", query=query)

        assert len(response.data) == 2

    @pytest.mark.respx
    async def test_create(
        self, strapi_config: StrapiConfig, mock_v5_single_response: dict, respx_mock: respx.Router
    ) -> None:
        """Test async create entity."""
        respx_mock.post("http://localhost:1337/api/articles").mock(
            return_value=httpx.Response(201, json=mock_v5_single_response)
        )

        async with AsyncClient(strapi_config) as client:
            data = {"title": "New Article", "content": "New content"}
            response = await client.create("articles", data)

        assert response.data is not None
        assert response.data.id == 1

    @pytest.mark.respx
    async def test_update(
        self, strapi_config: StrapiConfig, mock_v5_single_response: dict, respx_mock: respx.Router
    ) -> None:
        """Test async update entity."""
        respx_mock.put("http://localhost:1337/api/articles/1").mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        async with AsyncClient(strapi_config) as client:
            data = {"title": "Updated Title"}
            response = await client.update("articles/1", data)

        assert response.data is not None

    @pytest.mark.respx
    async def test_remove(
        self, strapi_config: StrapiConfig, mock_v5_single_response: dict, respx_mock: respx.Router
    ) -> None:
        """Test async delete entity."""
        respx_mock.delete("http://localhost:1337/api/articles/1").mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        async with AsyncClient(strapi_config) as client:
            response = await client.remove("articles/1")

        assert response.data is not None


class TestDocumentPath:
    """Tests for BaseClient.document_path encoding and validation."""

    def test_encodes_slash_question_space_and_percent(self) -> None:
        """document_id characters that change a URL must be fully encoded."""
        assert (
            BaseClient.document_path("articles", SPECIAL_DOCUMENT_ID)
            == f"articles/{ENCODED_DOCUMENT_ID}"
        )
        assert ENCODED_DOCUMENT_ID == "a%2Fb%3Fc%20d%25"

    def test_strips_collection_slashes_without_encoding(self) -> None:
        """Collection names are strip("/") only — not percent-encoded."""
        assert BaseClient.document_path("/articles/", "abc123") == "articles/abc123"

    def test_blank_collection_raises(self) -> None:
        """Blank collection names raise ValidationError."""
        with pytest.raises(ValidationError, match="collection"):
            BaseClient.document_path("", "abc123")
        with pytest.raises(ValidationError, match="collection"):
            BaseClient.document_path("/", "abc123")
        with pytest.raises(ValidationError, match="collection"):
            BaseClient.document_path("///", "abc123")

    def test_blank_document_id_raises(self) -> None:
        """Blank document IDs raise ValidationError."""
        with pytest.raises(ValidationError, match="document_id"):
            BaseClient.document_path("articles", "")
        with pytest.raises(ValidationError, match="document_id"):
            BaseClient.document_path("articles", "   ")

    def test_action_helpers_reuse_document_path(self, strapi_config: StrapiConfig) -> None:
        """publish / unpublish / discard_draft share the CRUD document_id encoder."""
        encoded = BaseClient.document_path("articles", SPECIAL_DOCUMENT_ID)
        with SyncClient(strapi_config) as client:
            assert (
                client._document_action_endpoint(
                    "articles", SPECIAL_DOCUMENT_ID, DocumentAction.PUBLISH
                )
                == f"{encoded}/actions/publish"
            )
            assert (
                client._document_action_endpoint(
                    "articles", SPECIAL_DOCUMENT_ID, DocumentAction.UNPUBLISH
                )
                == f"{encoded}/actions/unpublish"
            )
            assert (
                client._document_action_endpoint(
                    "articles", SPECIAL_DOCUMENT_ID, DocumentAction.DISCARD_DRAFT
                )
                == f"{encoded}/actions/discardDraft"
            )


class TestSyncClientDocumentId:
    """Sync get_one / update / remove with encoded document_id."""

    @pytest.mark.respx
    def test_get_one_encodes_document_id(
        self,
        strapi_config: StrapiConfig,
        mock_v5_single_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """GET uses a fully encoded document_id path segment."""
        respx_mock.get(ENCODED_DOCUMENT_URL).mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        with SyncClient(strapi_config) as client:
            response = client.get_one("articles", document_id=SPECIAL_DOCUMENT_ID)

        assert response.data is not None
        assert response.data.id == 1

    @pytest.mark.respx
    def test_update_encodes_document_id(
        self,
        strapi_config: StrapiConfig,
        mock_v5_single_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """PUT uses a fully encoded document_id path segment."""
        respx_mock.put(ENCODED_DOCUMENT_URL).mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        with SyncClient(strapi_config) as client:
            response = client.update(
                "articles", {"title": "Updated"}, document_id=SPECIAL_DOCUMENT_ID
            )

        assert response.data is not None
        assert response.data.id == 1

    @pytest.mark.respx
    def test_remove_encodes_document_id(
        self,
        strapi_config: StrapiConfig,
        mock_v5_single_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """DELETE uses a fully encoded document_id path segment."""
        respx_mock.delete(ENCODED_DOCUMENT_URL).mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        with SyncClient(strapi_config) as client:
            response = client.remove("articles", document_id=SPECIAL_DOCUMENT_ID)

        assert response.data is not None
        assert response.data.id == 1

    @pytest.mark.respx
    def test_get_one_string_endpoint_still_works(
        self,
        strapi_config: StrapiConfig,
        mock_v5_single_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Existing get_one("articles/abc") form remains supported."""
        respx_mock.get("http://localhost:1337/api/articles/abc").mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        with SyncClient(strapi_config) as client:
            response = client.get_one("articles/abc")

        assert response.data is not None
        assert response.data.id == 1

    def test_blank_collection_raises(self, strapi_config: StrapiConfig) -> None:
        """Blank collection on get_one / update / remove raises ValidationError."""
        with SyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="collection"):
                client.get_one("", document_id="abc123")
            with pytest.raises(ValidationError, match="collection"):
                client.update("", {"title": "x"}, document_id="abc123")
            with pytest.raises(ValidationError, match="collection"):
                client.remove("", document_id="abc123")

    def test_blank_document_id_raises(self, strapi_config: StrapiConfig) -> None:
        """Blank document_id on get_one / update / remove raises ValidationError."""
        with SyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="document_id"):
                client.get_one("articles", document_id="")
            with pytest.raises(ValidationError, match="document_id"):
                client.update("articles", {"title": "x"}, document_id="   ")
            with pytest.raises(ValidationError, match="document_id"):
                client.remove("articles", document_id="")


class TestAsyncClientDocumentId:
    """Async get_one / update / remove with encoded document_id."""

    @pytest.mark.respx
    async def test_get_one_encodes_document_id(
        self,
        strapi_config: StrapiConfig,
        mock_v5_single_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """GET uses a fully encoded document_id path segment."""
        respx_mock.get(ENCODED_DOCUMENT_URL).mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        async with AsyncClient(strapi_config) as client:
            response = await client.get_one("articles", document_id=SPECIAL_DOCUMENT_ID)

        assert response.data is not None
        assert response.data.id == 1

    @pytest.mark.respx
    async def test_update_encodes_document_id(
        self,
        strapi_config: StrapiConfig,
        mock_v5_single_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """PUT uses a fully encoded document_id path segment."""
        respx_mock.put(ENCODED_DOCUMENT_URL).mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        async with AsyncClient(strapi_config) as client:
            response = await client.update(
                "articles", {"title": "Updated"}, document_id=SPECIAL_DOCUMENT_ID
            )

        assert response.data is not None
        assert response.data.id == 1

    @pytest.mark.respx
    async def test_remove_encodes_document_id(
        self,
        strapi_config: StrapiConfig,
        mock_v5_single_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """DELETE uses a fully encoded document_id path segment."""
        respx_mock.delete(ENCODED_DOCUMENT_URL).mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        async with AsyncClient(strapi_config) as client:
            response = await client.remove("articles", document_id=SPECIAL_DOCUMENT_ID)

        assert response.data is not None
        assert response.data.id == 1

    @pytest.mark.respx
    async def test_get_one_string_endpoint_still_works(
        self,
        strapi_config: StrapiConfig,
        mock_v5_single_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Existing get_one("articles/abc") form remains supported."""
        respx_mock.get("http://localhost:1337/api/articles/abc").mock(
            return_value=httpx.Response(200, json=mock_v5_single_response)
        )

        async with AsyncClient(strapi_config) as client:
            response = await client.get_one("articles/abc")

        assert response.data is not None
        assert response.data.id == 1

    async def test_blank_collection_raises(self, strapi_config: StrapiConfig) -> None:
        """Blank collection on get_one / update / remove raises ValidationError."""
        async with AsyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="collection"):
                await client.get_one("", document_id="abc123")
            with pytest.raises(ValidationError, match="collection"):
                await client.update("", {"title": "x"}, document_id="abc123")
            with pytest.raises(ValidationError, match="collection"):
                await client.remove("", document_id="abc123")

    async def test_blank_document_id_raises(self, strapi_config: StrapiConfig) -> None:
        """Blank document_id on get_one / update / remove raises ValidationError."""
        async with AsyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="document_id"):
                await client.get_one("articles", document_id="")
            with pytest.raises(ValidationError, match="document_id"):
                await client.update("articles", {"title": "x"}, document_id="   ")
            with pytest.raises(ValidationError, match="document_id"):
                await client.remove("articles", document_id="")
