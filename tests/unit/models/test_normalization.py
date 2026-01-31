"""Tests for response normalization layer."""

from datetime import datetime

from py_strapi.models.response.normalized import NormalizedEntity
from py_strapi.models.response.v4 import V4Attributes, V4Entity
from py_strapi.models.response.v5 import V5Entity


class TestNormalizedEntity:
    """Tests for NormalizedEntity model."""

    def test_direct_creation(self) -> None:
        """Test creating normalized entity directly."""
        entity = NormalizedEntity(
            id=1,
            document_id="abc123",
            created_at=datetime(2024, 1, 1),
            updated_at=datetime(2024, 1, 2),
            published_at=datetime(2024, 1, 3),
            locale="en",
            attributes={"title": "Test", "content": "Body"},
        )

        assert entity.id == 1
        assert entity.document_id == "abc123"
        assert entity.created_at == datetime(2024, 1, 1)
        assert entity.attributes["title"] == "Test"
        assert entity.attributes["content"] == "Body"


class TestFromV4:
    """Tests for normalizing v4 entities."""

    def test_normalize_v4_basic(self) -> None:
        """Test normalizing basic v4 entity."""
        v4_entity = V4Entity(
            id=1,
            attributes=V4Attributes(
                createdAt=datetime(2024, 1, 1),
                updatedAt=datetime(2024, 1, 2),
                title="Test Article",
                content="Article content",
            ),
        )

        normalized = NormalizedEntity.from_v4(v4_entity)

        assert normalized.id == 1
        assert normalized.document_id is None  # v4 doesn't have document_id
        assert normalized.created_at == datetime(2024, 1, 1)
        assert normalized.updated_at == datetime(2024, 1, 2)
        assert normalized.attributes["title"] == "Test Article"
        assert normalized.attributes["content"] == "Article content"

    def test_normalize_v4_with_locale(self) -> None:
        """Test normalizing v4 entity with locale."""
        v4_entity = V4Entity(
            id=1,
            attributes=V4Attributes(
                locale="fr",
                title="Bonjour",
            ),
        )

        normalized = NormalizedEntity.from_v4(v4_entity)

        assert normalized.locale == "fr"
        assert normalized.attributes["title"] == "Bonjour"

    def test_normalize_v4_with_published_at(self) -> None:
        """Test normalizing v4 entity with publishedAt."""
        published_time = datetime(2024, 1, 15)
        v4_entity = V4Entity(
            id=1, attributes=V4Attributes(publishedAt=published_time, title="Published Article")
        )

        normalized = NormalizedEntity.from_v4(v4_entity)

        assert normalized.published_at == published_time
        assert normalized.attributes["title"] == "Published Article"

    def test_normalize_v4_complex_attributes(self) -> None:
        """Test normalizing v4 entity with complex attributes."""
        v4_entity = V4Entity(
            id=1,
            attributes=V4Attributes(
                createdAt=datetime(2024, 1, 1),
                title="Complex Article",
                views=1000,
                likes=50,
                tags=["python", "django", "strapi"],
                metadata={"category": "tech", "featured": True},
            ),
        )

        normalized = NormalizedEntity.from_v4(v4_entity)

        assert normalized.attributes["title"] == "Complex Article"
        assert normalized.attributes["views"] == 1000
        assert normalized.attributes["likes"] == 50
        assert normalized.attributes["tags"] == ["python", "django", "strapi"]
        assert normalized.attributes["metadata"] == {"category": "tech", "featured": True}

    def test_normalize_v4_minimal(self) -> None:
        """Test normalizing v4 entity with minimal data."""
        v4_entity = V4Entity(id=42, attributes=V4Attributes())

        normalized = NormalizedEntity.from_v4(v4_entity)

        assert normalized.id == 42
        assert normalized.document_id is None
        assert normalized.created_at is None
        assert normalized.updated_at is None
        assert normalized.published_at is None
        assert normalized.locale is None


