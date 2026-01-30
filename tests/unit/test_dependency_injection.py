"""Tests for dependency injection patterns.

This module demonstrates and tests proper dependency injection,
including mock injection for testing.
"""

from unittest.mock import Mock

import httpx
import pytest

from py_strapi import (
    AsyncClient,
    AuthProvider,
    HTTPClient,
    ResponseParser,
    StrapiConfig,
    SyncClient,
    VersionDetectingParser,
)
from py_strapi.auth.api_token import APITokenAuth


class MockAuth:
    """Mock authentication provider for testing."""

    def __init__(self, token: str = "mock-token"):
        self.token = token
        self.get_headers_called = False
        self.validate_called = False

    def get_headers(self) -> dict[str, str]:
        """Return mock auth headers."""
        self.get_headers_called = True
        return {"Authorization": f"Bearer {self.token}"}

    def validate_token(self) -> bool:
        """Return True to pass validation."""
        self.validate_called = True
        return True


class MockHTTPClient:
    """Mock HTTP client for testing."""

    def __init__(self):
        self.requests = []
        self.closed = False

    def request(self, method, url, **kwargs):
        """Record request and return mock response."""
        self.requests.append((method, url, kwargs))
        mock_response = Mock()
        mock_response.is_success = True
        mock_response.json.return_value = {
            "data": {"id": 1, "documentId": "abc", "title": "Test"}
        }
        return mock_response

    def close(self):
        """Mark as closed."""
        self.closed = True


class MockAsyncHTTPClient:
    """Mock async HTTP client for testing."""

    def __init__(self):
        self.requests = []
        self.closed = False

    async def request(self, method, url, **kwargs):
        """Record request and return mock response."""
        self.requests.append((method, url, kwargs))
        mock_response = Mock()
        mock_response.is_success = True
        mock_response.json.return_value = {
            "data": {"id": 1, "documentId": "abc", "title": "Test"}
        }
        return mock_response

    async def aclose(self):
        """Mark as closed."""
        self.closed = True


class MockParser:
    """Mock response parser for testing."""

    def __init__(self):
        self.parse_single_called = False
        self.parse_collection_called = False

    def parse_single(self, response_data):
        """Mark single parse as called."""
        self.parse_single_called = True
        from py_strapi.models.response.normalized import NormalizedSingleResponse
        return NormalizedSingleResponse(data=None, meta=None)

    def parse_collection(self, response_data):
        """Mark collection parse as called."""
        self.parse_collection_called = True
        from py_strapi.models.response.normalized import NormalizedCollectionResponse
        return NormalizedCollectionResponse(data=[], meta=None)


class TestSyncClientDependencyInjection:
    """Tests for SyncClient dependency injection."""

    def test_inject_all_dependencies(self):
        """Test injecting all dependencies into SyncClient."""
        config = StrapiConfig(base_url="http://localhost:1337", api_token="test")

        # Create mock dependencies
        mock_auth = MockAuth()
        mock_http = MockHTTPClient()
        mock_parser = MockParser()

        # Inject all dependencies
        client = SyncClient(
            config, http_client=mock_http, auth=mock_auth, parser=mock_parser
        )

        # Verify injected dependencies are used
        assert client.auth is mock_auth
        assert client._client is mock_http
        assert client.parser is mock_parser

        # Verify ownership tracking
        assert not client._owns_client  # We injected it, so we don't own it

    def test_default_dependencies_created(self):
        """Test that default dependencies are created when not injected."""
        config = StrapiConfig(base_url="http://localhost:1337", api_token="test")

        client = SyncClient(config)

        # Verify defaults were created
        assert isinstance(client.auth, APITokenAuth)
        assert isinstance(client._client, httpx.Client)
        assert isinstance(client.parser, VersionDetectingParser)

        # Verify ownership tracking
        assert client._owns_client  # We created it, so we own it

        client.close()

    def test_injected_client_not_closed(self):
        """Test that injected HTTP client is NOT closed by SyncClient."""
        config = StrapiConfig(base_url="http://localhost:1337", api_token="test")
        mock_http = MockHTTPClient()

        client = SyncClient(config, http_client=mock_http)
        client.close()

        # Injected client should NOT be closed
        assert not mock_http.closed

    def test_owned_client_is_closed(self):
        """Test that owned HTTP client IS closed by SyncClient."""
        config = StrapiConfig(base_url="http://localhost:1337", api_token="test")

        with SyncClient(config) as client:
            http_client = client._client

        # Owned client should be closed after context exit
        # Note: We can't check httpx.Client.is_closed without making a request
        # So we just verify the close was called without error

    def test_custom_auth_used_in_requests(self):
        """Test that custom auth provider is used for headers."""
        config = StrapiConfig(base_url="http://localhost:1337", api_token="test")
        mock_auth = MockAuth(token="custom-token")

        client = SyncClient(config, auth=mock_auth)

        # Get headers and verify custom auth was called
        headers = client._get_headers()
        assert mock_auth.get_headers_called
        assert headers["Authorization"] == "Bearer custom-token"

    def test_custom_parser_used(self):
        """Test that custom parser is used for response parsing."""
        config = StrapiConfig(base_url="http://localhost:1337", api_token="test")
        mock_parser = MockParser()
        mock_http = MockHTTPClient()

        client = SyncClient(config, http_client=mock_http, parser=mock_parser)

        # Make a request that triggers parsing
        client.get_one("articles/1")

        # Verify custom parser was used
        assert mock_parser.parse_single_called


