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
    MethodNotAllowedError,
    NotFoundError,
    ServerError,
    ValidationError,
)
from strapi_kit.exceptions import (
    ConnectionError as StrapiConnectionError,
)
from strapi_kit.models.enums import DocumentStatus, PublicationState
from strapi_kit.models.request.query import StrapiQuery

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


def _assert_write_rejected(error: NotFoundError, operation: str) -> None:
    """Same-params GET hit is a refused write, not a missing token (#171)."""
    assert not isinstance(error, AuthorizationError)
    assert error.details["classified_from"] == "write_rejected"
    assert error.message == f"document exists; {operation} was refused."
    assert error.status_code == 404
    assert "token" not in error.message
    assert "lacks" not in error.message


def _assert_draft_only(error: NotFoundError, operation: str) -> None:
    """Draft-only unpublish / discard stays NotFoundError (#166)."""
    assert not isinstance(error, AuthorizationError)
    assert error.details["classified_from"] == "draft_only"
    if operation == "discard":
        assert error.message == (
            "document exists only as a draft; nothing published to restore via discard."
        )
    else:
        assert error.message == (
            f"document exists only as a draft; no published version to {operation}."
        )


def _assert_unclassified_not_found(error: NotFoundError) -> None:
    """Document miss keeps the original write 404 (no classified_from)."""
    assert not isinstance(error, AuthorizationError)
    assert error.status_code == 404
    assert error.details.get("classified_from") is None


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


INVALID_LOCALE_BODY = {"error": {"message": "Invalid key locale"}}


def _route_by_locale(
    with_locale: Response,
    without_locale: Response,
    *,
    locale: str,
) -> Any:
    def _handler(request: httpx.Request) -> Response:
        if request.url.params.get("locale") == locale:
            return with_locale
        if "locale" not in request.url.params:
            return without_locale
        return _not_found()

    return _handler


