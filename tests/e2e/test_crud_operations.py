"""E2E tests for CRUD operations.

Tests create, read, update, and delete operations against a real Strapi instance.
"""

from __future__ import annotations

import pytest

from py_strapi import SyncClient
from py_strapi.exceptions import NotFoundError


@pytest.mark.e2e
class TestCreateOperations:
    """Tests for create operations."""

    def test_create_article(self, sync_client: SyncClient) -> None:
        """Test creating an article and verifying the response."""
        data = {
            "title": "Test Article",
            "content": "This is test content for the article.",
            "slug": "test-article-create",
            "status": "draft",
            "views": 0,
        }

        response = sync_client.create("articles", data)

        assert response.data is not None
        assert response.data.id is not None
        assert response.data.attributes["title"] == "Test Article"
        assert response.data.attributes["status"] == "draft"

        # Cleanup
        article_id = response.data.document_id or str(response.data.id)
        sync_client.remove(f"articles/{article_id}")

    def test_create_with_relations(self, sync_client: SyncClient) -> None:
        """Test creating entities with relations."""
        # Create a category first
        category_response = sync_client.create(
            "categories",
            {"name": "Test Category", "slug": "test-category-rel"},
        )
        assert category_response.data is not None
        category_id = category_response.data.document_id or category_response.data.id

        # Create an article with the category relation
        article_response = sync_client.create(
            "articles",
            {
                "title": "Article with Category",
                "slug": "article-with-category",
                "category": category_id,
            },
        )

        assert article_response.data is not None

        # Cleanup (reverse order)
        article_id = article_response.data.document_id or str(article_response.data.id)
        category_id_cleanup = category_response.data.document_id or str(category_response.data.id)
        sync_client.remove(f"articles/{article_id}")
        sync_client.remove(f"categories/{category_id_cleanup}")


@pytest.mark.e2e
class TestReadOperations:
    """Tests for read operations."""

    def test_get_one_article(self, sync_client: SyncClient) -> None:
        """Test retrieving a single article."""
        # Create test data
        create_response = sync_client.create(
            "articles",
            {"title": "Article to Read", "slug": "article-to-read"},
        )
        assert create_response.data is not None
        article_id = create_response.data.document_id or str(create_response.data.id)

        # Get the article - endpoint includes the ID
        response = sync_client.get_one(f"articles/{article_id}")

        assert response.data is not None
        assert response.data.attributes["title"] == "Article to Read"

        # Cleanup
        sync_client.remove(f"articles/{article_id}")

    def test_get_many_articles(self, sync_client: SyncClient) -> None:
        """Test retrieving multiple articles with pagination metadata."""
        # Create test articles
        created_ids = []
        for i in range(3):
            response = sync_client.create(
                "articles",
                {"title": f"List Article {i}", "slug": f"list-article-{i}"},
            )
            if response.data:
                created_ids.append(response.data.document_id or str(response.data.id))

        # Get articles
        response = sync_client.get_many("articles")

        assert response.data is not None
        assert len(response.data) > 0
        assert response.meta is not None
        assert response.meta.pagination is not None

        # Cleanup
        for article_id in created_ids:
            sync_client.remove(f"articles/{article_id}")

    def test_get_nonexistent_article(self, sync_client: SyncClient) -> None:
        """Test that getting a nonexistent article raises NotFoundError."""
        with pytest.raises(NotFoundError):
            sync_client.get_one("articles/nonexistent-document-id-12345")


