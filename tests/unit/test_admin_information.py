"""Unit tests for origin-path escape hatch and get_admin_information()."""

from typing import Any

import pytest
import respx
from httpx import Response

from strapi_kit import AsyncClient, StrapiConfig, SyncClient
from strapi_kit.exceptions import AuthenticationError, AuthorizationError, NotFoundError
from strapi_kit.models import AdminInformation

ADMIN_ORIGIN = "http://localhost:1337/admin/information"
ADMIN_API_PREFIXED = "http://localhost:1337/api/admin/information"


def _admin_error_payload(status: int, name: str, message: str) -> dict[str, Any]:
    return {"error": {"status": status, "name": name, "message": message}}


class TestBuildUrlApiPrefix:
    """Direct _build_url coverage for the default prefix and opt-out."""

    def test_default_prefixes_api(self, strapi_config: StrapiConfig) -> None:
        """Default get-style paths still receive the /api prefix."""
        with SyncClient(strapi_config) as client:
            assert client._build_url("admin/information") == ADMIN_API_PREFIXED
            assert client._build_url("/admin/information") == ADMIN_API_PREFIXED
            assert client._build_url("articles") == "http://localhost:1337/api/articles"
            assert client._build_url("api/articles") == "http://localhost:1337/api/articles"

    def test_opt_out_is_origin_rooted(self, strapi_config: StrapiConfig) -> None:
        """api_prefix=False joins the path to the origin without /api."""
        with SyncClient(strapi_config) as client:
            assert client._build_url("admin/information", api_prefix=False) == ADMIN_ORIGIN
            assert client._build_url("/admin/information", api_prefix=False) == ADMIN_ORIGIN
            assert (
                client._build_url("api/articles", api_prefix=False)
                == "http://localhost:1337/api/articles"
            )


class TestAdminInformationParsing:
    """Version extraction from both documented response shapes."""

    def test_top_level_strapi_version(self) -> None:
        payload = {"strapiVersion": "5.11.0", "currentEnvironment": "development"}
        info = AdminInformation.from_response(payload)
        assert info.strapi_version == "5.11.0"
        assert info.raw == payload

    def test_nested_data_strapi_version(self) -> None:
        payload = {"data": {"strapiVersion": "4.25.1", "autoReload": True}}
        info = AdminInformation.from_response(payload)
        assert info.strapi_version == "4.25.1"
        assert info.raw == payload

    def test_missing_version_still_succeeds(self) -> None:
        payload = {"data": {"currentEnvironment": "development"}}
        info = AdminInformation.from_response(payload)
        assert info.strapi_version is None
        assert info.raw == payload

    def test_empty_payload_still_succeeds(self) -> None:
        payload: dict[str, Any] = {}
        info = AdminInformation.from_response(payload)
        assert info.strapi_version is None
        assert info.raw == {}

    def test_top_level_takes_precedence(self) -> None:
        payload = {"strapiVersion": "5.0.0", "data": {"strapiVersion": "4.0.0"}}
        info = AdminInformation.from_response(payload)
        assert info.strapi_version == "5.0.0"

    def test_empty_string_falls_through_to_nested(self) -> None:
        payload = {"strapiVersion": "", "data": {"strapiVersion": "5.2.0"}}
        info = AdminInformation.from_response(payload)
        assert info.strapi_version == "5.2.0"


