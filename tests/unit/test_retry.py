"""Tests for retry functionality."""

import httpx
import pytest
import respx

from strapi_kit import AsyncClient, RetryConfig, StrapiConfig, SyncClient
from strapi_kit.exceptions import (
    AuthenticationError,
    NotFoundError,
    ServerError,
    ValidationError,
)
from strapi_kit.exceptions import (
    ConnectionError as StrapiConnectionError,
)


@pytest.fixture
def retry_config() -> RetryConfig:
    """Create retry config with fast retries for testing."""
    return RetryConfig(
        max_attempts=3,
        initial_wait=0.1,  # Fast retries for tests (minimum allowed)
        max_wait=1.0,  # Minimum allowed value
        exponential_base=2.0,
        retry_on_status={500, 502, 503, 504},
    )


@pytest.fixture
def strapi_config_with_retry(retry_config: RetryConfig) -> StrapiConfig:
    """Create Strapi config with retry enabled."""
    return StrapiConfig(
        base_url="http://localhost:1337",
        api_token="test-token-for-retry-tests",  # noqa: S106
        retry=retry_config,
    )


# Sync Client Retry Tests


@respx.mock
def test_retry_on_server_error_500(strapi_config_with_retry: StrapiConfig) -> None:
    """Test retry on HTTP 500 server error."""
    # First request fails with 500, second succeeds
    route = respx.get("http://localhost:1337/api/articles")
    route.side_effect = [
        httpx.Response(500, json={"error": {"message": "Internal Server Error"}}),
        httpx.Response(200, json={"data": [{"id": 1, "documentId": "abc"}]}),
    ]

    with SyncClient(strapi_config_with_retry) as client:
        # Should succeed after retry
        response = client.get("articles")
        assert response["data"] == [{"id": 1, "documentId": "abc"}]

    # Verify it was called twice (initial + 1 retry)
    assert route.call_count == 2


@respx.mock
def test_retry_on_server_error_503(strapi_config_with_retry: StrapiConfig) -> None:
    """Test retry on HTTP 503 service unavailable."""
    route = respx.get("http://localhost:1337/api/articles")
    route.side_effect = [
        httpx.Response(503, json={"error": {"message": "Service Unavailable"}}),
        httpx.Response(503, json={"error": {"message": "Service Unavailable"}}),
        httpx.Response(200, json={"data": []}),
    ]

    with SyncClient(strapi_config_with_retry) as client:
        response = client.get("articles")
        assert response["data"] == []

    # Should retry twice and succeed on third attempt
    assert route.call_count == 3


@respx.mock
def test_retry_exhausted_raises_error(strapi_config_with_retry: StrapiConfig) -> None:
    """Test that retries are exhausted after max_attempts."""
    route = respx.get("http://localhost:1337/api/articles")
    # Always fail with 500
    route.mock(return_value=httpx.Response(500, json={"error": {"message": "Error"}}))

    with SyncClient(strapi_config_with_retry) as client:
        with pytest.raises(ServerError):
            client.get("articles")

    # Should try 3 times (max_attempts=3)
    assert route.call_count == 3


@respx.mock
def test_no_retry_on_client_errors(strapi_config_with_retry: StrapiConfig) -> None:
    """Test that client errors (4xx) are NOT retried."""
    # 400 - Validation error
    route_400 = respx.get("http://localhost:1337/api/articles")
    route_400.mock(return_value=httpx.Response(400, json={"error": {"message": "Bad Request"}}))

    with SyncClient(strapi_config_with_retry) as client:
        with pytest.raises(ValidationError):
            client.get("articles")

    # Should only try once (no retry on 400)
    assert route_400.call_count == 1


@respx.mock
def test_no_retry_on_401(strapi_config_with_retry: StrapiConfig) -> None:
    """Test that 401 errors are NOT retried."""
    route = respx.get("http://localhost:1337/api/articles")
    route.mock(return_value=httpx.Response(401, json={"error": {"message": "Unauthorized"}}))

    with SyncClient(strapi_config_with_retry) as client:
        with pytest.raises(AuthenticationError):
            client.get("articles")

    # No retry on auth errors
    assert route.call_count == 1


@respx.mock
def test_no_retry_on_404(strapi_config_with_retry: StrapiConfig) -> None:
    """Test that 404 errors are NOT retried."""
    route = respx.get("http://localhost:1337/api/articles")
    route.mock(return_value=httpx.Response(404, json={"error": {"message": "Not Found"}}))

    with SyncClient(strapi_config_with_retry) as client:
        with pytest.raises(NotFoundError):
            client.get("articles")

    assert route.call_count == 1


@respx.mock
def test_retry_on_rate_limit_with_retry_after(strapi_config_with_retry: StrapiConfig) -> None:
    """Test retry on 429 with Retry-After header."""
    route = respx.get("http://localhost:1337/api/articles")
    route.side_effect = [
        httpx.Response(
            429,
            headers={"Retry-After": "1"},
            json={"error": {"message": "Rate limit exceeded"}},
        ),
        httpx.Response(200, json={"data": []}),
    ]

    with SyncClient(strapi_config_with_retry) as client:
        response = client.get("articles")
        assert response["data"] == []

    # Should retry after rate limit
    assert route.call_count == 2


@respx.mock
def test_retry_on_connection_error(strapi_config_with_retry: StrapiConfig) -> None:
    """Test retry on connection failures."""
    route = respx.get("http://localhost:1337/api/articles")
    route.side_effect = [
        httpx.ConnectError("Connection refused"),
        httpx.Response(200, json={"data": []}),
    ]

    with SyncClient(strapi_config_with_retry) as client:
        response = client.get("articles")
        assert response["data"] == []

    assert route.call_count == 2