@pytest.mark.e2e
class TestUpdateOperations:
    """Tests for update operations."""

    def test_update_article(self, sync_client: SyncClient) -> None:
        """Test updating an article and verifying changes."""
        # Create test article
        create_response = sync_client.create(
            "articles",
            {"title": "Original Title", "slug": "article-to-update", "views": 0},
        )
        assert create_response.data is not None
        article_id = create_response.data.document_id or str(create_response.data.id)

        # Update the article - endpoint includes the ID, data is second arg
        update_response = sync_client.update(
            f"articles/{article_id}",
            {"title": "Updated Title", "views": 100},
        )

        assert update_response.data is not None
        assert update_response.data.attributes["title"] == "Updated Title"
        assert update_response.data.attributes["views"] == 100

        # Verify by fetching
        get_response = sync_client.get_one(f"articles/{article_id}")
        assert get_response.data is not None
        assert get_response.data.attributes["title"] == "Updated Title"

        # Cleanup
        sync_client.remove(f"articles/{article_id}")

    def test_partial_update(self, sync_client: SyncClient) -> None:
        """Test partial update (only some fields)."""
        # Create test article
        create_response = sync_client.create(
            "articles",
            {"title": "Partial Update Test", "slug": "partial-update", "status": "draft"},
        )
        assert create_response.data is not None
        article_id = create_response.data.document_id or str(create_response.data.id)

        # Update only status
        update_response = sync_client.update(
            f"articles/{article_id}",
            {"status": "published"},
        )

        assert update_response.data is not None
        assert update_response.data.attributes["status"] == "published"
        # Title should remain unchanged
        assert update_response.data.attributes["title"] == "Partial Update Test"

        # Cleanup
        sync_client.remove(f"articles/{article_id}")


@pytest.mark.e2e
class TestDeleteOperations:
    """Tests for delete operations."""

    def test_delete_article(self, sync_client: SyncClient) -> None:
        """Test deleting an article and verifying it's gone."""
        # Create test article
        create_response = sync_client.create(
            "articles",
            {"title": "Article to Delete", "slug": "article-to-delete"},
        )
        assert create_response.data is not None
        article_id = create_response.data.document_id or str(create_response.data.id)

        # Delete the article
        sync_client.remove(f"articles/{article_id}")

        # Verify it's deleted
        with pytest.raises(NotFoundError):
            sync_client.get_one(f"articles/{article_id}")

    def test_delete_with_relations(self, sync_client: SyncClient) -> None:
        """Test deleting entities with relations."""
        # Create category
        category_response = sync_client.create(
            "categories",
            {"name": "Category to Delete", "slug": "category-to-delete"},
        )
        assert category_response.data is not None
        category_id = category_response.data.document_id or str(category_response.data.id)

        # Create article with category
        article_response = sync_client.create(
            "articles",
            {"title": "Article with Cat", "slug": "article-with-cat", "category": category_id},
        )
        assert article_response.data is not None
        article_id = article_response.data.document_id or str(article_response.data.id)

        # Delete article first (respects foreign key)
        sync_client.remove(f"articles/{article_id}")

        # Now delete category
        sync_client.remove(f"categories/{category_id}")

        # Verify both are deleted
        with pytest.raises(NotFoundError):
            sync_client.get_one(f"articles/{article_id}")
        with pytest.raises(NotFoundError):
            sync_client.get_one(f"categories/{category_id}")


@pytest.mark.e2e
class TestAsyncCrudOperations:
    """Tests for async CRUD operations."""

    @pytest.mark.asyncio
    async def test_async_create_and_read(self, async_client) -> None:
        """Test async create and read operations."""
        # Create
        create_response = await async_client.create(
            "articles",
            {"title": "Async Article", "slug": "async-article"},
        )
        assert create_response.data is not None
        article_id = create_response.data.document_id or str(create_response.data.id)

        # Read - endpoint includes the ID
        get_response = await async_client.get_one(f"articles/{article_id}")
        assert get_response.data is not None
        assert get_response.data.attributes["title"] == "Async Article"

        # Cleanup
        await async_client.remove(f"articles/{article_id}")

    @pytest.mark.asyncio
    async def test_async_update_and_delete(self, async_client) -> None:
        """Test async update and delete operations."""
        # Create
        create_response = await async_client.create(
            "articles",
            {"title": "Async Update Test", "slug": "async-update-test"},
        )
        assert create_response.data is not None
        article_id = create_response.data.document_id or str(create_response.data.id)

        # Update - endpoint includes ID, data is second arg
        update_response = await async_client.update(
            f"articles/{article_id}",
            {"title": "Async Updated"},
        )
        assert update_response.data is not None
        assert update_response.data.attributes["title"] == "Async Updated"

        # Delete
        await async_client.remove(f"articles/{article_id}")

        # Verify deleted
        with pytest.raises(NotFoundError):
            await async_client.get_one(f"articles/{article_id}")
