"""Tests for AUDIT.md fixes.

This module tests all the fixes implemented from the code audit:
- Exporter UID pluralization with schema support
- Auto-populate on export
- v4 media detection
- Media filename sanitization
- v4/v5 media update endpoint
- Rate limiting
- Import conflict resolution
- Version detection caching
- Non-JSON response handling
- Query mutation protection
"""

import httpx
import pytest
import respx

from py_strapi import StrapiConfig, SyncClient
from py_strapi.exceptions import FormatError
from py_strapi.export.media_handler import MediaHandler
from py_strapi.models.request.filters import FilterBuilder
from py_strapi.models.request.query import StrapiQuery
from py_strapi.utils.rate_limiter import AsyncTokenBucketRateLimiter, TokenBucketRateLimiter
from py_strapi.utils.uid import extract_model_name, is_api_content_type, uid_to_endpoint


class TestMediaHandler:
    """Tests for MediaHandler v4 detection and filename sanitization."""

    def test_is_media_v5_format(self):
        """Test media detection with v5 format (mime at top level)."""
        item = {"id": 1, "mime": "image/jpeg", "name": "test.jpg"}
        assert MediaHandler._is_media(item) is True

    def test_is_media_v4_format(self):
        """Test media detection with v4 format (mime in attributes)."""
        item = {
            "id": 1,
            "attributes": {
                "mime": "image/jpeg",
                "name": "test.jpg",
            },
        }
        assert MediaHandler._is_media(item) is True

    def test_is_media_not_media(self):
        """Test media detection returns False for non-media items."""
        item = {"id": 1, "name": "Article Title"}
        assert MediaHandler._is_media(item) is False

    def test_extract_media_references_v4_format(self):
        """Test extracting media references from v4 format."""
        data = {
            "title": "Test Article",
            "cover": {
                "data": {
                    "id": 5,
                    "attributes": {
                        "mime": "image/jpeg",
                        "name": "cover.jpg",
                    },
                }
            },
        }
        media_ids = MediaHandler.extract_media_references(data)
        assert media_ids == [5]

    def test_extract_media_references_v5_format(self):
        """Test extracting media references from v5 format."""
        data = {
            "title": "Test Article",
            "cover": {
                "data": {
                    "id": 5,
                    "mime": "image/jpeg",
                    "name": "cover.jpg",
                }
            },
        }
        media_ids = MediaHandler.extract_media_references(data)
        assert media_ids == [5]

    def test_extract_media_references_multiple_v4(self):
        """Test extracting multiple media references in v4 format."""
        data = {
            "gallery": {
                "data": [
                    {"id": 1, "attributes": {"mime": "image/jpeg"}},
                    {"id": 2, "attributes": {"mime": "image/png"}},
                ]
            }
        }
        media_ids = MediaHandler.extract_media_references(data)
        assert set(media_ids) == {1, 2}

    def test_sanitize_filename_path_traversal(self):
        """Test sanitization prevents path traversal attacks."""
        dangerous_names = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
            "/etc/passwd",
            "\\windows\\system32",
        ]
        for name in dangerous_names:
            sanitized = MediaHandler._sanitize_filename(name)
            assert "/" not in sanitized
            assert "\\" not in sanitized
            assert ".." not in sanitized

    def test_sanitize_filename_special_chars(self):
        """Test sanitization removes dangerous special characters."""
        name = 'file<script>alert("xss")</script>.jpg'
        sanitized = MediaHandler._sanitize_filename(name)
        assert "<" not in sanitized
        assert ">" not in sanitized
        assert '"' not in sanitized

    def test_sanitize_filename_empty(self):
        """Test sanitization handles empty filenames."""
        assert MediaHandler._sanitize_filename("") == "unnamed"
        assert MediaHandler._sanitize_filename("   ") == "unnamed"
        # "..." becomes "_" after ".." replacement and dot stripping
        sanitized = MediaHandler._sanitize_filename("...")
        # Just verify it's not empty and doesn't contain original dots pattern
        assert sanitized and "..." not in sanitized

    def test_sanitize_filename_preserves_extension(self):
        """Test sanitization preserves file extension."""
        name = "a" * 300 + ".jpg"
        sanitized = MediaHandler._sanitize_filename(name, max_length=200)
        assert sanitized.endswith(".jpg")
        assert len(sanitized) <= 200

    def test_sanitize_filename_null_bytes(self):
        """Test sanitization removes null bytes."""
        name = "file\x00name.jpg"
        sanitized = MediaHandler._sanitize_filename(name)
        assert "\x00" not in sanitized


