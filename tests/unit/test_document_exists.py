"""Draft-inclusive exists() and opt-in write-404 classification."""

from typing import Any

import httpx
import pytest
import respx
from httpx import Response

from strapi_kit import (
    AsyncClient,
    DocumentStatus,
    RetryConfig,
    StrapiConfig,
    SyncClient,
)
from strapi_kit.exceptions import (
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    ServerError,
    ValidationError,
)
from strapi_kit.exceptions import (
    ConnectionError as StrapiConnectionError,
)
from strapi_kit.models import StrapiQuery

DOCUMENT_ID = "abc123def456"
COLLECTION = "articles"
ENDPOINT = f"{COLLECTION}/{DOCUMENT_ID}"
DOCUMENT_URL = f"http://localhost:1337/api/{ENDPOINT}"

NOT_FOUND_BODY = {"error": {"message": "Not Found"}}
UNAUTHORIZED_BODY = {"error": {"message": "Unauthorized"}}
FORBIDDEN_BODY = {"error": {"message": "Forbidden"}}
VALIDATION_BODY = {"error": {"message": "Invalid key status"}}
SERVER_ERROR_BODY = {"error": {"message": "Internal Server Error"}}
EMPTY_DATA_BODY = {"data": None}


def _not_found() -> Response:
    return Response(404, json=NOT_FOUND_BODY)


def _no_retry(strapi_config: StrapiConfig) -> StrapiConfig:
    return StrapiConfig(
        base_url=strapi_config.base_url,
        api_token=strapi_config.api_token,
        retry=RetryConfig(max_attempts=1),
    )


def _route_by_status(
    published: Response,
    draft: Response,
) -> Any:
    def _handler(request: httpx.Request) -> Response:
        if request.url.params.get("status") == "draft":
            return draft
        return published

    return _handler


