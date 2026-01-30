"""Tests for Strapi v4 response models."""

from datetime import datetime

from py_strapi.models.response.v4 import V4Attributes, V4CollectionResponse, V4Entity


class TestV4Attributes:
    """Tests for V4Attributes model."""

    def test_basic_attributes(self) -> None:
        """Test v4 attributes with basic fields."""
        attrs = V4Attributes(
            createdAt=datetime(2024, 1, 1),
            updatedAt=datetime(2024, 1, 2),
            publishedAt=datetime(2024, 1, 3),
            locale="en",
        )

        assert attrs.created_at == datetime(2024, 1, 1)
        assert attrs.updated_at == datetime(2024, 1, 2)
        assert attrs.published_at == datetime(2024, 1, 3)
        assert attrs.locale == "en"

    def test_custom_fields(self) -> None:
        """Test v4 attributes with custom fields."""
        attrs = V4Attributes(
            createdAt=datetime(2024, 1, 1),
            title="Test Article",
            content="Article body",
            views=100,
        )

        # Custom fields should be accessible
        assert attrs.model_extra["title"] == "Test Article"  # type: ignore
        assert attrs.model_extra["content"] == "Article body"  # type: ignore
        assert attrs.model_extra["views"] == 100  # type: ignore

    def test_optional_timestamps(self) -> None:
        """Test v4 attributes with optional timestamps."""
        attrs = V4Attributes(title="Test")

        assert attrs.created_at is None
        assert attrs.updated_at is None
        assert attrs.published_at is None
        assert attrs.locale is None


class TestV4Entity:
    """Tests for V4Entity model."""

    def test_basic_entity(self) -> None:
        """Test basic v4 entity structure."""
        entity = V4Entity(
            id=1,
            attributes=V4Attributes(createdAt=datetime(2024, 1, 1), title="Test", content="Body"),
        )

        assert entity.id == 1
        assert entity.attributes.created_at == datetime(2024, 1, 1)
        assert entity.attributes.model_extra["title"] == "Test"  # type: ignore

    def test_entity_from_api_response(self) -> None:
        """Test parsing v4 entity from API response."""
        api_data = {
            "id": 42,
            "attributes": {
                "title": "Hello World",
                "content": "Article content",
                "views": 1000,
                "createdAt": "2024-01-01T12:00:00.000Z",
                "updatedAt": "2024-01-02T12:00:00.000Z",
                "publishedAt": "2024-01-03T12:00:00.000Z",
                "locale": "en",
            },
        }

        entity = V4Entity(**api_data)

        assert entity.id == 42
        assert entity.attributes.model_extra["title"] == "Hello World"  # type: ignore
        assert entity.attributes.model_extra["content"] == "Article content"  # type: ignore
        assert entity.attributes.model_extra["views"] == 1000  # type: ignore
        assert entity.attributes.locale == "en"


class TestV4CollectionResponse:
    """Tests for V4CollectionResponse model."""

    def test_collection_response(self) -> None:
        """Test v4 collection response."""
        response = V4CollectionResponse(
            data=[
                V4Entity(id=1, attributes=V4Attributes(title="First")),
                V4Entity(id=2, attributes=V4Attributes(title="Second")),
            ]
        )

        assert len(response.data) == 2
        assert response.data[0].id == 1
        assert response.data[1].id == 2

    def test_collection_with_pagination(self) -> None:
        """Test v4 collection with pagination metadata."""
        api_data = {
            "data": [
                {"id": 1, "attributes": {"title": "Article 1"}},
                {"id": 2, "attributes": {"title": "Article 2"}},
            ],
            "meta": {"pagination": {"page": 1, "pageSize": 25, "pageCount": 10, "total": 250}},
        }

        response = V4CollectionResponse(**api_data)

        assert len(response.data) == 2
        assert response.meta is not None
        assert response.meta.pagination is not None
        assert response.meta.pagination.page == 1
        assert response.meta.pagination.total == 250

    def test_empty_collection(self) -> None:
        """Test empty v4 collection."""
        response = V4CollectionResponse(data=[])

        assert len(response.data) == 0
        assert response.data == []