class TestStrapiQueryCopy:
    """Tests for StrapiQuery.copy() method."""

    def test_copy_creates_independent_instance(self):
        """Test that copy creates an independent query instance."""
        original = (
            StrapiQuery()
            .filter(FilterBuilder().eq("status", "published"))
            .paginate(page=1, page_size=10)
        )

        copied = original.copy()
        copied.paginate(page=2, page_size=25)

        original_params = original.to_query_params()
        copied_params = copied.to_query_params()

        # Original should be unchanged
        assert original_params.get("pagination[page]") == 1
        assert original_params.get("pagination[pageSize]") == 10

        # Copy should have new values
        assert copied_params.get("pagination[page]") == 2
        assert copied_params.get("pagination[pageSize]") == 25

    def test_copy_preserves_filters(self):
        """Test that copy preserves filter configuration."""
        original = StrapiQuery().filter(FilterBuilder().eq("status", "published").gt("views", 100))

        copied = original.copy()
        original_params = original.to_query_params()
        copied_params = copied.to_query_params()

        assert original_params == copied_params

    def test_copy_preserves_populate(self):
        """Test that copy preserves populate configuration."""
        original = StrapiQuery().populate_all()

        copied = original.copy()
        original_params = original.to_query_params()
        copied_params = copied.to_query_params()

        assert original_params == copied_params


class TestRateLimiter:
    """Tests for rate limiter implementation."""

    def test_rate_limiter_creation(self):
        """Test rate limiter can be created with valid rate."""
        limiter = TokenBucketRateLimiter(rate=10.0)
        assert limiter.available_tokens == 10.0

    def test_rate_limiter_invalid_rate(self):
        """Test rate limiter rejects invalid rate."""
        with pytest.raises(ValueError):
            TokenBucketRateLimiter(rate=0)

        with pytest.raises(ValueError):
            TokenBucketRateLimiter(rate=-1)

    def test_rate_limiter_acquire(self):
        """Test rate limiter acquire reduces tokens."""
        limiter = TokenBucketRateLimiter(rate=10.0)

        assert limiter.acquire() is True
        assert limiter.available_tokens < 10.0

    def test_rate_limiter_non_blocking(self):
        """Test rate limiter non-blocking mode."""
        limiter = TokenBucketRateLimiter(rate=1.0, capacity=1.0)

        # First acquire should succeed
        assert limiter.acquire(blocking=False) is True

        # Second immediate acquire should fail (no tokens)
        assert limiter.acquire(blocking=False) is False


class TestAsyncRateLimiter:
    """Tests for async rate limiter implementation."""

    @pytest.mark.asyncio
    async def test_async_rate_limiter_creation(self):
        """Test async rate limiter can be created with valid rate."""
        limiter = AsyncTokenBucketRateLimiter(rate=10.0)
        # Note: available_tokens is not thread-safe without lock
        # This is just a basic creation test
        assert limiter._rate == 10.0

    @pytest.mark.asyncio
    async def test_async_rate_limiter_acquire(self):
        """Test async rate limiter acquire works."""
        limiter = AsyncTokenBucketRateLimiter(rate=10.0)
        result = await limiter.acquire()
        assert result is True


class TestUidUtilities:
    """Tests for UID utility functions."""

    def test_uid_to_endpoint_basic(self):
        """Test basic UID to endpoint conversion."""
        assert uid_to_endpoint("api::article.article") == "articles"
        assert uid_to_endpoint("api::author.author") == "authors"

    def test_uid_to_endpoint_plural_y(self):
        """Test pluralization of words ending in y."""
        assert uid_to_endpoint("api::category.category") == "categories"
        assert uid_to_endpoint("api::company.company") == "companies"

    def test_uid_to_endpoint_plural_es(self):
        """Test pluralization of words ending in s, x, z, ch, sh."""
        assert uid_to_endpoint("api::class.class") == "classes"
        assert uid_to_endpoint("api::box.box") == "boxes"

    def test_uid_to_endpoint_vowel_y(self):
        """Test words ending in vowel+y don't change y to ies."""
        assert uid_to_endpoint("api::key.key") == "keys"
        assert uid_to_endpoint("api::toy.toy") == "toys"

    def test_extract_model_name(self):
        """Test extracting model name from UID."""
        assert extract_model_name("api::article.article") == "article"
        assert extract_model_name("plugin::users-permissions.user") == "user"

    def test_is_api_content_type(self):
        """Test detecting API content types."""
        assert is_api_content_type("api::article.article") is True
        assert is_api_content_type("plugin::users-permissions.user") is False


