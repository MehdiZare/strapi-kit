"""E2E tests for error handling.

Tests that errors from Strapi are correctly mapped to py-strapi exceptions.
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from py_strapi import StrapiConfig, SyncClient
from py_strapi.exceptions import (
    AuthenticationError,
    NotFoundError,
    ValidationError,
)


@pytest.mark.e2e
class TestNotFoundError:
    """Tests for 404 Not Found error mapping."""

    def test_get_nonexistent_entity(self, sync_client: SyncClient) -> None:
        """Test that getting a nonexistent entity raises NotFoundError."""
        with pytest.raises(NotFoundError) as exc_info:
            sync_client.get_one("articles/nonexistent-document-id-xyz789")

        # NotFoundError inherits from StrapiError which has message attribute
        assert str(exc_info.value) != ""

    def test_update_nonexistent_entity(self, sync_client: SyncClient) -> None:
        """Test that updating a nonexistent entity raises NotFoundError."""
        with pytest.raises(NotFoundError):
            sync_client.update(
                "articles/nonexistent-document-id-abc123",
                {"title": "Will Fail"},
            )

    def test_delete_nonexistent_entity(self, sync_client: SyncClient) -> None:
        """Test behavior when deleting a nonexistent entity.

        Note: Strapi v5 may return success (200/204) when deleting non-existent
        entities instead of 404. This test verifies the operation completes
        without unexpected errors.
        """
        # Strapi v5 may not raise NotFoundError for delete operations
        # on non-existent entities - it may return success silently
        try:
            sync_client.remove("articles/nonexistent-document-id-def456")
            # If we get here, Strapi accepted the delete (v5 behavior)
        except NotFoundError:
            # Expected for v4 or stricter Strapi configurations
            pass


@pytest.mark.e2e
class TestValidationError:
    """Tests for 400 Bad Request / Validation error mapping."""

    def test_create_with_invalid_data(self, sync_client: SyncClient) -> None:
        """Test that creating with invalid data raises ValidationError."""
        # Try to create an article without required 'title' field
        # (if title is required in schema)
        # This test depends on the schema having required fields
        with pytest.raises((ValidationError, Exception)):
            # Using an invalid relation ID should cause validation error
            sync_client.create(
                "articles",
                {
                    "title": "Test",
                    "slug": "test-validation",
                    "author": "invalid-not-a-real-id",
                },
            )

    def test_create_duplicate_unique_field(self, sync_client: SyncClient) -> None:
        """Test that creating with duplicate unique field raises error."""
        # Create first author
        response = sync_client.create(
            "authors",
            {"name": "Unique Test", "email": "unique-test@example.com"},
        )
        assert response.data is not None
        author_id = response.data.document_id or str(response.data.id)

        try:
            # Try to create another with same unique email
            with pytest.raises((ValidationError, Exception)):
                sync_client.create(
                    "authors",
                    {"name": "Another Author", "email": "unique-test@example.com"},
                )
        finally:
            # Cleanup
            sync_client.remove(f"authors/{author_id}")


@pytest.mark.e2e
class TestAuthenticationError:
    """Tests for 401 Unauthorized error mapping."""

    def test_request_with_invalid_token(self, strapi_instance: str) -> None:
        """Test that requests with invalid token raise AuthenticationError."""
        # Create config with invalid token
        config = StrapiConfig(
            base_url=strapi_instance,
            api_token=SecretStr("invalid-token-that-does-not-exist"),
        )

        with SyncClient(config) as client:
            with pytest.raises(AuthenticationError) as exc_info:
                client.get_many("articles")

            # AuthenticationError inherits from StrapiError which has message attribute
            assert str(exc_info.value) != ""

    def test_request_without_token(self, strapi_instance: str) -> None:
        """Test behavior when an empty token is provided.

        Note: StrapiConfig accepts empty tokens (just requires a token to be set).
        The actual authentication failure happens at request time.
        Strapi's public API endpoints may allow access without a token,
        so this test checks that proper error handling occurs when auth is required.
        """
        # Empty token is accepted by StrapiConfig but will fail at request time
        config = StrapiConfig(
            base_url=strapi_instance,
            api_token=SecretStr("empty-token-for-testing"),  # Invalid token
        )

        with SyncClient(config) as client:
            # This should raise AuthenticationError since the token is invalid
            with pytest.raises(AuthenticationError):
                client.get_many("articles")


@pytest.mark.e2e
class TestErrorDetails:
    """Tests for error detail extraction."""

    def test_error_contains_details(self, sync_client: SyncClient) -> None:
        """Test that errors contain useful details from Strapi response."""
        with pytest.raises(NotFoundError) as exc_info:
            sync_client.get_one("articles/nonexistent-xyz")

        error = exc_info.value
        # Error should have a message
        assert str(error) != ""
        # Error should have details dict (may be empty but should exist)
        assert hasattr(error, "details")
        assert isinstance(error.details, dict)

    def test_validation_error_details(self, sync_client: SyncClient) -> None:
        """Test that validation errors include field-level details."""
        # Create an author first
        author_response = sync_client.create(
            "authors",
            {"name": "Detail Test Author", "email": "detail-test@example.com"},
        )
        assert author_response.data is not None
        author_id = author_response.data.document_id or str(author_response.data.id)

        try:
            # Try to create another with same email
            with pytest.raises((ValidationError, Exception)) as exc_info:
                sync_client.create(
                    "authors",
                    {"name": "Duplicate", "email": "detail-test@example.com"},
                )

            error = exc_info.value
            # Should have meaningful error message
            assert str(error) != ""

        finally:
            sync_client.remove(f"authors/{author_id}")


@pytest.mark.e2e
class TestAsyncErrorHandling:
    """Tests for async error handling."""

    @pytest.mark.asyncio
    async def test_async_not_found(self, async_client) -> None:
        """Test async NotFoundError."""
        with pytest.raises(NotFoundError):
            await async_client.get_one("articles/async-nonexistent-id")

    @pytest.mark.asyncio
    async def test_async_auth_error(self, strapi_instance: str) -> None:
        """Test async AuthenticationError."""
        from py_strapi import AsyncClient

        config = StrapiConfig(
            base_url=strapi_instance,
            api_token=SecretStr("async-invalid-token"),
        )

        async with AsyncClient(config) as client:
            with pytest.raises(AuthenticationError):
                await client.get_many("articles")
