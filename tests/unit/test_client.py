"""Unit tests for HTTP clients."""

import pytest
import respx
from httpx import Response

from py_strapi import AsyncClient, StrapiConfig, SyncClient
from py_strapi.exceptions import (
    AuthenticationError,
    NotFoundError,
    ServerError,
    ValidationError,
)


class TestSyncClient:
    """Test cases for SyncClient."""

    def test_initialization(self, strapi_config: StrapiConfig) -> None:
        """Test client initialization."""
        client = SyncClient(strapi_config)
        assert client.base_url == "http://localhost:1337"
        assert client.config == strapi_config

    def test_context_manager(self, strapi_config: StrapiConfig) -> None:
        """Test client as context manager."""
        with SyncClient(strapi_config) as client:
            assert client is not None
        # Client should be closed after context

    @respx.mock
    def test_get_request_success(
        self, strapi_config: StrapiConfig, mock_v4_response: dict
    ) -> None:
        """Test successful GET request."""
        respx.get("http://localhost:1337/api/articles/1").mock(
            return_value=Response(200, json=mock_v4_response)
        )

        with SyncClient(strapi_config) as client:
            response = client.get("articles/1")
            assert response == mock_v4_response
            assert client.api_version == "v4"

    @respx.mock
    def test_post_request_success(
        self, strapi_config: StrapiConfig, mock_v4_response: dict
    ) -> None:
        """Test successful POST request."""
        respx.post("http://localhost:1337/api/articles").mock(
            return_value=Response(200, json=mock_v4_response)
        )

        with SyncClient(strapi_config) as client:
            data = {"data": {"title": "Test", "content": "Test content"}}
            response = client.post("articles", json=data)
            assert response == mock_v4_response

    @respx.mock
    def test_authentication_error(self, strapi_config: StrapiConfig) -> None:
        """Test authentication error handling."""
        error_response = {
            "error": {
                "status": 401,
                "name": "UnauthorizedError",
                "message": "Invalid token",
            }
        }
        respx.get("http://localhost:1337/api/articles").mock(
            return_value=Response(401, json=error_response)
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(AuthenticationError) as exc_info:
                client.get("articles")
            assert "Invalid token" in str(exc_info.value)

    @respx.mock
    def test_not_found_error(self, strapi_config: StrapiConfig) -> None:
        """Test not found error handling."""
        error_response = {
            "error": {
                "status": 404,
                "name": "NotFoundError",
                "message": "Not found",
            }
        }
        respx.get("http://localhost:1337/api/articles/999").mock(
            return_value=Response(404, json=error_response)
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError):
                client.get("articles/999")

    @respx.mock
    def test_validation_error(self, strapi_config: StrapiConfig) -> None:
        """Test validation error handling."""
        error_response = {
            "error": {
                "status": 400,
                "name": "ValidationError",
                "message": "Invalid data",
                "details": {"field": "title is required"},
            }
        }
        respx.post("http://localhost:1337/api/articles").mock(
            return_value=Response(400, json=error_response)
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(ValidationError):
                client.post("articles", json={})

    @respx.mock
    def test_server_error(self, strapi_config: StrapiConfig) -> None:
        """Test server error handling."""
        error_response = {
            "error": {
                "status": 500,
                "name": "InternalServerError",
                "message": "Server error",
            }
        }
        respx.get("http://localhost:1337/api/articles").mock(
            return_value=Response(500, json=error_response)
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(ServerError) as exc_info:
                client.get("articles")
            assert exc_info.value.status_code == 500

    @respx.mock
    def test_api_version_detection_v4(
        self, strapi_config: StrapiConfig, mock_v4_response: dict
    ) -> None:
        """Test automatic v4 API detection."""
        respx.get("http://localhost:1337/api/articles/1").mock(
            return_value=Response(200, json=mock_v4_response)
        )

        with SyncClient(strapi_config) as client:
            client.get("articles/1")
            assert client.api_version == "v4"

    @respx.mock
    def test_api_version_detection_v5(
        self, strapi_config: StrapiConfig, mock_v5_response: dict
    ) -> None:
        """Test automatic v5 API detection."""
        respx.get("http://localhost:1337/api/articles/1").mock(
            return_value=Response(200, json=mock_v5_response)
        )

        with SyncClient(strapi_config) as client:
            client.get("articles/1")
            assert client.api_version == "v5"


class TestAsyncClient:
    """Test cases for AsyncClient."""

    def test_initialization(self, strapi_config: StrapiConfig) -> None:
        """Test client initialization."""
        client = AsyncClient(strapi_config)
        assert client.base_url == "http://localhost:1337"
        assert client.config == strapi_config

    @pytest.mark.asyncio
    async def test_context_manager(self, strapi_config: StrapiConfig) -> None:
        """Test client as async context manager."""
        async with AsyncClient(strapi_config) as client:
            assert client is not None
        # Client should be closed after context

    @pytest.mark.asyncio
    @respx.mock
    async def test_get_request_success(
        self, strapi_config: StrapiConfig, mock_v4_response: dict
    ) -> None:
        """Test successful async GET request."""
        respx.get("http://localhost:1337/api/articles/1").mock(
            return_value=Response(200, json=mock_v4_response)
        )

        async with AsyncClient(strapi_config) as client:
            response = await client.get("articles/1")
            assert response == mock_v4_response
            assert client.api_version == "v4"

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_request_success(
        self, strapi_config: StrapiConfig, mock_v4_response: dict
    ) -> None:
        """Test successful async POST request."""
        respx.post("http://localhost:1337/api/articles").mock(
            return_value=Response(200, json=mock_v4_response)
        )

        async with AsyncClient(strapi_config) as client:
            data = {"data": {"title": "Test", "content": "Test content"}}
            response = await client.post("articles", json=data)
            assert response == mock_v4_response

    @pytest.mark.asyncio
    @respx.mock
    async def test_authentication_error(self, strapi_config: StrapiConfig) -> None:
        """Test authentication error handling."""
        error_response = {
            "error": {
                "status": 401,
                "name": "UnauthorizedError",
                "message": "Invalid token",
            }
        }
        respx.get("http://localhost:1337/api/articles").mock(
            return_value=Response(401, json=error_response)
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(AuthenticationError):
                await client.get("articles")
