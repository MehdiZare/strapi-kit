"""E2E tests for bulk operations.

Tests bulk create, update, and delete operations against a real Strapi instance.
"""

from __future__ import annotations

import pytest

from strapi_kit import SyncClient


@pytest.mark.e2e
class TestBulkCreateOperations:
    """Tests for bulk create operations."""

    def test_bulk_create_articles(self, sync_client: SyncClient) -> None:
        """Test creating multiple articles in bulk."""
        articles_data = [
            {"title": "Bulk Article 1", "slug": "bulk-article-1", "status": "draft"},
            {"title": "Bulk Article 2", "slug": "bulk-article-2", "status": "draft"},
            {"title": "Bulk Article 3", "slug": "bulk-article-3", "status": "draft"},
        ]

        result = sync_client.bulk_create("articles", articles_data)

        assert result is not None
        assert result.succeeded == 3
        assert result.failed == 0
        assert len(result.successes) == 3

        # Verify all were created
        for entity in result.successes:
            assert entity is not None
            assert entity.id is not None

        # Cleanup
        for entity in result.successes:
            entity_id = entity.document_id or str(entity.id)
            sync_client.remove(f"articles/{entity_id}")

    def test_bulk_create_with_progress(self, sync_client: SyncClient) -> None:
        """Test bulk create with progress callback."""
        articles_data = [
            {"title": f"Progress Article {i}", "slug": f"progress-article-{i}"} for i in range(5)
        ]

        progress_calls: list[tuple[int, int]] = []

        def on_progress(completed: int, total: int) -> None:
            progress_calls.append((completed, total))

        result = sync_client.bulk_create(
            "articles",
            articles_data,
            progress_callback=on_progress,
        )

        assert result.succeeded == 5
        assert len(progress_calls) == 5
        # Progress should be sequential
        for i, (completed, total) in enumerate(progress_calls):
            assert completed == i + 1
            assert total == 5

        # Cleanup
        for entity in result.successes:
            entity_id = entity.document_id or str(entity.id)
            sync_client.remove(f"articles/{entity_id}")


@pytest.mark.e2e
class TestBulkUpdateOperations:
    """Tests for bulk update operations."""

    def test_bulk_update_articles(self, sync_client: SyncClient) -> None:
        """Test updating multiple articles in bulk."""
        # First create some articles
        created_ids = []
        for i in range(3):
            response = sync_client.create(
                "articles",
                {"title": f"Update Target {i}", "slug": f"update-target-{i}", "views": 0},
            )
            if response.data:
                created_ids.append(response.data.document_id or str(response.data.id))

        # Prepare bulk update data (list of tuples: (id, data))
        updates = [(id_, {"views": 100}) for id_ in created_ids]

        result = sync_client.bulk_update("articles", updates)

        assert result is not None
        assert result.succeeded == 3
        assert result.failed == 0

        # Verify updates were applied
        for id_ in created_ids:
            response = sync_client.get_one(f"articles/{id_}")
            assert response.data is not None
            assert response.data.attributes["views"] == 100

        # Cleanup
        for id_ in created_ids:
            sync_client.remove(f"articles/{id_}")

    def test_bulk_update_different_fields(self, sync_client: SyncClient) -> None:
        """Test bulk updating different fields for different entities."""
        # Create articles
        created = []
        for i in range(2):
            response = sync_client.create(
                "articles",
                {
                    "title": f"Different Field {i}",
                    "slug": f"different-field-{i}",
                    "status": "draft",
                    "views": 0,
                },
            )
            if response.data:
                created.append(response.data)

        # Update different fields (list of tuples: (id, data))
        updates = [
            (created[0].document_id or str(created[0].id), {"status": "published"}),
            (created[1].document_id or str(created[1].id), {"views": 500}),
        ]

        result = sync_client.bulk_update("articles", updates)

        assert result.succeeded == 2

        # Verify first article
        id_0 = created[0].document_id or str(created[0].id)
        response1 = sync_client.get_one(f"articles/{id_0}")
        assert response1.data is not None
        assert response1.data.attributes["status"] == "published"

        # Verify second article
        id_1 = created[1].document_id or str(created[1].id)
        response2 = sync_client.get_one(f"articles/{id_1}")
        assert response2.data is not None
        assert response2.data.attributes["views"] == 500

        # Cleanup
        for entity in created:
            entity_id = entity.document_id or str(entity.id)
            sync_client.remove(f"articles/{entity_id}")