class TestSyncAdminInformation:
    """Sync client URL routing and get_admin_information()."""

    @pytest.mark.respx
    def test_get_admin_information_still_prefixes_api(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        """Default get('admin/information') must keep today's /api behaviour."""
        respx_mock.get(ADMIN_API_PREFIXED).mock(return_value=Response(200, json={"ok": True}))

        with SyncClient(strapi_config) as client:
            response = client.get("admin/information")
            assert response == {"ok": True}

    @pytest.mark.respx
    def test_request_api_prefix_false_hits_origin(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        payload = {"strapiVersion": "5.11.0"}
        respx_mock.get(ADMIN_ORIGIN).mock(return_value=Response(200, json=payload))

        with SyncClient(strapi_config) as client:
            response = client.request("GET", "admin/information", api_prefix=False)
            assert response == payload

    @pytest.mark.respx
    def test_get_api_prefix_false_hits_origin(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.get(ADMIN_ORIGIN).mock(return_value=Response(200, json={"ok": True}))

        with SyncClient(strapi_config) as client:
            response = client.get("admin/information", api_prefix=False)
            assert response == {"ok": True}

    @pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
    @pytest.mark.respx
    def test_mutating_methods_thread_api_prefix(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router, method: str
    ) -> None:
        route = getattr(respx_mock, method.lower())(ADMIN_ORIGIN)
        route.mock(return_value=Response(200, json={"ok": True}))

        with SyncClient(strapi_config) as client:
            if method == "POST":
                response = client.post("admin/information", json={}, api_prefix=False)
            elif method == "PUT":
                response = client.put("admin/information", json={}, api_prefix=False)
            else:
                response = client.delete("admin/information", api_prefix=False)

            assert response == {"ok": True}
            assert route.called

    @pytest.mark.respx
    def test_get_admin_information_hits_origin(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        payload = {"strapiVersion": "5.11.0", "currentEnvironment": "development"}
        respx_mock.get(ADMIN_ORIGIN).mock(return_value=Response(200, json=payload))

        with SyncClient(strapi_config) as client:
            info = client.get_admin_information()
            assert isinstance(info, AdminInformation)
            assert info.strapi_version == "5.11.0"
            assert info.raw == payload

    @pytest.mark.respx
    def test_get_admin_information_nested_version(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        payload = {"data": {"strapiVersion": "4.25.1"}}
        respx_mock.get(ADMIN_ORIGIN).mock(return_value=Response(200, json=payload))

        with SyncClient(strapi_config) as client:
            info = client.get_admin_information()
            assert info.strapi_version == "4.25.1"
            assert info.raw == payload

    @pytest.mark.respx
    def test_get_admin_information_missing_version(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        payload = {"data": {"currentEnvironment": "development"}}
        respx_mock.get(ADMIN_ORIGIN).mock(return_value=Response(200, json=payload))

        with SyncClient(strapi_config) as client:
            info = client.get_admin_information()
            assert info.strapi_version is None
            assert info.raw == payload

    @pytest.mark.respx
    def test_get_admin_information_401(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.get(ADMIN_ORIGIN).mock(
            return_value=Response(
                401, json=_admin_error_payload(401, "UnauthorizedError", "Invalid token")
            )
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(AuthenticationError) as exc_info:
                client.get_admin_information()
            assert "Invalid token" in str(exc_info.value)
            assert exc_info.value.status_code == 401

    @pytest.mark.respx
    def test_get_admin_information_403(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.get(ADMIN_ORIGIN).mock(
            return_value=Response(
                403, json=_admin_error_payload(403, "ForbiddenError", "Forbidden")
            )
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(AuthorizationError) as exc_info:
                client.get_admin_information()
            assert "Forbidden" in str(exc_info.value)
            assert exc_info.value.status_code == 403

    @pytest.mark.respx
    def test_get_admin_information_404(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.get(ADMIN_ORIGIN).mock(
            return_value=Response(404, json=_admin_error_payload(404, "NotFoundError", "Not found"))
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.get_admin_information()
            assert exc_info.value.status_code == 404


class TestAsyncAdminInformation:
    """Async client URL routing and get_admin_information()."""

    @pytest.mark.respx
    async def test_get_admin_information_still_prefixes_api(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.get(ADMIN_API_PREFIXED).mock(return_value=Response(200, json={"ok": True}))

        async with AsyncClient(strapi_config) as client:
            response = await client.get("admin/information")
            assert response == {"ok": True}

    @pytest.mark.respx
    async def test_request_api_prefix_false_hits_origin(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        payload = {"data": {"strapiVersion": "5.0.0"}}
        respx_mock.get(ADMIN_ORIGIN).mock(return_value=Response(200, json=payload))

        async with AsyncClient(strapi_config) as client:
            response = await client.request("GET", "admin/information", api_prefix=False)
            assert response == payload

    @pytest.mark.respx
    async def test_get_admin_information_hits_origin(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        payload = {"strapiVersion": "5.11.0"}
        respx_mock.get(ADMIN_ORIGIN).mock(return_value=Response(200, json=payload))

        async with AsyncClient(strapi_config) as client:
            info = await client.get_admin_information()
            assert isinstance(info, AdminInformation)
            assert info.strapi_version == "5.11.0"
            assert info.raw == payload

    @pytest.mark.respx
    async def test_get_admin_information_nested_version(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        payload = {"data": {"strapiVersion": "4.25.1"}}
        respx_mock.get(ADMIN_ORIGIN).mock(return_value=Response(200, json=payload))

        async with AsyncClient(strapi_config) as client:
            info = await client.get_admin_information()
            assert info.strapi_version == "4.25.1"

    @pytest.mark.respx
    async def test_get_admin_information_missing_version(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.get(ADMIN_ORIGIN).mock(return_value=Response(200, json={}))

        async with AsyncClient(strapi_config) as client:
            info = await client.get_admin_information()
            assert info.strapi_version is None
            assert info.raw == {}

    @pytest.mark.respx
    async def test_get_admin_information_401(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.get(ADMIN_ORIGIN).mock(
            return_value=Response(
                401, json=_admin_error_payload(401, "UnauthorizedError", "Invalid token")
            )
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(AuthenticationError) as exc_info:
                await client.get_admin_information()
            assert exc_info.value.status_code == 401

    @pytest.mark.respx
    async def test_get_admin_information_403(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.get(ADMIN_ORIGIN).mock(
            return_value=Response(
                403, json=_admin_error_payload(403, "ForbiddenError", "Forbidden")
            )
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(AuthorizationError) as exc_info:
                await client.get_admin_information()
            assert exc_info.value.status_code == 403

    @pytest.mark.respx
    async def test_get_admin_information_404(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        respx_mock.get(ADMIN_ORIGIN).mock(
            return_value=Response(404, json=_admin_error_payload(404, "NotFoundError", "Not found"))
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError) as exc_info:
                await client.get_admin_information()
            assert exc_info.value.status_code == 404
