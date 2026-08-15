"""Draft-inclusive exists() and opt-in write-404 classification."""

from typing import Any

import httpx
import pytest
import respx
from httpx import Response

from strapi_kit import AsyncClient, RetryConfig, StrapiConfig, SyncClient
from strapi_kit.exceptions import (
    AuthenticationError,
    AuthorizationError,
    NotFoundError,
    ServerError,
)

DOCUMENT_ID = "abc123def456"
COLLECTION = "articles"
ENDPOINT = f"{COLLECTION}/{DOCUMENT_ID}"
DOCUMENT_URL = f"http://localhost:1337/api/{ENDPOINT}"

NOT_FOUND_BODY = {"error": {"message": "Not Found"}}
UNAUTHORIZED_BODY = {"error": {"message": "Unauthorized"}}
VALIDATION_BODY = {"error": {"message": "Invalid key status"}}
SERVER_ERROR_BODY = {"error": {"message": "Internal Server Error"}}


def _not_found() -> Response:
    return Response(404, json=NOT_FOUND_BODY)


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
        no_retry = StrapiConfig(
            base_url=strapi_config.base_url,
            api_token=strapi_config.api_token,
            retry=RetryConfig(max_attempts=1),
        )
        route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(_not_found(), Response(500, json=SERVER_ERROR_BODY))
        )

        with SyncClient(no_retry) as client:
            with pytest.raises(ServerError) as exc_info:
                client.exists(COLLECTION, DOCUMENT_ID)

        assert exc_info.value.status_code == 500
        assert route.call_count == 2


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
        respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        async with AsyncClient(strapi_config) as client:
            assert await client.exists(COLLECTION, DOCUMENT_ID) is False

    @pytest.mark.respx
    async def test_draft_400_validation_false(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(_not_found(), Response(400, json=VALIDATION_BODY))
        )

        async with AsyncClient(strapi_config) as client:
            assert await client.exists(COLLECTION, DOCUMENT_ID) is False

    @pytest.mark.respx
    async def test_401_on_first_get_raises(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.get(DOCUMENT_URL).mock(return_value=Response(401, json=UNAUTHORIZED_BODY))

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(AuthenticationError) as exc_info:
                await client.exists(COLLECTION, DOCUMENT_ID)

        assert exc_info.value.status_code == 401

    @pytest.mark.respx
    async def test_draft_500_raises(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        no_retry = StrapiConfig(
            base_url=strapi_config.base_url,
            api_token=strapi_config.api_token,
            retry=RetryConfig(max_attempts=1),
        )
        respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(_not_found(), Response(500, json=SERVER_ERROR_BODY))
        )

        async with AsyncClient(no_retry) as client:
            with pytest.raises(ServerError):
                await client.exists(COLLECTION, DOCUMENT_ID)


class TestSyncClassifyWrite404:
    """Opt-in write-404 remapping on SyncClient.update / remove."""

    @pytest.mark.respx
    def test_update_404_draft_exists_authorization(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        put_route = respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            return_value=Response(200, json=mock_v5_response)
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(AuthorizationError) as exc_info:
                client.update(ENDPOINT, {"title": "x"}, classify_write_404=True)

        assert put_route.called
        assert get_route.call_count == 1
        assert get_route.calls[0].request.url.params["status"] == "draft"
        assert "document exists" in str(exc_info.value)
        assert exc_info.value.details["status_code"] == 404
        assert exc_info.value.status_code == 404

    @pytest.mark.respx
    def test_remove_404_draft_exists_authorization(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.delete(DOCUMENT_URL).mock(return_value=_not_found())
        respx_mock.get(DOCUMENT_URL).mock(return_value=Response(200, json=mock_v5_response))

        with SyncClient(strapi_config) as client:
            with pytest.raises(AuthorizationError) as exc_info:
                client.remove(ENDPOINT, classify_write_404=True)

        assert exc_info.value.details["status_code"] == 404

    @pytest.mark.respx
    def test_update_404_draft_404_original_not_found(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.update(ENDPOINT, {"title": "x"}, classify_write_404=True)

        assert get_route.call_count == 1
        assert isinstance(exc_info.value, NotFoundError)
        assert exc_info.value.status_code == 404
        assert not isinstance(exc_info.value, AuthorizationError)

    @pytest.mark.respx
    def test_update_404_probe_exception_keeps_original(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        no_retry = StrapiConfig(
            base_url=strapi_config.base_url,
            api_token=strapi_config.api_token,
            retry=RetryConfig(max_attempts=1),
        )
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        respx_mock.get(DOCUMENT_URL).mock(side_effect=httpx.ConnectError("boom"))

        with SyncClient(no_retry) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.update(ENDPOINT, {"title": "x"}, classify_write_404=True)

        assert exc_info.value.status_code == 404

    @pytest.mark.respx
    def test_default_update_404_unchanged(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError):
                client.update(ENDPOINT, {"title": "x"})

        assert get_route.call_count == 0


class TestAsyncClassifyWrite404:
    """Opt-in write-404 remapping on AsyncClient.update / remove."""

    @pytest.mark.respx
    async def test_update_404_draft_exists_authorization(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            return_value=Response(200, json=mock_v5_response)
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(AuthorizationError) as exc_info:
                await client.update(ENDPOINT, {"title": "x"}, classify_write_404=True)

        assert get_route.call_count == 1
        assert get_route.calls[0].request.url.params["status"] == "draft"
        assert exc_info.value.details["status_code"] == 404

    @pytest.mark.respx
    async def test_remove_404_draft_exists_authorization(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.delete(DOCUMENT_URL).mock(return_value=_not_found())
        respx_mock.get(DOCUMENT_URL).mock(return_value=Response(200, json=mock_v5_response))

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(AuthorizationError) as exc_info:
                await client.remove(ENDPOINT, classify_write_404=True)

        assert exc_info.value.details["status_code"] == 404

    @pytest.mark.respx
    async def test_update_404_draft_404_original_not_found(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                await client.update(ENDPOINT, {"title": "x"}, classify_write_404=True)

        assert exc_info.value.status_code == 404
        assert not isinstance(exc_info.value, AuthorizationError)

    @pytest.mark.respx
    async def test_update_404_probe_exception_keeps_original(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        no_retry = StrapiConfig(
            base_url=strapi_config.base_url,
            api_token=strapi_config.api_token,
            retry=RetryConfig(max_attempts=1),
        )
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        respx_mock.get(DOCUMENT_URL).mock(side_effect=httpx.ConnectError("boom"))

        async with AsyncClient(no_retry) as client:
            with pytest.raises(NotFoundError) as exc_info:
                await client.update(ENDPOINT, {"title": "x"}, classify_write_404=True)

        assert exc_info.value.status_code == 404

    @pytest.mark.respx
    async def test_default_update_404_unchanged(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError):
                await client.update(ENDPOINT, {"title": "x"})

        assert get_route.call_count == 0