@respx.mock
def test_retry_connection_error_exhausted(strapi_config_with_retry: StrapiConfig) -> None:
    """Test connection error retries exhausted."""
    route = respx.get("http://localhost:1337/api/articles")
    # Always fail with connection error
    route.side_effect = httpx.ConnectError("Connection refused")

    with SyncClient(strapi_config_with_retry) as client:
        with pytest.raises(StrapiConnectionError):
            client.get("articles")

    # Should retry max_attempts times
    assert route.call_count == 3


@respx.mock
def test_custom_retry_on_status(strapi_config_with_retry: StrapiConfig) -> None:
    """Test custom retry_on_status configuration."""
    # Configure to retry on 502 and 503 only
    strapi_config_with_retry.retry.retry_on_status = {502, 503}

    route_502 = respx.get("http://localhost:1337/api/articles")
    route_502.side_effect = [
        httpx.Response(502, json={"error": {"message": "Bad Gateway"}}),
        httpx.Response(200, json={"data": []}),
    ]

    with SyncClient(strapi_config_with_retry) as client:
        response = client.get("articles")
        assert response["data"] == []

    # Should retry 502
    assert route_502.call_count == 2


@respx.mock
def test_no_retry_on_excluded_status(strapi_config_with_retry: StrapiConfig) -> None:
    """Test that status codes NOT in retry_on_status are not retried."""
    # Configure to NOT retry 500
    strapi_config_with_retry.retry.retry_on_status = {502, 503}

    route = respx.get("http://localhost:1337/api/articles")
    route.mock(return_value=httpx.Response(500, json={"error": {"message": "Error"}}))

    with SyncClient(strapi_config_with_retry) as client:
        with pytest.raises(ServerError):
            client.get("articles")

    # Should NOT retry 500 (not in retry_on_status)
    assert route.call_count == 1


# Async Client Retry Tests


@pytest.mark.asyncio
@respx.mock
async def test_async_retry_on_server_error(strapi_config_with_retry: StrapiConfig) -> None:
    """Test async retry on server errors."""
    route = respx.get("http://localhost:1337/api/articles")
    route.side_effect = [
        httpx.Response(500, json={"error": {"message": "Internal Server Error"}}),
        httpx.Response(200, json={"data": [{"id": 1, "documentId": "abc"}]}),
    ]

    async with AsyncClient(strapi_config_with_retry) as client:
        response = await client.get("articles")
        assert response["data"] == [{"id": 1, "documentId": "abc"}]

    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_async_retry_exhausted(strapi_config_with_retry: StrapiConfig) -> None:
    """Test async retry exhaustion."""
    route = respx.get("http://localhost:1337/api/articles")
    route.mock(return_value=httpx.Response(503, json={"error": {"message": "Unavailable"}}))

    async with AsyncClient(strapi_config_with_retry) as client:
        with pytest.raises(ServerError):
            await client.get("articles")

    # Should try max_attempts times
    assert route.call_count == 3


@pytest.mark.asyncio
@respx.mock
async def test_async_no_retry_on_404(strapi_config_with_retry: StrapiConfig) -> None:
    """Test async does not retry 404."""
    route = respx.get("http://localhost:1337/api/articles/999")
    route.mock(return_value=httpx.Response(404, json={"error": {"message": "Not Found"}}))

    async with AsyncClient(strapi_config_with_retry) as client:
        with pytest.raises(NotFoundError):
            await client.get("articles/999")

    # No retry on 404
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_async_retry_on_rate_limit(strapi_config_with_retry: StrapiConfig) -> None:
    """Test async retry on rate limit."""
    route = respx.get("http://localhost:1337/api/articles")
    route.side_effect = [
        httpx.Response(
            429,
            headers={"Retry-After": "1"},
            json={"error": {"message": "Rate limit"}},
        ),
        httpx.Response(200, json={"data": []}),
    ]

    async with AsyncClient(strapi_config_with_retry) as client:
        response = await client.get("articles")
        assert response["data"] == []

    assert route.call_count == 2


# Configuration Tests


def test_retry_config_defaults() -> None:
    """Test default retry configuration values."""
    config = RetryConfig()

    assert config.max_attempts == 3
    assert config.initial_wait == 1.0
    assert config.max_wait == 60.0
    assert config.exponential_base == 2.0
    assert config.retry_on_status == {500, 502, 503, 504}


def test_retry_config_validation() -> None:
    """Test retry config validation."""
    # Valid config
    config = RetryConfig(max_attempts=5, initial_wait=0.5)
    assert config.max_attempts == 5

    # Invalid max_attempts (too high)
    with pytest.raises(ValueError):
        RetryConfig(max_attempts=11)

    # Invalid max_attempts (too low)
    with pytest.raises(ValueError):
        RetryConfig(max_attempts=0)


@respx.mock
def test_retry_disabled_with_max_attempts_1(strapi_config_with_retry: StrapiConfig) -> None:
    """Test that max_attempts=1 effectively disables retry."""
    strapi_config_with_retry.retry.max_attempts = 1

    route = respx.get("http://localhost:1337/api/articles")
    route.mock(return_value=httpx.Response(500, json={"error": {"message": "Error"}}))

    with SyncClient(strapi_config_with_retry) as client:
        with pytest.raises(ServerError):
            client.get("articles")

    # Should only try once (no retries)
    assert route.call_count == 1
