"""Strapi v5 document actions and honest 2xx handling."""

import pytest
import respx
from httpx import Response

from strapi_kit import AsyncClient, SyncClient, ValidationError
from strapi_kit.exceptions import (
    AuthenticationError,
    MethodNotAllowedError,
    NotFoundError,
    UnstructuredResponseError,
)


class TestDocumentActions:
    """publish() / unpublish() hit the v5 document-action routes."""

    @pytest.mark.respx
    def test_publish_posts_actions_publish(
        self, strapi_config, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.post(
            "http://localhost:1337/api/articles/doc_test_001/actions/publish"
        ).mock(return_value=Response(200, json=mock_v5_response))

        with SyncClient(strapi_config) as client:
            result = client.publish("articles", "doc_test_001")

        assert route.called
        assert result.data is not None
        assert result.data.document_id == mock_v5_response["data"]["documentId"]

    @pytest.mark.respx
    def test_unpublish_posts_actions_unpublish(
        self, strapi_config, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.post(
            "http://localhost:1337/api/articles/doc_test_001/actions/unpublish"
        ).mock(return_value=Response(200, json=mock_v5_response))

        with SyncClient(strapi_config) as client:
            client.unpublish("articles", "doc_test_001")

        assert route.called

    @pytest.mark.respx
    def test_publish_percent_encodes_document_id(
        self, strapi_config, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        route = respx_mock.post(
            "http://localhost:1337/api/articles/a%2Fb%3Fc/actions/publish"
        ).mock(return_value=Response(200, json=mock_v5_response))

        with SyncClient(strapi_config) as client:
            client.publish("articles", "a/b?c")

        assert route.called

    def test_publish_rejects_blank_document_id(self, strapi_config) -> None:
        with SyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="document_id"):
                client.publish("articles", "  ")

    def test_publish_rejects_blank_collection(self, strapi_config) -> None:
        with SyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="collection"):
                client.publish("", "abc123")

    @pytest.mark.respx
    async def test_async_publish(
        self, strapi_config, mock_v5_response: dict, respx_mock: respx.Router
    ) -> None:
        respx_mock.post("http://localhost:1337/api/articles/doc_test_001/actions/publish").mock(
            return_value=Response(200, json=mock_v5_response)
        )

        async with AsyncClient(strapi_config) as client:
            result = await client.publish("articles", "doc_test_001")

        assert result.data is not None
        assert result.data.document_id == mock_v5_response["data"]["documentId"]


class TestHonestSuccessBodies:
    """2xx empty / non-object bodies must not look like a created entity."""

    @pytest.mark.respx
    def test_empty_create_raises(self, strapi_config, respx_mock: respx.Router) -> None:
        respx_mock.post("http://localhost:1337/api/articles").mock(
            return_value=Response(201, content=b"")
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(UnstructuredResponseError) as exc_info:
                client.post("articles", json={"data": {"title": "x"}})
            assert exc_info.value.status_code == 201
            assert "empty body" in str(exc_info.value)

    @pytest.mark.respx
    def test_created_string_body_raises(self, strapi_config, respx_mock: respx.Router) -> None:
        respx_mock.post("http://localhost:1337/api/articles").mock(
            return_value=Response(201, json="Created")
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(UnstructuredResponseError) as exc_info:
                client.post("articles", json={"data": {"title": "x"}})
            assert exc_info.value.status_code == 201
            assert exc_info.value.details.get("parsed_type") == "str"

    @pytest.mark.respx
    def test_delete_204_is_empty_success(self, strapi_config, respx_mock: respx.Router) -> None:
        respx_mock.delete("http://localhost:1337/api/articles/1").mock(return_value=Response(204))

        with SyncClient(strapi_config) as client:
            assert client.delete("articles/1") == {}

    @pytest.mark.respx
    def test_empty_get_raises(self, strapi_config, respx_mock: respx.Router) -> None:
        respx_mock.get("http://localhost:1337/api/articles/1").mock(
            return_value=Response(200, content=b"")
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(UnstructuredResponseError) as exc_info:
                client.get("articles/1")
            assert exc_info.value.status_code == 200


class TestHttpErrorStatusCodes:
    """Every HTTP error exposes status_code (not just ServerError)."""

    @pytest.mark.respx
    def test_401_has_status_code(self, strapi_config, respx_mock: respx.Router) -> None:
        respx_mock.get("http://localhost:1337/api/articles").mock(
            return_value=Response(401, json={"error": {"message": "nope"}})
        )
        with SyncClient(strapi_config) as client:
            with pytest.raises(AuthenticationError) as exc_info:
                client.get("articles")
            assert exc_info.value.status_code == 401

    @pytest.mark.respx
    def test_404_has_status_code(self, strapi_config, respx_mock: respx.Router) -> None:
        respx_mock.get("http://localhost:1337/api/articles/missing").mock(
            return_value=Response(404, json={"error": {"message": "gone"}})
        )
        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.get("articles/missing")
            assert exc_info.value.status_code == 404

    @pytest.mark.respx
    def test_405_is_method_not_allowed(self, strapi_config, respx_mock: respx.Router) -> None:
        respx_mock.post("http://localhost:1337/api/articles/abc/actions/publish").mock(
            return_value=Response(405, json={"error": {"message": "nope"}})
        )
        with SyncClient(strapi_config) as client:
            with pytest.raises(MethodNotAllowedError) as exc_info:
                client.publish("articles", "abc")
            assert exc_info.value.status_code == 405

    @pytest.mark.respx
    def test_422_is_validation_error(self, strapi_config, respx_mock: respx.Router) -> None:
        respx_mock.post("http://localhost:1337/api/articles").mock(
            return_value=Response(422, json={"error": {"message": "slug taken"}})
        )
        with SyncClient(strapi_config) as client:
            with pytest.raises(ValidationError) as exc_info:
                client.post("articles", json={"data": {}})
            assert exc_info.value.status_code == 422