class TestFromV5:
    """Tests for normalizing v5 entities."""

    def test_normalize_v5_basic(self) -> None:
        """Test normalizing basic v5 entity."""
        v5_entity = V5Entity(
            id=1,
            documentId="abc123",
            createdAt=datetime(2024, 1, 1),
            updatedAt=datetime(2024, 1, 2),
            title="Test Article",
            content="Article content",
        )

        normalized = NormalizedEntity.from_v5(v5_entity)

        assert normalized.id == 1
        assert normalized.document_id == "abc123"
        assert normalized.created_at == datetime(2024, 1, 1)
        assert normalized.updated_at == datetime(2024, 1, 2)
        assert normalized.attributes["title"] == "Test Article"
        assert normalized.attributes["content"] == "Article content"

    def test_normalize_v5_with_locale(self) -> None:
        """Test normalizing v5 entity with locale."""
        v5_entity = V5Entity(
            id=1,
            documentId="abc123",
            locale="de",
            title="Hallo Welt",
        )

        normalized = NormalizedEntity.from_v5(v5_entity)

        assert normalized.locale == "de"
        assert normalized.attributes["title"] == "Hallo Welt"

    def test_normalize_v5_with_published_at(self) -> None:
        """Test normalizing v5 entity with publishedAt."""
        published_time = datetime(2024, 1, 15)
        v5_entity = V5Entity(
            id=1,
            documentId="abc123",
            publishedAt=published_time,
            title="Published Article",
        )

        normalized = NormalizedEntity.from_v5(v5_entity)

        assert normalized.published_at == published_time
        assert normalized.attributes["title"] == "Published Article"

    def test_normalize_v5_complex_attributes(self) -> None:
        """Test normalizing v5 entity with complex attributes."""
        v5_entity = V5Entity(
            id=1,
            documentId="xyz789",
            createdAt=datetime(2024, 1, 1),
            title="Complex Article",
            views=1000,
            likes=50,
            tags=["python", "fastapi", "strapi"],
            metadata={"category": "tech", "featured": True},
        )

        normalized = NormalizedEntity.from_v5(v5_entity)

        assert normalized.attributes["title"] == "Complex Article"
        assert normalized.attributes["views"] == 1000
        assert normalized.attributes["likes"] == 50
        assert normalized.attributes["tags"] == ["python", "fastapi", "strapi"]
        assert normalized.attributes["metadata"] == {"category": "tech", "featured": True}

    def test_normalize_v5_minimal(self) -> None:
        """Test normalizing v5 entity with minimal data."""
        v5_entity = V5Entity(id=42, documentId="minimal123")

        normalized = NormalizedEntity.from_v5(v5_entity)

        assert normalized.id == 42
        assert normalized.document_id == "minimal123"
        assert normalized.created_at is None
        assert normalized.updated_at is None
        assert normalized.published_at is None
        assert normalized.locale is None


class TestV4VsV5Normalization:
    """Tests comparing v4 and v5 normalization results."""

    def test_equivalent_data_normalizes_similarly(self) -> None:
        """Test that equivalent v4 and v5 entities normalize to similar structure."""
        # Create equivalent entities
        v4_entity = V4Entity(
            id=1,
            attributes=V4Attributes(
                createdAt=datetime(2024, 1, 1),
                title="Same Article",
                content="Same content",
            ),
        )

        v5_entity = V5Entity(
            id=1,
            documentId="abc123",
            createdAt=datetime(2024, 1, 1),
            title="Same Article",
            content="Same content",
        )

        # Normalize both
        normalized_v4 = NormalizedEntity.from_v4(v4_entity)
        normalized_v5 = NormalizedEntity.from_v5(v5_entity)

        # Compare (except document_id which v4 doesn't have)
        assert normalized_v4.id == normalized_v5.id
        assert normalized_v4.created_at == normalized_v5.created_at
        assert normalized_v4.attributes["title"] == normalized_v5.attributes["title"]
        assert normalized_v4.attributes["content"] == normalized_v5.attributes["content"]

        # v4 doesn't have document_id
        assert normalized_v4.document_id is None
        assert normalized_v5.document_id == "abc123"

    def test_system_fields_extracted_consistently(self) -> None:
        """Test that system fields are extracted consistently from both versions."""
        v4_entity = V4Entity(
            id=1,
            attributes=V4Attributes(
                createdAt=datetime(2024, 1, 1),
                updatedAt=datetime(2024, 1, 2),
                publishedAt=datetime(2024, 1, 3),
                locale="en",
                custom_field="value",
            ),
        )

        v5_entity = V5Entity(
            id=1,
            documentId="abc",
            createdAt=datetime(2024, 1, 1),
            updatedAt=datetime(2024, 1, 2),
            publishedAt=datetime(2024, 1, 3),
            locale="en",
            custom_field="value",
        )

        normalized_v4 = NormalizedEntity.from_v4(v4_entity)
        normalized_v5 = NormalizedEntity.from_v5(v5_entity)

        # All system fields should match
        assert normalized_v4.created_at == normalized_v5.created_at
        assert normalized_v4.updated_at == normalized_v5.updated_at
        assert normalized_v4.published_at == normalized_v5.published_at
        assert normalized_v4.locale == normalized_v5.locale

        # Custom fields should be in attributes
        assert normalized_v4.attributes["custom_field"] == "value"
        assert normalized_v5.attributes["custom_field"] == "value"