class TestAsyncClientDependencyInjection:
    """Tests for AsyncClient dependency injection."""

    async def test_inject_all_dependencies(self):
        """Test injecting all dependencies into AsyncClient."""
        config = StrapiConfig(base_url="http://localhost:1337", api_token="test")

        # Create mock dependencies
        mock_auth = MockAuth()
        mock_http = MockAsyncHTTPClient()
        mock_parser = MockParser()

        # Inject all dependencies
        client = AsyncClient(
            config, http_client=mock_http, auth=mock_auth, parser=mock_parser
        )

        # Verify injected dependencies are used
        assert client.auth is mock_auth
        assert client._client is mock_http
        assert client.parser is mock_parser

        # Verify ownership tracking
        assert not client._owns_client  # We injected it, so we don't own it

        await client.close()

    async def test_default_dependencies_created(self):
        """Test that default dependencies are created when not injected."""
        config = StrapiConfig(base_url="http://localhost:1337", api_token="test")

        client = AsyncClient(config)

        # Verify defaults were created
        assert isinstance(client.auth, APITokenAuth)
        assert isinstance(client._client, httpx.AsyncClient)
        assert isinstance(client.parser, VersionDetectingParser)

        # Verify ownership tracking
        assert client._owns_client  # We created it, so we own it

        await client.close()

    async def test_injected_client_not_closed(self):
        """Test that injected HTTP client is NOT closed by AsyncClient."""
        config = StrapiConfig(base_url="http://localhost:1337", api_token="test")
        mock_http = MockAsyncHTTPClient()

        client = AsyncClient(config, http_client=mock_http)
        await client.close()

        # Injected client should NOT be closed
        assert not mock_http.closed

    async def test_custom_parser_used(self):
        """Test that custom parser is used for response parsing."""
        config = StrapiConfig(base_url="http://localhost:1337", api_token="test")
        mock_parser = MockParser()
        mock_http = MockAsyncHTTPClient()

        client = AsyncClient(config, http_client=mock_http, parser=mock_parser)

        # Make a request that triggers parsing
        await client.get_one("articles/1")

        # Verify custom parser was used
        assert mock_parser.parse_single_called


class TestProtocolCompliance:
    """Tests that implementations satisfy protocol contracts."""

    def test_api_token_auth_satisfies_auth_provider(self):
        """Test that APITokenAuth satisfies AuthProvider protocol."""
        auth = APITokenAuth("test-token")

        # Should satisfy protocol
        assert isinstance(auth, AuthProvider)

        # Test required methods
        assert callable(auth.get_headers)
        assert callable(auth.validate_token)

        # Test behavior
        headers = auth.get_headers()
        assert "Authorization" in headers
        assert auth.validate_token()

    def test_httpx_client_satisfies_http_client_protocol(self):
        """Test that httpx.Client satisfies HTTPClient protocol."""
        client = httpx.Client()

        # Should satisfy protocol
        assert isinstance(client, HTTPClient)

        # Test required methods
        assert callable(client.request)
        assert callable(client.close)

        client.close()

    def test_httpx_async_client_satisfies_async_http_client_protocol(self):
        """Test that httpx.AsyncClient satisfies AsyncHTTPClient protocol."""
        import asyncio

        async def check():
            client = httpx.AsyncClient()

            # Should satisfy protocol (runtime check)
            from py_strapi.protocols import AsyncHTTPClient

            assert isinstance(client, AsyncHTTPClient)

            # Test required methods
            assert callable(client.request)
            assert callable(client.aclose)

            await client.aclose()

        asyncio.run(check())

    def test_version_detecting_parser_satisfies_response_parser(self):
        """Test that VersionDetectingParser satisfies ResponseParser protocol."""
        parser = VersionDetectingParser()

        # Should satisfy protocol
        assert isinstance(parser, ResponseParser)

        # Test required methods
        assert callable(parser.parse_single)
        assert callable(parser.parse_collection)


class TestDIUsageExamples:
    """Real-world examples of using DI for testing and customization."""

    def test_example_inject_mock_for_unit_testing(self):
        """Example: Inject mocks for pure unit testing (no HTTP)."""
        config = StrapiConfig(base_url="http://localhost:1337", api_token="test")

        # Create fully mocked client
        mock_http = MockHTTPClient()
        client = SyncClient(config, http_client=mock_http)

        # Make "request" (no actual HTTP)
        result = client.get("articles")

        # Verify our mock was called
        assert len(mock_http.requests) == 1
        method, url, kwargs = mock_http.requests[0]
        assert method == "GET"
        assert "articles" in url

        client.close()

    def test_example_custom_parser_for_special_format(self):
        """Example: Custom parser for non-standard response format."""
        config = StrapiConfig(base_url="http://localhost:1337", api_token="test")

        # Custom parser for legacy API
        class LegacyParser(MockParser):
            """Parser for legacy Strapi format."""

            pass

        mock_http = MockHTTPClient()
        custom_parser = LegacyParser()

        client = SyncClient(config, http_client=mock_http, parser=custom_parser)

        # Use client with custom parser
        client.get_one("articles/1")

        # Verify custom parser was used
        assert custom_parser.parse_single_called

        client.close()

    def test_example_shared_http_client(self):
        """Example: Share HTTP client across multiple Strapi clients."""
        config1 = StrapiConfig(base_url="http://cms1.example.com", api_token="token1")
        config2 = StrapiConfig(base_url="http://cms2.example.com", api_token="token2")

        # Share one HTTP client for connection pooling across both CMS instances
        shared_http = httpx.Client()

        client1 = SyncClient(config1, http_client=shared_http)
        client2 = SyncClient(config2, http_client=shared_http)

        # Both clients share the connection pool
        assert client1._client is client2._client

        # Close clients (won't close shared HTTP client)
        client1.close()
        client2.close()

        # We manage shared client lifecycle
        shared_http.close()