class TestSyncExistsInLocale:
    """SyncClient.exists_in_locale published-then-draft, optional locale."""

    @pytest.mark.respx
    def test_published_hit_sends_locale(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(return_value=Response(200, json=mock_v5_response))

        with SyncClient(strapi_config) as client:
            assert client.exists_in_locale(COLLECTION, DOCUMENT_ID, locale="fr") is True

        assert route.call_count == 1
        assert route.calls[0].request.url.params["locale"] == "fr"
        assert "status" not in route.calls[0].request.url.params

    @pytest.mark.respx
    def test_published_404_draft_hit_keeps_locale(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status_and_locale(
                _not_found(), Response(200, json=mock_v5_response), locale="fr"
            )
        )

        with SyncClient(strapi_config) as client:
            assert client.exists_in_locale(COLLECTION, DOCUMENT_ID, locale="fr") is True

        assert route.call_count == 2
        assert route.calls[0].request.url.params["locale"] == "fr"
        assert "status" not in route.calls[0].request.url.params
        assert route.calls[1].request.url.params["locale"] == "fr"
        assert route.calls[1].request.url.params["status"] == "draft"

    @pytest.mark.respx
    def test_both_404_false(self, strapi_config: StrapiConfig, respx_mock: respx.Router) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        with SyncClient(strapi_config) as client:
            assert client.exists_in_locale(COLLECTION, DOCUMENT_ID, locale="fr") is False

        assert route.call_count == 2
        assert route.calls[1].request.url.params["status"] == "draft"

    @pytest.mark.respx
    def test_invalid_key_locale_retries_published_without_locale(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_locale(
                Response(400, json=INVALID_LOCALE_BODY),
                Response(200, json=mock_v5_response),
                locale="fr",
            )
        )

        with SyncClient(strapi_config) as client:
            assert client.exists_in_locale(COLLECTION, DOCUMENT_ID, locale="fr") is True

        assert route.call_count == 2
        assert route.calls[0].request.url.params["locale"] == "fr"
        assert "locale" not in route.calls[1].request.url.params
        assert "status" not in route.calls[1].request.url.params

    @pytest.mark.respx
    def test_invalid_key_locale_on_draft_keeps_status_draft(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        def _handler(request: httpx.Request) -> Response:
            locale = request.url.params.get("locale")
            status = request.url.params.get("status")
            if locale == "fr" and status != "draft":
                return _not_found()
            if locale == "fr" and status == "draft":
                return Response(400, json=INVALID_LOCALE_BODY)
            if status == "draft" and locale is None:
                return Response(200, json=mock_v5_response)
            return _not_found()

        route = respx_mock.get(DOCUMENT_URL).mock(side_effect=_handler)

        with SyncClient(strapi_config) as client:
            assert client.exists_in_locale(COLLECTION, DOCUMENT_ID, locale="fr") is True

        assert route.call_count == 3
        assert route.calls[0].request.url.params["locale"] == "fr"
        assert "status" not in route.calls[0].request.url.params
        assert route.calls[1].request.url.params["locale"] == "fr"
        assert route.calls[1].request.url.params["status"] == "draft"
        assert "locale" not in route.calls[2].request.url.params
        assert route.calls[2].request.url.params["status"] == "draft"

    @pytest.mark.respx
    def test_none_locale_matches_exists(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(return_value=Response(200, json=mock_v5_response))

        with SyncClient(strapi_config) as client:
            assert client.exists_in_locale(COLLECTION, DOCUMENT_ID) is True

        assert route.call_count == 1
        assert "locale" not in route.calls[0].request.url.params

    @pytest.mark.respx
    def test_unrelated_400_still_raises(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(
            return_value=Response(400, json={"error": {"message": "Invalid key populate"}})
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="Invalid key populate"):
                client.exists_in_locale(COLLECTION, DOCUMENT_ID, locale="fr")

        assert route.call_count == 1

    def test_rejects_multi_segment_collection(self, strapi_config: StrapiConfig) -> None:
        with SyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="single path segment"):
                client.exists_in_locale("articles/../upload", DOCUMENT_ID, locale="fr")


class TestAsyncExistsInLocale:
    """AsyncClient.exists_in_locale published-then-draft, optional locale."""

    @pytest.mark.respx
    async def test_published_hit_sends_locale(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(return_value=Response(200, json=mock_v5_response))

        async with AsyncClient(strapi_config) as client:
            assert await client.exists_in_locale(COLLECTION, DOCUMENT_ID, locale="fr") is True

        assert route.call_count == 1
        assert route.calls[0].request.url.params["locale"] == "fr"

    @pytest.mark.respx
    async def test_published_404_draft_hit_keeps_locale(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status_and_locale(
                _not_found(), Response(200, json=mock_v5_response), locale="fr"
            )
        )

        async with AsyncClient(strapi_config) as client:
            assert await client.exists_in_locale(COLLECTION, DOCUMENT_ID, locale="fr") is True

        assert route.call_count == 2
        assert route.calls[1].request.url.params["locale"] == "fr"
        assert route.calls[1].request.url.params["status"] == "draft"

    @pytest.mark.respx
    async def test_invalid_key_locale_retries_published_without_locale(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_locale(
                Response(400, json=INVALID_LOCALE_BODY),
                Response(200, json=mock_v5_response),
                locale="fr",
            )
        )

        async with AsyncClient(strapi_config) as client:
            assert await client.exists_in_locale(COLLECTION, DOCUMENT_ID, locale="fr") is True

        assert route.call_count == 2
        assert "locale" not in route.calls[1].request.url.params

    @pytest.mark.respx
    async def test_invalid_key_locale_on_draft_keeps_status_draft(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        def _handler(request: httpx.Request) -> Response:
            locale = request.url.params.get("locale")
            status = request.url.params.get("status")
            if locale == "fr" and status != "draft":
                return _not_found()
            if locale == "fr" and status == "draft":
                return Response(400, json=INVALID_LOCALE_BODY)
            if status == "draft" and locale is None:
                return Response(200, json=mock_v5_response)
            return _not_found()

        route = respx_mock.get(DOCUMENT_URL).mock(side_effect=_handler)

        async with AsyncClient(strapi_config) as client:
            assert await client.exists_in_locale(COLLECTION, DOCUMENT_ID, locale="fr") is True

        assert route.call_count == 3
        assert route.calls[2].request.url.params["status"] == "draft"
        assert "locale" not in route.calls[2].request.url.params

    @pytest.mark.respx
    async def test_both_404_false(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        async with AsyncClient(strapi_config) as client:
            assert await client.exists_in_locale(COLLECTION, DOCUMENT_ID, locale="fr") is False

        assert route.call_count == 2
        assert route.calls[1].request.url.params["status"] == "draft"

    @pytest.mark.respx
    async def test_none_locale_matches_exists(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(return_value=Response(200, json=mock_v5_response))

        async with AsyncClient(strapi_config) as client:
            assert await client.exists_in_locale(COLLECTION, DOCUMENT_ID) is True

        assert route.call_count == 1
        assert "locale" not in route.calls[0].request.url.params

    @pytest.mark.respx
    async def test_unrelated_400_still_raises(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.get(DOCUMENT_URL).mock(
            return_value=Response(400, json={"error": {"message": "Invalid key populate"}})
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="Invalid key populate"):
                await client.exists_in_locale(COLLECTION, DOCUMENT_ID, locale="fr")

        assert route.call_count == 1

    async def test_rejects_multi_segment_collection(self, strapi_config: StrapiConfig) -> None:
        async with AsyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="single path segment"):
                await client.exists_in_locale("articles/../upload", DOCUMENT_ID, locale="fr")


class TestSyncClassifyWrite404:
    """Opt-in write-404 remapping on SyncClient.update / remove."""

    @pytest.mark.respx
    def test_update_404_addressed_variant_readable_is_write_rejected(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        put_route = respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(
                Response(200, json=mock_v5_response),
                _not_found(),
            )
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.update(ENDPOINT, {"title": "x"}, classify_write_404=True)

        assert put_route.called
        assert get_route.call_count == 1
        assert "status" not in get_route.calls[0].request.url.params
        _assert_write_rejected(exc_info.value, "update")
        assert exc_info.value.details["status_code"] == 404

    @pytest.mark.respx
    def test_update_404_draft_only_stays_not_found(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(_not_found(), Response(200, json=mock_v5_response))
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.update(ENDPOINT, {"title": "x"}, classify_write_404=True)

        assert not isinstance(exc_info.value, AuthorizationError)
        assert exc_info.value.details["classified_from"] == "draft_only"
        assert (
            exc_info.value.message
            == "document exists only as a draft; no published version to update."
        )
        assert exc_info.value.status_code == 404
        assert get_route.call_count == 2
        assert "status" not in get_route.calls[0].request.url.params
        assert get_route.calls[1].request.url.params["status"] == "draft"

    @pytest.mark.respx
    def test_update_published_status_404_draft_only(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(_not_found(), Response(200, json=mock_v5_response))
        )
        query = StrapiQuery().with_document_status(DocumentStatus.PUBLISHED)

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.update(
                    ENDPOINT,
                    {"title": "x"},
                    query=query,
                    classify_write_404=True,
                )

        assert exc_info.value.details["classified_from"] == "draft_only"
        assert get_route.call_count == 2
        assert get_route.calls[0].request.url.params["status"] == "published"
        assert get_route.calls[1].request.url.params["status"] == "draft"

    @pytest.mark.respx
    def test_remove_404_addressed_variant_readable_is_write_rejected(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.delete(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(
                Response(200, json=mock_v5_response),
                _not_found(),
            )
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.remove(ENDPOINT, classify_write_404=True)

        _assert_write_rejected(exc_info.value, "delete")
        assert get_route.call_count == 1

    @pytest.mark.respx
    def test_remove_404_draft_exists_authorization(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.delete(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(_not_found(), Response(200, json=mock_v5_response))
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(AuthorizationError) as exc_info:
                client.remove(ENDPOINT, classify_write_404=True)

        assert exc_info.value.details["status_code"] == 404
        assert exc_info.value.details["classified_from"] == "write_404"
        assert exc_info.value.message == "document exists; token likely lacks Delete."
        assert get_route.call_count == 2

    @pytest.mark.respx
    def test_update_404_draft_404_original_not_found(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.update(ENDPOINT, {"title": "x"}, classify_write_404=True)

        assert get_route.call_count == 2
        assert isinstance(exc_info.value, NotFoundError)
        assert exc_info.value.status_code == 404
        assert not isinstance(exc_info.value, AuthorizationError)
        assert exc_info.value.details.get("classified_from") != "draft_only"

    @pytest.mark.respx
    def test_update_404_probe_exception_keeps_original(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        respx_mock.get(DOCUMENT_URL).mock(side_effect=httpx.ConnectError("boom"))

        with SyncClient(_no_retry(strapi_config)) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.update(ENDPOINT, {"title": "x"}, classify_write_404=True)

        assert exc_info.value.status_code == 404

    @pytest.mark.respx
    def test_update_404_empty_probe_keeps_not_found(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        respx_mock.get(DOCUMENT_URL).mock(return_value=Response(200, json=EMPTY_DATA_BODY))

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.update(ENDPOINT, {"title": "x"}, classify_write_404=True)

        assert exc_info.value.status_code == 404
        assert not isinstance(exc_info.value, AuthorizationError)

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

    @pytest.mark.respx
    def test_default_remove_404_unchanged(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.delete(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError):
                client.remove(ENDPOINT)

        assert get_route.call_count == 0


class TestAsyncClassifyWrite404:
    """Opt-in write-404 remapping on AsyncClient.update / remove."""

    @pytest.mark.respx
    async def test_update_404_addressed_variant_readable_is_write_rejected(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(
                Response(200, json=mock_v5_response),
                _not_found(),
            )
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                await client.update(ENDPOINT, {"title": "x"}, classify_write_404=True)

        assert get_route.call_count == 1
        assert "status" not in get_route.calls[0].request.url.params
        _assert_write_rejected(exc_info.value, "update")
        assert exc_info.value.details["status_code"] == 404

    @pytest.mark.respx
    async def test_update_404_draft_only_stays_not_found(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(_not_found(), Response(200, json=mock_v5_response))
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                await client.update(ENDPOINT, {"title": "x"}, classify_write_404=True)

        assert not isinstance(exc_info.value, AuthorizationError)
        assert exc_info.value.details["classified_from"] == "draft_only"
        assert (
            exc_info.value.message
            == "document exists only as a draft; no published version to update."
        )
        assert get_route.call_count == 2
        assert get_route.calls[1].request.url.params["status"] == "draft"

    @pytest.mark.respx
    async def test_remove_404_draft_exists_authorization(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.delete(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(_not_found(), Response(200, json=mock_v5_response))
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(AuthorizationError) as exc_info:
                await client.remove(ENDPOINT, classify_write_404=True)

        assert exc_info.value.details["status_code"] == 404
        assert exc_info.value.message == "document exists; token likely lacks Delete."
        assert get_route.call_count == 2

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
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        respx_mock.get(DOCUMENT_URL).mock(side_effect=httpx.ConnectError("boom"))

        async with AsyncClient(_no_retry(strapi_config)) as client:
            with pytest.raises(NotFoundError) as exc_info:
                await client.update(ENDPOINT, {"title": "x"}, classify_write_404=True)

        assert exc_info.value.status_code == 404

    @pytest.mark.respx
    async def test_update_404_empty_probe_keeps_not_found(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        respx_mock.get(DOCUMENT_URL).mock(return_value=Response(200, json=EMPTY_DATA_BODY))

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                await client.update(ENDPOINT, {"title": "x"}, classify_write_404=True)

        assert exc_info.value.status_code == 404
        assert not isinstance(exc_info.value, AuthorizationError)

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

    @pytest.mark.respx
    async def test_default_remove_404_unchanged(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.delete(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError):
                await client.remove(ENDPOINT)

        assert get_route.call_count == 0


def _route_by_status_and_locale(
    published: Response,
    draft: Response,
    *,
    locale: str,
) -> Any:
    def _handler(request: httpx.Request) -> Response:
        if request.url.params.get("locale") != locale:
            return _not_found()
        if request.url.params.get("status") == "draft":
            return draft
        return published

    return _handler


class TestSyncClassifyWrite404LocaleAndPublish:
    """Locale-preserving probes and opt-in publish classification."""

    @pytest.mark.respx
    def test_update_404_preserves_locale_on_both_probes(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status_and_locale(
                _not_found(), Response(200, json=mock_v5_response), locale="fr"
            )
        )
        query = StrapiQuery().with_locale("fr").with_document_status(DocumentStatus.PUBLISHED)

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.update(ENDPOINT, {"title": "x"}, query=query, classify_write_404=True)

        assert exc_info.value.details["classified_from"] == "draft_only"
        assert get_route.call_count == 2
        assert get_route.calls[0].request.url.params["locale"] == "fr"
        assert get_route.calls[0].request.url.params["status"] == "published"
        assert get_route.calls[1].request.url.params["locale"] == "fr"
        assert get_route.calls[1].request.url.params["status"] == "draft"

    @pytest.mark.respx
    def test_update_404_does_not_treat_other_locale_as_addressed(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status_and_locale(
                Response(200, json=mock_v5_response),
                Response(200, json=mock_v5_response),
                locale="en",
            )
        )
        query = StrapiQuery().with_locale("fr")

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.update(ENDPOINT, {"title": "x"}, query=query, classify_write_404=True)

        assert exc_info.value.details.get("classified_from") != "draft_only"
        assert not isinstance(exc_info.value, AuthorizationError)
        assert get_route.call_count == 2
        assert get_route.calls[0].request.url.params["locale"] == "fr"
        assert get_route.calls[1].request.url.params["locale"] == "fr"

    @pytest.mark.respx
    def test_remove_404_preserves_locale_on_probes(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        delete_route = respx_mock.delete(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status_and_locale(
                _not_found(), Response(200, json=mock_v5_response), locale="fr"
            )
        )
        query = StrapiQuery().with_locale("fr")

        with SyncClient(strapi_config) as client:
            with pytest.raises(AuthorizationError) as exc_info:
                client.remove(ENDPOINT, query=query, classify_write_404=True)

        assert delete_route.calls[0].request.url.params["locale"] == "fr"
        assert exc_info.value.details["classified_from"] == "write_404"
        assert get_route.call_count == 2
        assert get_route.calls[0].request.url.params["locale"] == "fr"
        assert get_route.calls[1].request.url.params["locale"] == "fr"
        assert get_route.calls[1].request.url.params["status"] == "draft"

    @pytest.mark.respx
    def test_publish_404_draft_only_is_authorization(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(_not_found(), Response(200, json=mock_v5_response))
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(AuthorizationError) as exc_info:
                client.publish(COLLECTION, DOCUMENT_ID, classify_write_404=True)

        assert exc_info.value.details["classified_from"] == "write_404"
        assert exc_info.value.message == "document exists; token likely lacks Publish."
        assert get_route.call_count == 2
        assert get_route.calls[0].request.url.params["status"] == "published"
        assert get_route.calls[1].request.url.params["status"] == "draft"

    @pytest.mark.respx
    def test_publish_404_addressed_variant_readable_is_write_rejected(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(
                Response(200, json=mock_v5_response),
                _not_found(),
            )
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.publish(COLLECTION, DOCUMENT_ID, classify_write_404=True)

        _assert_write_rejected(exc_info.value, "publish")
        assert get_route.call_count == 1
        assert get_route.calls[0].request.url.params["status"] == "published"

    @pytest.mark.respx
    def test_publish_404_preserves_locale(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status_and_locale(
                _not_found(), Response(200, json=mock_v5_response), locale="fr"
            )
        )
        query = StrapiQuery().with_locale("fr")

        with SyncClient(strapi_config) as client:
            with pytest.raises(AuthorizationError) as exc_info:
                client.publish(COLLECTION, DOCUMENT_ID, query=query, classify_write_404=True)

        assert exc_info.value.details["classified_from"] == "write_404"
        assert exc_info.value.message == "document exists; token likely lacks Publish."
        assert get_route.call_count == 2
        assert get_route.calls[0].request.url.params["locale"] == "fr"
        assert get_route.calls[0].request.url.params["status"] == "published"
        assert get_route.calls[1].request.url.params["locale"] == "fr"
        assert get_route.calls[1].request.url.params["status"] == "draft"

    @pytest.mark.respx
    def test_update_404_probe_omits_populate(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(
                Response(200, json=mock_v5_response),
                _not_found(),
            )
        )
        query = StrapiQuery().with_locale("fr").populate_fields(["author"])

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.update(ENDPOINT, {"title": "x"}, query=query, classify_write_404=True)

        _assert_write_rejected(exc_info.value, "update")
        params = get_route.calls[0].request.url.params
        assert params["locale"] == "fr"
        assert "populate" not in params
        assert "populate[0]" not in params

    @pytest.mark.respx
    def test_default_publish_404_unchanged(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError):
                client.publish(COLLECTION, DOCUMENT_ID)

        assert get_route.call_count == 0


def _route_by_publication_state(
    live: Response,
    preview: Response,
) -> Any:
    def _handler(request: httpx.Request) -> Response:
        params = request.url.params
        if "status" in params:
            return Response(400, json=VALIDATION_BODY)
        if params.get("publicationState") == "preview":
            return preview
        if params.get("publicationState") == "live":
            return live
        return live

    return _handler


class TestSyncClassifyWrite404PublicationStateAndDraftWrite:
    """v4 publicationState probes and writes that already address draft."""

    @pytest.mark.respx
    def test_update_404_publication_state_live_draft_only(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_publication_state(
                _not_found(), Response(200, json=mock_v5_response)
            )
        )
        query = StrapiQuery().with_publication_state(PublicationState.LIVE)

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.update(ENDPOINT, {"title": "x"}, query=query, classify_write_404=True)

        assert exc_info.value.details["classified_from"] == "draft_only"
        assert get_route.call_count == 2
        assert get_route.calls[0].request.url.params["publicationState"] == "live"
        assert get_route.calls[1].request.url.params["publicationState"] == "preview"
        assert "status" not in get_route.calls[0].request.url.params
        assert "status" not in get_route.calls[1].request.url.params

    @pytest.mark.respx
    def test_update_404_publication_state_live_readable_is_write_rejected(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_publication_state(
                Response(200, json=mock_v5_response), _not_found()
            )
        )
        query = StrapiQuery().with_publication_state(PublicationState.LIVE)

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.update(ENDPOINT, {"title": "x"}, query=query, classify_write_404=True)

        _assert_write_rejected(exc_info.value, "update")
        assert get_route.call_count == 1
        assert get_route.calls[0].request.url.params["publicationState"] == "live"
        assert "status" not in get_route.calls[0].request.url.params

    @pytest.mark.respx
    def test_update_404_preview_write_skips_second_probe(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_publication_state(
                _not_found(), Response(200, json=mock_v5_response)
            )
        )
        query = StrapiQuery().with_publication_state(PublicationState.PREVIEW)

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.update(ENDPOINT, {"title": "x"}, query=query, classify_write_404=True)

        _assert_write_rejected(exc_info.value, "update")
        assert get_route.call_count == 1
        assert get_route.calls[0].request.url.params["publicationState"] == "preview"
        assert "status" not in get_route.calls[0].request.url.params

    @pytest.mark.respx
    def test_update_404_draft_status_readable_is_write_rejected(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(_not_found(), Response(200, json=mock_v5_response))
        )
        query = StrapiQuery().with_document_status(DocumentStatus.DRAFT)

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.update(ENDPOINT, {"title": "x"}, query=query, classify_write_404=True)

        _assert_write_rejected(exc_info.value, "update")
        assert get_route.call_count == 1
        assert get_route.calls[0].request.url.params["status"] == "draft"

    @pytest.mark.respx
    def test_update_404_draft_status_both_miss_keeps_original(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())
        query = StrapiQuery().with_document_status(DocumentStatus.DRAFT)

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.update(ENDPOINT, {"title": "x"}, query=query, classify_write_404=True)

        assert get_route.call_count == 1
        assert get_route.calls[0].request.url.params["status"] == "draft"
        assert not isinstance(exc_info.value, AuthorizationError)
        assert exc_info.value.details.get("classified_from") != "draft_only"


class TestAsyncClassifyWrite404LocaleAndPublish:
    """Async locale-preserving probes and publish classification."""

    @pytest.mark.respx
    async def test_update_404_preserves_locale_on_both_probes(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status_and_locale(
                _not_found(), Response(200, json=mock_v5_response), locale="fr"
            )
        )
        query = StrapiQuery().with_locale("fr").with_document_status(DocumentStatus.PUBLISHED)

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                await client.update(ENDPOINT, {"title": "x"}, query=query, classify_write_404=True)

        assert exc_info.value.details["classified_from"] == "draft_only"
        assert get_route.call_count == 2
        assert get_route.calls[1].request.url.params["locale"] == "fr"

    @pytest.mark.respx
    async def test_publish_404_draft_only_is_authorization(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(_not_found(), Response(200, json=mock_v5_response))
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(AuthorizationError) as exc_info:
                await client.publish(COLLECTION, DOCUMENT_ID, classify_write_404=True)

        assert exc_info.value.details["classified_from"] == "write_404"
        assert exc_info.value.message == "document exists; token likely lacks Publish."
        assert get_route.call_count == 2
        assert get_route.calls[0].request.url.params["status"] == "published"
        assert get_route.calls[1].request.url.params["status"] == "draft"

    @pytest.mark.respx
    async def test_publish_404_addressed_variant_readable_is_write_rejected(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(
                Response(200, json=mock_v5_response),
                _not_found(),
            )
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                await client.publish(COLLECTION, DOCUMENT_ID, classify_write_404=True)

        _assert_write_rejected(exc_info.value, "publish")
        assert get_route.call_count == 1
        assert get_route.calls[0].request.url.params["status"] == "published"

    @pytest.mark.respx
    async def test_publish_404_preserves_locale(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status_and_locale(
                _not_found(), Response(200, json=mock_v5_response), locale="fr"
            )
        )
        query = StrapiQuery().with_locale("fr")

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(AuthorizationError) as exc_info:
                await client.publish(COLLECTION, DOCUMENT_ID, query=query, classify_write_404=True)

        assert exc_info.value.details["classified_from"] == "write_404"
        assert exc_info.value.message == "document exists; token likely lacks Publish."
        assert get_route.call_count == 2
        assert get_route.calls[0].request.url.params["locale"] == "fr"
        assert get_route.calls[0].request.url.params["status"] == "published"
        assert get_route.calls[1].request.url.params["locale"] == "fr"
        assert get_route.calls[1].request.url.params["status"] == "draft"

    @pytest.mark.respx
    async def test_update_404_publication_state_live_draft_only(
        self, strapi_config: StrapiConfig, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_publication_state(
                _not_found(), Response(200, json=mock_v5_response)
            )
        )
        query = StrapiQuery().with_publication_state(PublicationState.LIVE)

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                await client.update(ENDPOINT, {"title": "x"}, query=query, classify_write_404=True)

        assert exc_info.value.details["classified_from"] == "draft_only"
        assert get_route.call_count == 2
        assert get_route.calls[0].request.url.params["publicationState"] == "live"
        assert get_route.calls[1].request.url.params["publicationState"] == "preview"
        assert "status" not in get_route.calls[1].request.url.params

    @pytest.mark.respx
    async def test_update_404_draft_status_both_miss_keeps_original(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())
        query = StrapiQuery().with_document_status(DocumentStatus.DRAFT)

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                await client.update(ENDPOINT, {"title": "x"}, query=query, classify_write_404=True)

        assert get_route.call_count == 1
        assert get_route.calls[0].request.url.params["status"] == "draft"
        assert exc_info.value.details.get("classified_from") != "draft_only"

    @pytest.mark.respx
    async def test_default_publish_404_unchanged(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.put(DOCUMENT_URL).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError):
                await client.publish(COLLECTION, DOCUMENT_ID)

        assert get_route.call_count == 0


_ACTION_CASES = (
    pytest.param("unpublish", "unpublish", "Unpublish", "unpublish", id="unpublish"),
    pytest.param("discard_draft", "discardDraft", "Discard", "discard", id="discard_draft"),
)


def _action_url(action_segment: str) -> str:
    return f"{DOCUMENT_URL}/actions/{action_segment}"


class TestSyncClassifyWrite404Actions:
    """Opt-in classify_write_404 on custom-route unpublish / discard_draft."""

    @pytest.mark.respx
    @pytest.mark.parametrize(
        ("method_name", "action_segment", "_permission", "_verb"), _ACTION_CASES
    )
    def test_default_404_unchanged(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
        method_name: str,
        action_segment: str,
        _permission: str,
        _verb: str,
    ) -> None:
        respx_mock.post(_action_url(action_segment)).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                getattr(client, method_name)(COLLECTION, DOCUMENT_ID)

        assert get_route.call_count == 0
        assert exc_info.value.details.get("classified_from") is None

    @pytest.mark.respx
    @pytest.mark.parametrize(
        ("method_name", "action_segment", "_permission", "_verb"), _ACTION_CASES
    )
    def test_default_405_unchanged(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
        method_name: str,
        action_segment: str,
        _permission: str,
        _verb: str,
    ) -> None:
        respx_mock.post(_action_url(action_segment)).mock(
            return_value=Response(405, json={"error": {"message": "nope"}})
        )
        get_route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        with SyncClient(strapi_config) as client:
            with pytest.raises(MethodNotAllowedError) as exc_info:
                getattr(client, method_name)(COLLECTION, DOCUMENT_ID, classify_write_404=True)

        assert get_route.call_count == 0
        assert exc_info.value.status_code == 405

    @pytest.mark.respx
    @pytest.mark.parametrize(
        ("method_name", "action_segment", "_permission", "verb"), _ACTION_CASES
    )
    def test_addressed_variant_readable_is_write_rejected(
        self,
        strapi_config: StrapiConfig,
        mock_v5_response: dict,
        respx_mock: respx.Router,
        method_name: str,
        action_segment: str,
        _permission: str,
        verb: str,
    ) -> None:
        respx_mock.post(_action_url(action_segment)).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(
                Response(200, json=mock_v5_response),
                _not_found(),
            )
        )
        action_get = respx_mock.get(_action_url(action_segment)).mock(return_value=_not_found())

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                getattr(client, method_name)(COLLECTION, DOCUMENT_ID, classify_write_404=True)

        _assert_write_rejected(exc_info.value, verb)
        assert get_route.call_count == 1
        assert "status" not in get_route.calls[0].request.url.params
        assert action_get.call_count == 0

    @pytest.mark.respx
    @pytest.mark.parametrize(
        ("method_name", "action_segment", "_permission", "verb"), _ACTION_CASES
    )
    def test_draft_only_stays_not_found(
        self,
        strapi_config: StrapiConfig,
        mock_v5_response: dict,
        respx_mock: respx.Router,
        method_name: str,
        action_segment: str,
        _permission: str,
        verb: str,
    ) -> None:
        respx_mock.post(_action_url(action_segment)).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(_not_found(), Response(200, json=mock_v5_response))
        )
        action_get = respx_mock.get(_action_url(action_segment)).mock(return_value=_not_found())

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                getattr(client, method_name)(COLLECTION, DOCUMENT_ID, classify_write_404=True)

        _assert_draft_only(exc_info.value, verb)
        assert get_route.call_count == 2
        assert "status" not in get_route.calls[0].request.url.params
        assert get_route.calls[1].request.url.params["status"] == "draft"
        assert action_get.call_count == 0

    @pytest.mark.respx
    @pytest.mark.parametrize(
        ("method_name", "action_segment", "_permission", "_verb"), _ACTION_CASES
    )
    def test_document_miss_keeps_original_not_found(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
        method_name: str,
        action_segment: str,
        _permission: str,
        _verb: str,
    ) -> None:
        respx_mock.post(_action_url(action_segment)).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                getattr(client, method_name)(COLLECTION, DOCUMENT_ID, classify_write_404=True)

        assert get_route.call_count == 2
        _assert_unclassified_not_found(exc_info.value)

    @pytest.mark.respx
    @pytest.mark.parametrize(
        ("method_name", "action_segment", "_permission", "verb"), _ACTION_CASES
    )
    def test_preserves_locale_on_probes(
        self,
        strapi_config: StrapiConfig,
        mock_v5_response: dict,
        respx_mock: respx.Router,
        method_name: str,
        action_segment: str,
        _permission: str,
        verb: str,
    ) -> None:
        post_route = respx_mock.post(_action_url(action_segment)).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status_and_locale(
                Response(200, json=mock_v5_response),
                _not_found(),
                locale="fr",
            )
        )
        query = StrapiQuery().with_locale("fr")

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                getattr(client, method_name)(
                    COLLECTION, DOCUMENT_ID, query=query, classify_write_404=True
                )

        assert post_route.calls[0].request.url.params["locale"] == "fr"
        _assert_write_rejected(exc_info.value, verb)
        assert get_route.call_count == 1
        assert get_route.calls[0].request.url.params["locale"] == "fr"
        assert "status" not in get_route.calls[0].request.url.params


class TestAsyncClassifyWrite404Actions:
    """Async opt-in classify_write_404 on unpublish / discard_draft."""

    @pytest.mark.respx
    @pytest.mark.parametrize(
        ("method_name", "action_segment", "_permission", "_verb"), _ACTION_CASES
    )
    async def test_default_404_unchanged(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
        method_name: str,
        action_segment: str,
        _permission: str,
        _verb: str,
    ) -> None:
        respx_mock.post(_action_url(action_segment)).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                await getattr(client, method_name)(COLLECTION, DOCUMENT_ID)

        assert get_route.call_count == 0
        _assert_unclassified_not_found(exc_info.value)

    @pytest.mark.respx
    @pytest.mark.parametrize(
        ("method_name", "action_segment", "_permission", "_verb"), _ACTION_CASES
    )
    async def test_default_405_unchanged(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
        method_name: str,
        action_segment: str,
        _permission: str,
        _verb: str,
    ) -> None:
        respx_mock.post(_action_url(action_segment)).mock(
            return_value=Response(405, json={"error": {"message": "nope"}})
        )
        get_route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(MethodNotAllowedError) as exc_info:
                await getattr(client, method_name)(COLLECTION, DOCUMENT_ID, classify_write_404=True)

        assert get_route.call_count == 0
        assert exc_info.value.status_code == 405

    @pytest.mark.respx
    @pytest.mark.parametrize(
        ("method_name", "action_segment", "_permission", "verb"), _ACTION_CASES
    )
    async def test_addressed_and_draft_only(
        self,
        strapi_config: StrapiConfig,
        mock_v5_response: dict,
        respx_mock: respx.Router,
        method_name: str,
        action_segment: str,
        _permission: str,
        verb: str,
    ) -> None:
        respx_mock.post(_action_url(action_segment)).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status(
                Response(200, json=mock_v5_response),
                _not_found(),
            )
        )
        action_get = respx_mock.get(_action_url(action_segment)).mock(return_value=_not_found())

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as addressed:
                await getattr(client, method_name)(COLLECTION, DOCUMENT_ID, classify_write_404=True)

        _assert_write_rejected(addressed.value, verb)
        assert get_route.call_count == 1
        assert action_get.call_count == 0

        get_route.reset()
        get_route.mock(
            side_effect=_route_by_status(_not_found(), Response(200, json=mock_v5_response))
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as draft_only:
                await getattr(client, method_name)(COLLECTION, DOCUMENT_ID, classify_write_404=True)

        _assert_draft_only(draft_only.value, verb)
        assert get_route.call_count == 2
        assert action_get.call_count == 0

    @pytest.mark.respx
    @pytest.mark.parametrize(
        ("method_name", "action_segment", "_permission", "_verb"), _ACTION_CASES
    )
    async def test_document_miss_keeps_original_not_found(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
        method_name: str,
        action_segment: str,
        _permission: str,
        _verb: str,
    ) -> None:
        respx_mock.post(_action_url(action_segment)).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(return_value=_not_found())

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                await getattr(client, method_name)(COLLECTION, DOCUMENT_ID, classify_write_404=True)

        assert get_route.call_count == 2
        _assert_unclassified_not_found(exc_info.value)

    @pytest.mark.respx
    @pytest.mark.parametrize(
        ("method_name", "action_segment", "_permission", "_verb"), _ACTION_CASES
    )
    async def test_preserves_locale_on_probes(
        self,
        strapi_config: StrapiConfig,
        mock_v5_response: dict,
        respx_mock: respx.Router,
        method_name: str,
        action_segment: str,
        _permission: str,
        _verb: str,
    ) -> None:
        post_route = respx_mock.post(_action_url(action_segment)).mock(return_value=_not_found())
        get_route = respx_mock.get(DOCUMENT_URL).mock(
            side_effect=_route_by_status_and_locale(
                _not_found(), Response(200, json=mock_v5_response), locale="fr"
            )
        )
        query = StrapiQuery().with_locale("fr")

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                await getattr(client, method_name)(
                    COLLECTION, DOCUMENT_ID, query=query, classify_write_404=True
                )

        assert post_route.calls[0].request.url.params["locale"] == "fr"
        _assert_draft_only(exc_info.value, _verb)
        assert get_route.call_count == 2
        assert get_route.calls[0].request.url.params["locale"] == "fr"
        assert get_route.calls[1].request.url.params["locale"] == "fr"
        assert get_route.calls[1].request.url.params["status"] == "draft"