class TestSyncExists:
    """SyncClient.exists published-then-draft lookup."""

    @pytest.mark.respx
    def test_published_hit_one_request(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(return_value=Response(200, json=mock_v5_response))

        with SyncClient(strapi_config) as client:
            assert client.exists(COLLECTION, DOCUMENT_ID) is True

        assert route.call_count == 1
        assert "status" not in route.calls[0].request.url.params

    @pytest.mark.respx
    def test_published_404_draft_hit(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(_not_found(), Response(200, json=mock_v5_response))
        )

        with SyncClient(strapi_config) as client:
            assert client.exists(COLLECTION, DOCUMENT_ID) is True

        assert route.call_count == 2
        assert route.calls[1].request.url.params["status"] == "draft"

    @pytest.mark.respx
    def test_both_404_false(self, strapi_config: StrapiConfig, respx_mock: respx.Router) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        with SyncClient(strapi_config) as client:
            assert client.exists(COLLECTION, DOCUMENT_ID) is False

        assert route.call_count == 2
        assert route.calls[1].request.url.params["status"] == "draft"

    @pytest.mark.respx
    def test_draft_400_validation_false(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(_not_found(), Response(400, json=VALIDATION_BODY))
        )

        with SyncClient(strapi_config) as client:
            assert client.exists(COLLECTION, DOCUMENT_ID) is False

        assert route.call_count == 2

    @pytest.mark.respx
    def test_draft_400_unrelated_populate_raises(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        """A populate/filter 400 on the draft probe must not look like absent."""
        route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(
                _not_found(),
                Response(400, json={"error": {"message": "Invalid key populate"}}),
            )
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="Invalid key populate"):
                client.exists(COLLECTION, DOCUMENT_ID)

        assert route.call_count == 2

    @pytest.mark.respx
    def test_draft_400_publication_state_false(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        """Unknown publicationState on the draft probe is still absent."""
        route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(
                _not_found(),
                Response(400, json={"error": {"message": "Invalid key publicationState"}}),
            )
        )

        with SyncClient(strapi_config) as client:
            assert client.exists(COLLECTION, DOCUMENT_ID) is False

        assert route.call_count == 2

    @pytest.mark.respx
    def test_401_on_first_get_raises(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(
            return_value=Response(401, json=UNAUTHORIZED_BODY)
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(AuthenticationError) as exc_info:
                client.exists(COLLECTION, DOCUMENT_ID)

        assert exc_info.value.status_code == 401
        assert route.call_count == 1

    @pytest.mark.respx
    def test_draft_500_raises(self, strapi_config: StrapiConfig, respx_mock: respx.Router) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(_not_found(), Response(500, json=SERVER_ERROR_BODY))
        )

        with SyncClient(_no_retry(strapi_config)) as client:
            with pytest.raises(ServerError) as exc_info:
                client.exists(COLLECTION, DOCUMENT_ID)

        assert exc_info.value.status_code == 500
        assert route.call_count == 2

    @pytest.mark.respx
    def test_401_on_draft_retry_raises(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(_not_found(), Response(401, json=UNAUTHORIZED_BODY))
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(AuthenticationError) as exc_info:
                client.exists(COLLECTION, DOCUMENT_ID)

        assert exc_info.value.status_code == 401
        assert route.call_count == 2

    @pytest.mark.respx
    def test_403_on_first_get_raises(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(return_value=Response(403, json=FORBIDDEN_BODY))

        with SyncClient(strapi_config) as client:
            with pytest.raises(AuthorizationError) as exc_info:
                client.exists(COLLECTION, DOCUMENT_ID)

        assert exc_info.value.status_code == 403
        assert route.call_count == 1

    @pytest.mark.respx
    def test_published_400_raises(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(return_value=Response(400, json=VALIDATION_BODY))

        with SyncClient(strapi_config) as client:
            with pytest.raises(ValidationError) as exc_info:
                client.exists(COLLECTION, DOCUMENT_ID)

        assert exc_info.value.status_code == 400
        assert route.call_count == 1

    @pytest.mark.respx
    def test_network_on_first_get_raises(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.get(DOCUMENT_URL).mock(side_effect=httpx.ConnectError("boom"))

        with SyncClient(_no_retry(strapi_config)) as client:
            with pytest.raises(StrapiConnectionError):
                client.exists(COLLECTION, DOCUMENT_ID)

    @pytest.mark.respx
    def test_published_empty_data_false(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(return_value=Response(200, json=EMPTY_DATA_BODY))

        with SyncClient(strapi_config) as client:
            assert client.exists(COLLECTION, DOCUMENT_ID) is False

        assert route.call_count == 1
        assert "status" not in route.calls[0].request.url.params

    @pytest.mark.respx
    def test_percent_encodes_document_id(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get("http://localhost:1337/api/articles/a%2Fb%3Fc").mock(
            return_value=Response(200, json=mock_v5_response)
        )

        with SyncClient(strapi_config) as client:
            assert client.exists(COLLECTION, "a/b?c") is True

        assert route.call_count == 1

    def test_rejects_blank_document_id(self, strapi_config: StrapiConfig) -> None:
        with SyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="document_id"):
                client.exists(COLLECTION, "  ")

    def test_rejects_blank_collection(self, strapi_config: StrapiConfig) -> None:
        with SyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="collection"):
                client.exists("", DOCUMENT_ID)
            with pytest.raises(ValidationError, match="collection"):
                client.exists("   ", DOCUMENT_ID)

    def test_rejects_multi_segment_collection(self, strapi_config: StrapiConfig) -> None:
        with SyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="single path segment"):
                client.exists("articles/../upload", DOCUMENT_ID)


class TestAsyncExists:
    """AsyncClient.exists published-then-draft lookup."""

    @pytest.mark.respx
    async def test_published_hit_one_request(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(return_value=Response(200, json=mock_v5_response))

        async with AsyncClient(strapi_config) as client:
            assert await client.exists(COLLECTION, DOCUMENT_ID) is True

        assert route.call_count == 1
        assert "status" not in route.calls[0].request.url.params

    @pytest.mark.respx
    async def test_published_404_draft_hit(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(_not_found(), Response(200, json=mock_v5_response))
        )

        async with AsyncClient(strapi_config) as client:
            assert await client.exists(COLLECTION, DOCUMENT_ID) is True

        assert route.call_count == 2
        assert route.calls[1].request.url.params["status"] == "draft"

    @pytest.mark.respx
    async def test_both_404_false(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        async with AsyncClient(strapi_config) as client:
            assert await client.exists(COLLECTION, DOCUMENT_ID) is False

        assert route.call_count == 2
        assert route.calls[1].request.url.params["status"] == "draft"

    @pytest.mark.respx
    async def test_draft_400_validation_false(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(_not_found(), Response(400, json=VALIDATION_BODY))
        )

        async with AsyncClient(strapi_config) as client:
            assert await client.exists(COLLECTION, DOCUMENT_ID) is False

        assert route.call_count == 2

    @pytest.mark.respx
    async def test_draft_400_unrelated_populate_raises(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        """A populate/filter 400 on the draft probe must not look like absent."""
        route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(
                _not_found(),
                Response(400, json={"error": {"message": "Invalid key populate"}}),
            )
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="Invalid key populate"):
                await client.exists(COLLECTION, DOCUMENT_ID)

        assert route.call_count == 2

    @pytest.mark.respx
    async def test_401_on_first_get_raises(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(
            return_value=Response(401, json=UNAUTHORIZED_BODY)
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(AuthenticationError) as exc_info:
                await client.exists(COLLECTION, DOCUMENT_ID)

        assert exc_info.value.status_code == 401
        assert route.call_count == 1

    @pytest.mark.respx
    async def test_draft_500_raises(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(_not_found(), Response(500, json=SERVER_ERROR_BODY))
        )

        async with AsyncClient(_no_retry(strapi_config)) as client:
            with pytest.raises(ServerError) as exc_info:
                await client.exists(COLLECTION, DOCUMENT_ID)

        assert exc_info.value.status_code == 500
        assert route.call_count == 2

    @pytest.mark.respx
    async def test_401_on_draft_retry_raises(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        async with AsyncClient(strapi_config) as client:
            respx_mock.get(DOCUMENT_URL).mock(
                side_effect=_route_by_status(_not_found(), Response(401, json=UNAUTHORIZED_BODY))
            )
            with pytest.raises(AuthenticationError) as exc_info:
                await client.exists(COLLECTION, DOCUMENT_ID)

        assert exc_info.value.status_code == 401

    @pytest.mark.respx
    async def test_published_empty_data_false(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(return_value=Response(200, json=EMPTY_DATA_BODY))

        async with AsyncClient(strapi_config) as client:
            assert await client.exists(COLLECTION, DOCUMENT_ID) is False

        assert route.call_count == 1

    async def test_rejects_multi_segment_collection(self, strapi_config: StrapiConfig) -> None:
        async with AsyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="single path segment"):
                await client.exists("articles/../upload", DOCUMENT_ID)


class TestSync