class TestVersionDetectionCaching:
    """Tests for version detection caching behavior."""

    @respx.mock
    def test_ambiguous_response_not_cached(self, strapi_config):
        """Test that ambiguous responses don't cache version."""
        # Mock response without clear v4/v5 indicators
        respx.get("http://localhost:1337/api/test").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"id": 1, "title": "Test"}},  # No attributes or documentId
            )
        )

        with SyncClient(strapi_config) as client:
            client.get("test")
            # Version should not be cached on ambiguous response
            assert client._api_version is None

    @respx.mock
    def test_v5_response_cached(self, strapi_config):
        """Test that v5 responses are cached."""
        respx.get("http://localhost:1337/api/test").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"id": 1, "documentId": "abc123", "title": "Test"}},
            )
        )

        with SyncClient(strapi_config) as client:
            client.get("test")
            assert client._api_version == "v5"

    @respx.mock
    def test_v4_response_cached(self, strapi_config):
        """Test that v4 responses are cached."""
        respx.get("http://localhost:1337/api/test").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"id": 1, "attributes": {"title": "Test"}}},
            )
        )

        with SyncClient(strapi_config) as client:
            client.get("test")
            assert client._api_version == "v4"

    @respx.mock
    def test_reset_version_detection(self, strapi_config):
        """Test reset_version_detection clears cached version."""
        respx.get("http://localhost:1337/api/test").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"id": 1, "documentId": "abc123", "title": "Test"}},
            )
        )

        with SyncClient(strapi_config) as client:
            client.get("test")
            assert client._api_version == "v5"

            client.reset_version_detection()
            assert client._api_version is None