@pytest.mark.e2e
class TestBulkDeleteOperations:
    """Tests for bulk delete operations."""

    def test_bulk_delete_articles(self, sync_client: SyncClient) -> None:
        """Test deleting multiple articles in bulk."""
        # Create articles to delete
        created_ids = []
        for i in range(3):
            response = sync_client.create(
                "articles",
                {"title": f"Delete Target {i}", "slug": f"delete-target-{i}"},
            )
            if response.data:
                created_ids.append(response.data.document_id or str(response.data.id))

        result = sync_client.bulk_delete("articles", created_ids)

        assert result is not None
        assert result.succeeded == 3
        assert result.failed == 0

        # Verify all were deleted
        from strapi_kit.exceptions import NotFoundError

        for id_ in created_ids:
            with pytest.raises(NotFoundError):
                sync_client.get_one(f"articles/{id_}")

    def test_bulk_delete_with_nonexistent(self, sync_client: SyncClient) -> None:
        """Test bulk delete with some nonexistent IDs."""
        # Create one real article
        response = sync_client.create(
            "articles",
            {"title": "Real Article", "slug": "real-article-bulk"},
        )
        assert response.data is not None
        real_id = response.data.document_id or str(response.data.id)

        # Try to delete real and fake IDs
        ids_to_delete = [real_id, "nonexistent-id-12345"]

        result = sync_client.bulk_delete("articles", ids_to_delete)

        # At least one should succeed, one should fail
        assert result.succeeded >= 1
        # The nonexistent ID may or may not count as failed depending on Strapi behavior


@pytest.mark.e2e
class TestBulkOperationResult:
    """Tests for BulkOperationResult accuracy."""

    def test_result_accuracy(self, sync_client: SyncClient) -> None:
        """Test that BulkOperationResult accurately reflects outcomes."""
        articles_data = [
            {"title": "Valid Article", "slug": "valid-article-result"},
            # This might fail due to validation (e.g., missing required field in strict mode)
            {"title": "Another Valid", "slug": "another-valid-result"},
        ]

        result = sync_client.bulk_create("articles", articles_data)

        # Verify totals match
        assert result.succeeded + result.failed == len(articles_data)
        assert len(result.successes) + len(result.failures) == len(articles_data)

        # Verify successes have entities
        for entity in result.successes:
            assert entity is not None
            assert entity.id is not None

        # Verify failures have error info
        for failure in result.failures:
            assert failure.error is not None

        # Cleanup successful creates
        for entity in result.successes:
            entity_id = entity.document_id or str(entity.id)
            sync_client.remove(f"articles/{entity_id}")


@pytest.mark.e2e
class TestAsyncBulkOperations:
    """Tests for async bulk operations."""

    @pytest.mark.asyncio
    async def test_async_bulk_create(self, async_client) -> None:
        """Test async bulk create."""
        articles_data = [{"title": f"Async Bulk {i}", "slug": f"async-bulk-{i}"} for i in range(3)]

        result = await async_client.bulk_create("articles", articles_data)

        assert result.succeeded == 3

        # Cleanup
        for entity in result.successes:
            entity_id = entity.document_id or str(entity.id)
            await async_client.remove(f"articles/{entity_id}")

    @pytest.mark.asyncio
    async def test_async_bulk_update(self, async_client) -> None:
        """Test async bulk update."""
        # Create articles
        created_ids = []
        for i in range(2):
            response = await async_client.create(
                "articles",
                {"title": f"Async Update {i}", "slug": f"async-update-{i}", "views": 0},
            )
            if response.data:
                created_ids.append(response.data.document_id or str(response.data.id))

        # Update (list of tuples: (id, data))
        updates = [(id_, {"views": 50}) for id_ in created_ids]
        result = await async_client.bulk_update("articles", updates)

        assert result.succeeded == 2

        # Cleanup
        for id_ in created_ids:
            await async_client.remove(f"articles/{id_}")

    @pytest.mark.asyncio
    async def test_async_bulk_delete(self, async_client) -> None:
        """Test async bulk delete."""
        # Create articles
        created_ids = []
        for i in range(2):
            response = await async_client.create(
                "articles",
                {"title": f"Async Delete {i}", "slug": f"async-delete-{i}"},
            )
            if response.data:
                created_ids.append(response.data.document_id or str(response.data.id))

        # Delete
        result = await async_client.bulk_delete("articles", created_ids)

        assert result.succeeded == 2
