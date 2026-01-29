"""Tests for Strapi v5 response models."""

from datetime import datetime

import pytest

from py_strapi.models.response.v5 import V5CollectionResponse, V5Entity


class TestV5Entity:
    """Tests for V5Entity model."""

    def test_basic_entity(self) -> None:
        """Test basic v5 entity structure."""
        entity = V5Entity(
            id=1,
            documentId="abc123",
            createdAt=datetime(2024, 1, 1),
            updatedAt=datetime(2024, 1, 2),
            publishedAt=datetime(2024, 1, 3),
            locale="en",
        )

        assert entity.id == 1
        assert entity.document_id == "abc123"
        assert entity.created_at == datetime(2024, 1, 1)
        assert entity.updated_at == datetime(2024, 1, 2)
        assert entity.published_at == datetime(2024, 1, 3)
        assert entity.locale == "en"

    def test_entity_with_custom_fields(self) -> None:
        """Test v5 entity with custom fields."""
        entity = V5Entity(
            id=1,
            documentId="abc123",
            title="Test Article",
            content="Article body",
            views=100,
        )

        # Custom fields should be accessible via model_extra
        assert entity.model_extra["title"] == "Test Article"  # type: ignore
        assert entity.model_extra["content"] == "Article body"  # type: ignore
        assert entity.model_extra["views"] == 100  # type: ignore

    def test_entity_from_api_response(self) -> None:
        """Test parsing v5 entity from API response."""
        api_data = {
            "id": 42,
            "documentId": "xyz789",
            "title": "Hello World",
            "content": "Article content",
            "views": 1000,
            "author": "John Doe",
            "createdAt": "2024-01-01T12:00:00.000Z",
            "updatedAt": "2024-01-02T12:00:00.000Z",
            "publishedAt": "2024-01-03T12:00:00.000Z",
            "locale": "en",
        }

        entity = V5Entity(**api_data)

        assert entity.id == 42
        assert entity.document_id == "xyz789"
        assert entity.model_extra["title"] == "Hello World"  # type: ignore
        assert entity.model_extra["content"] == "Article content"  # type: ignore
        assert entity.model_extra["views"] == 1000  # type: ignore
        assert entity.model_extra["author"] == "John Doe"  # type: ignore
        assert entity.locale == "en"

    def test_optional_timestamps(self) -> None:
        """Test v5 entity with optional timestamps."""
        entity = V5Entity(id=1, documentId="abc123")

        assert entity.created_at is None
        assert entity.updated_at is None
        assert entity.published_at is None
        assert entity.locale is None


class TestV5CollectionResponse:
    """Tests for V5CollectionResponse model."""

    def test_collection_response(self) -> None:
        """Test v5 collection response."""
        response = V5CollectionResponse(
            data=[
                V5Entity(id=1, documentId="abc", title="First"),
                V5Entity(id=2, documentId="def", title="Second"),
            ]
        )

        assert len(response.data) == 2
        assert response.data[0].id == 1
        assert response.data[0].document_id == "abc"
        assert response.data[1].id == 2
        assert response.data[1].document_id == "def"

    def test_collection_with_pagination(self) -> None:
        """Test v5 collection with pagination metadata."""
        api_data = {
            "data": [
                {"id": 1, "documentId": "abc", "title": "Article 1"},
                {"id": 2, "documentId": "def", "title": "Article 2"},
            ],
            "meta": {
                "pagination": {"page": 1, "pageSize": 25, "pageCount": 10, "total": 250}
            },
        }

        response = V5CollectionResponse(**api_data)

        assert len(response.data) == 2
        assert response.meta is not None
        assert response.meta.pagination is not None
        assert response.meta.pagination.page == 1
        assert response.meta.pagination.total == 250

    def test_empty_collection(self) -> None:
        """Test empty v5 collection."""
        response = V5CollectionResponse(data=[])

        assert len(response.data) == 0
        assert response.data == []

    def test_collection_from_api_response(self) -> None:
        """Test parsing v5 collection from full API response."""
        api_data = {
            "data": [
                {
                    "id": 1,
                    "documentId": "abc123",
                    "title": "First Article",
                    "slug": "first-article",
                    "createdAt": "2024-01-01T00:00:00.000Z",
                    "publishedAt": "2024-01-02T00:00:00.000Z",
                },
                {
                    "id": 2,
                    "documentId": "def456",
                    "title": "Second Article",
                    "slug": "second-article",
                    "createdAt": "2024-01-03T00:00:00.000Z",
                    "publishedAt": "2024-01-04T00:00:00.000Z",
                },
            ],
            "meta": {
                "pagination": {"page": 1, "pageSize": 2, "pageCount": 5, "total": 10}
            },
        }

        response = V5CollectionResponse(**api_data)

        assert len(response.data) == 2
        assert response.data[0].document_id == "abc123"
        assert response.data[0].model_extra["title"] == "First Article"  # type: ignore
        assert response.data[1].document_id == "def456"
        assert response.data[1].model_extra["title"] == "Second Article"  # type: ignore