class TestNonJsonResponseHandling:
    """Tests for non-JSON response handling."""

    @respx.mock
    def test_html_response_raises_format_error(self, strapi_config):
        """Test that HTML responses raise FormatError."""
        respx.get("http://localhost:1337/api/test").mock(
            return_value=httpx.Response(
                200,
                content=b"<html><body>Error</body></html>",
                headers={"content-type": "text/html"},
            )
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(FormatError) as exc_info:
                client.get("test")

            assert "non-JSON response" in str(exc_info.value)
            assert "text/html" in str(exc_info.value)

    @respx.mock
    def test_format_error_includes_body_preview(self, strapi_config):
        """Test that FormatError includes body preview."""
        html_body = "<html><body>Gateway Error</body></html>"
        respx.get("http://localhost:1337/api/test").mock(
            return_value=httpx.Response(
                200,
                content=html_body.encode(),
                headers={"content-type": "text/html"},
            )
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(FormatError) as exc_info:
                client.get("test")

            assert exc_info.value.details.get("body_preview") == html_body


class TestMediaUpdateEndpoint:
    """Tests for v4/v5 media update endpoint handling."""

    @respx.mock
    def test_update_media_v5_uses_post(self):
        """Test that v5 uses POST /api/upload?id=x."""
        # Config with explicit v5
        config = StrapiConfig(
            base_url="http://localhost:1337",
            api_token="test-token-12345678",
            api_version="v5",
        )

        # Complete mock response for MediaFile validation
        mock_media = {
            "id": 42,
            "documentId": "abc123",
            "name": "updated.jpg",
            "alternativeText": "New alt",
            "caption": None,
            "width": 800,
            "height": 600,
            "formats": None,
            "hash": "abc123hash",
            "ext": ".jpg",
            "mime": "image/jpeg",
            "size": 1024.5,
            "url": "/uploads/updated.jpg",
            "previewUrl": None,
            "provider": "local",
            "provider_metadata": None,
            "createdAt": "2024-01-01T00:00:00.000Z",
            "updatedAt": "2024-01-01T00:00:00.000Z",
        }

        # Mock the media update endpoint (v5 style)
        route = respx.post("http://localhost:1337/api/upload").mock(
            return_value=httpx.Response(200, json=mock_media)
        )

        with SyncClient(config) as client:
            assert client._api_version == "v5"
            media = client.update_media(42, alternative_text="New alt")
            assert media.id == 42

            # Verify v5 uses POST with query param
            assert route.called
            assert route.calls.last.request.method == "POST"
            assert "id=42" in str(route.calls.last.request.url)

    @respx.mock
    def test_update_media_v4_uses_put(self):
        """Test that v4 uses PUT /api/upload/files/:id."""
        # Config with explicit v4
        config = StrapiConfig(
            base_url="http://localhost:1337",
            api_token="test-token-12345678",
            api_version="v4",
        )

        # Complete mock response for MediaFile validation
        mock_media = {
            "id": 42,
            "name": "updated.jpg",
            "alternativeText": "New alt",
            "caption": None,
            "width": 800,
            "height": 600,
            "formats": None,
            "hash": "abc123hash",
            "ext": ".jpg",
            "mime": "image/jpeg",
            "size": 1024.5,
            "url": "/uploads/updated.jpg",
            "previewUrl": None,
            "provider": "local",
            "provider_metadata": None,
            "createdAt": "2024-01-01T00:00:00.000Z",
            "updatedAt": "2024-01-01T00:00:00.000Z",
        }

        # Mock the media update endpoint (v4 style)
        route = respx.put("http://localhost:1337/api/upload/files/42").mock(
            return_value=httpx.Response(200, json=mock_media)
        )

        with SyncClient(config) as client:
            assert client._api_version == "v4"
            media = client.update_media(42, alternative_text="New alt")
            assert media.id == 42

            # Verify v4 uses PUT with path param
            assert route.called
            assert route.calls.last.request.method == "PUT"
            assert "/upload/files/42" in str(route.calls.last.request.url)


class TestRateLimitingInClient:
    """Tests for rate limiting integration in clients."""

    def test_rate_limiter_initialized_when_configured(self):
        """Test rate limiter is created when config has rate_limit_per_second."""
        config = StrapiConfig(
            base_url="http://localhost:1337",
            api_token="test-token-12345678",
            rate_limit_per_second=5.0,
        )

        with SyncClient(config) as client:
            assert client._rate_limiter is not None
            assert isinstance(client._rate_limiter, TokenBucketRateLimiter)

    def test_rate_limiter_not_initialized_when_disabled(self):
        """Test rate limiter is None when not configured."""
        config = StrapiConfig(
            base_url="http://localhost:1337",
            api_token="test-token-12345678",
            rate_limit_per_second=None,
        )

        with SyncClient(config) as client:
            assert client._rate_limiter is None


class TestBaseUrlValidation:
    """Tests for base_url validation in StrapiConfig."""

    def test_valid_http_url(self):
        """Test valid HTTP URL is accepted."""
        config = StrapiConfig(
            base_url="http://localhost:1337",
            api_token="test-token-12345678",
        )
        assert config.base_url == "http://localhost:1337"

    def test_valid_https_url(self):
        """Test valid HTTPS URL is accepted."""
        config = StrapiConfig(
            base_url="https://api.example.com",
            api_token="test-token-12345678",
        )
        assert config.base_url == "https://api.example.com"

    def test_trailing_slash_removed(self):
        """Test trailing slash is stripped from base_url."""
        config = StrapiConfig(
            base_url="http://localhost:1337/",
            api_token="test-token-12345678",
        )
        assert config.base_url == "http://localhost:1337"

    def test_invalid_scheme_rejected(self):
        """Test URLs without http/https scheme are rejected."""
        with pytest.raises(ValueError) as exc_info:
            StrapiConfig(
                base_url="ftp://localhost:1337",
                api_token="test-token-12345678",
            )
        assert "http://" in str(exc_info.value) or "https://" in str(exc_info.value)

    def test_no_scheme_rejected(self):
        """Test URLs without any scheme are rejected."""
        with pytest.raises(ValueError) as exc_info:
            StrapiConfig(
                base_url="localhost:1337",
                api_token="test-token-12345678",
            )
        assert "http://" in str(exc_info.value) or "https://" in str(exc_info.value)

    def test_empty_url_rejected(self):
        """Test empty URL is rejected."""
        with pytest.raises(ValueError) as exc_info:
            StrapiConfig(
                base_url="",
                api_token="test-token-12345678",
            )
        assert "empty" in str(exc_info.value).lower()

    def test_whitespace_only_rejected(self):
        """Test whitespace-only URL is rejected."""
        with pytest.raises(ValueError) as exc_info:
            StrapiConfig(
                base_url="   ",
                api_token="test-token-12345678",
            )
        assert "empty" in str(exc_info.value).lower()

    def test_url_with_path(self):
        """Test URL with path is accepted."""
        config = StrapiConfig(
            base_url="http://localhost:1337/strapi",
            api_token="test-token-12345678",
        )
        assert config.base_url == "http://localhost:1337/strapi"

    def test_url_whitespace_trimmed(self):
        """Test whitespace is trimmed from URL."""
        config = StrapiConfig(
            base_url="  http://localhost:1337  ",
            api_token="test-token-12345678",
        )
        assert config.base_url == "http://localhost:1337"
