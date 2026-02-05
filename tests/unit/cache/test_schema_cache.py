"""Tests for InMemorySchemaCache."""

from typing import Any

import pytest
import respx
from httpx import Response

from strapi_kit import StrapiConfig, SyncClient
from strapi_kit.cache.schema_cache import InMemorySchemaCache
from strapi_kit.exceptions import StrapiError
from strapi_kit.models.schema import ContentTypeSchema, FieldType, RelationType


@pytest.fixture
def strapi_config() -> StrapiConfig:
    """Fixture for test Strapi configuration."""
    return StrapiConfig(
        base_url="http://localhost:1337",
        api_token="test-token",
    )


@pytest.fixture
def mock_schema_response() -> dict[str, Any]:
    """Mock schema response from Strapi API."""
    return {
        "data": {
            "kind": "collectionType",
            "info": {
                "displayName": "Article",
                "singularName": "article",
                "pluralName": "articles",
            },
            "attributes": {
                "title": {
                    "type": "string",
                    "required": True,
                },
                "content": {
                    "type": "text",
                },
                "author": {
                    "type": "relation",
                    "relation": "manyToOne",
                    "target": "api::author.author",
                    "inversedBy": "articles",
                },
                "categories": {
                    "type": "relation",
                    "relation": "manyToMany",
                    "target": "api::category.category",
                    "mappedBy": "articles",
                },
            },
        }
    }


@pytest.mark.respx
def test_cache_initialization(strapi_config: StrapiConfig, respx_mock: respx.Router) -> None:
    """Test cache initialization."""
    with SyncClient(strapi_config) as client:
        cache = InMemorySchemaCache(client)

        assert cache.cache_size == 0
        assert cache.fetch_count == 0


@pytest.mark.respx
def test_get_schema_fetches_on_miss(
    strapi_config: StrapiConfig, mock_schema_response: dict[str, Any], respx_mock: respx.Router
) -> None:
    """Test that get_schema fetches from API on cache miss."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=Response(200, json=mock_schema_response))

    with SyncClient(strapi_config) as client:
        cache = InMemorySchemaCache(client)

        schema = cache.get_schema("api::article.article")

        assert schema.uid == "api::article.article"
        assert schema.display_name == "Article"
        assert schema.kind == "collectionType"
        assert cache.cache_size == 1
        assert cache.fetch_count == 1


@pytest.mark.respx
def test_get_schema_returns_cached_on_hit(
    strapi_config: StrapiConfig, mock_schema_response: dict[str, Any], respx_mock: respx.Router
) -> None:
    """Test that get_schema returns cached schema on hit."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=Response(200, json=mock_schema_response))

    with SyncClient(strapi_config) as client:
        cache = InMemorySchemaCache(client)

        # First call - cache miss
        schema1 = cache.get_schema("api::article.article")

        # Second call - cache hit
        schema2 = cache.get_schema("api::article.article")

        assert schema1 is schema2
        assert cache.fetch_count == 1  # Only fetched once


@pytest.mark.respx
def test_has_schema(
    strapi_config: StrapiConfig, mock_schema_response: dict[str, Any], respx_mock: respx.Router
) -> None:
    """Test has_schema method."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=Response(200, json=mock_schema_response))

    with SyncClient(strapi_config) as client:
        cache = InMemorySchemaCache(client)

        assert not cache.has_schema("api::article.article")

        cache.get_schema("api::article.article")

        assert cache.has_schema("api::article.article")


@pytest.mark.respx
def test_cache_schema(strapi_config: StrapiConfig, respx_mock: respx.Router) -> None:
    """Test manually caching a schema."""
    with SyncClient(strapi_config) as client:
        cache = InMemorySchemaCache(client)

        schema = ContentTypeSchema(
            uid="api::article.article",
            display_name="Article",
            fields={},
        )

        cache.cache_schema("api::article.article", schema)

        assert cache.has_schema("api::article.article")
        assert cache.cache_size == 1
        assert cache.fetch_count == 0  # No API fetch


@pytest.mark.respx
def test_clear_cache(
    strapi_config: StrapiConfig, mock_schema_response: dict[str, Any], respx_mock: respx.Router
) -> None:
    """Test clearing the cache."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=Response(200, json=mock_schema_response))

    with SyncClient(strapi_config) as client:
        cache = InMemorySchemaCache(client)

        cache.get_schema("api::article.article")
        assert cache.cache_size == 1

        cache.clear_cache()

        assert cache.cache_size == 0
        assert cache.fetch_count == 0


@pytest.mark.respx
def test_parse_schema_response(
    strapi_config: StrapiConfig, mock_schema_response: dict[str, Any], respx_mock: respx.Router
) -> None:
    """Test parsing schema response."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=Response(200, json=mock_schema_response))

    with SyncClient(strapi_config) as client:
        cache = InMemorySchemaCache(client)
        schema = cache.get_schema("api::article.article")

        # Check fields
        assert "title" in schema.fields
        assert "content" in schema.fields
        assert "author" in schema.fields
        assert "categories" in schema.fields

        # Check title field
        title_field = schema.fields["title"]
        assert title_field.type == FieldType.STRING
        assert title_field.required is True

        # Check content field
        content_field = schema.fields["content"]
        assert content_field.type == FieldType.TEXT


@pytest.mark.respx
def test_parse_field_schema_relation(
    strapi_config: StrapiConfig, mock_schema_response: dict[str, Any], respx_mock: respx.Router
) -> None:
    """Test parsing relation field schema."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=Response(200, json=mock_schema_response))

    with SyncClient(strapi_config) as client:
        cache = InMemorySchemaCache(client)
        schema = cache.get_schema("api::article.article")

        # Check author relation
        author_field = schema.fields["author"]
        assert author_field.type == FieldType.RELATION
        assert author_field.relation == RelationType.MANY_TO_ONE
        assert author_field.target == "api::author.author"
        assert author_field.inversed_by == "articles"

        # Check categories relation
        categories_field = schema.fields["categories"]
        assert categories_field.type == FieldType.RELATION
        assert categories_field.relation == RelationType.MANY_TO_MANY
        assert categories_field.target == "api::category.category"
        assert categories_field.mapped_by == "articles"


@pytest.mark.respx
def test_get_field_target(
    strapi_config: StrapiConfig, mock_schema_response: dict[str, Any], respx_mock: respx.Router
) -> None:
    """Test getting field target for relation."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=Response(200, json=mock_schema_response))

    with SyncClient(strapi_config) as client:
        cache = InMemorySchemaCache(client)
        schema = cache.get_schema("api::article.article")

        # Relation field
        assert schema.get_field_target("author") == "api::author.author"
        assert schema.get_field_target("categories") == "api::category.category"

        # Non-relation field
        assert schema.get_field_target("title") is None

        # Non-existent field
        assert schema.get_field_target("nonexistent") is None


@pytest.mark.respx
def test_is_relation_field(
    strapi_config: StrapiConfig, mock_schema_response: dict[str, Any], respx_mock: respx.Router
) -> None:
    """Test checking if field is a relation."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=Response(200, json=mock_schema_response))

    with SyncClient(strapi_config) as client:
        cache = InMemorySchemaCache(client)
        schema = cache.get_schema("api::article.article")

        assert schema.is_relation_field("author") is True
        assert schema.is_relation_field("categories") is True
        assert schema.is_relation_field("title") is False
        assert schema.is_relation_field("nonexistent") is False


@pytest.mark.respx
def test_fetch_schema_error_handling(strapi_config: StrapiConfig, respx_mock: respx.Router) -> None:
    """Test error handling when fetching schema."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=Response(404, json={"error": "Not found"}))

    with SyncClient(strapi_config) as client:
        cache = InMemorySchemaCache(client)

        with pytest.raises(StrapiError) as exc_info:
            cache.get_schema("api::article.article")

        assert "Failed to fetch schema" in str(exc_info.value)


@pytest.mark.respx
def test_parse_unknown_field_type(strapi_config: StrapiConfig, respx_mock: respx.Router) -> None:
    """Test parsing schema with unknown field type."""
    mock_response = {
        "data": {
            "kind": "collectionType",
            "info": {"displayName": "Test"},
            "attributes": {
                "custom_field": {
                    "type": "unknown-custom-type",
                    "required": False,
                }
            },
        }
    }

    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::test.test"
    ).mock(return_value=Response(200, json=mock_response))

    with SyncClient(strapi_config) as client:
        cache = InMemorySchemaCache(client)
        schema = cache.get_schema("api::test.test")

        # Unknown types should fallback to STRING
        assert schema.fields["custom_field"].type == FieldType.STRING


# Tests for ACTUAL Strapi v5 format (Issue #28)


@pytest.fixture
def mock_actual_v5_schema_response() -> dict[str, Any]:
    """Mock ACTUAL Strapi v5 schema response (Issue #28).

    This is the real format Strapi v5 returns, with displayName/singularName/pluralName
    at the schema top level, not nested in schema.info.
    """
    return {
        "data": {
            "uid": "api::article.article",
            "apiID": "article",
            "schema": {
                "displayName": "Article",  # At top level, NOT in info!
                "singularName": "article",
                "pluralName": "articles",
                "kind": "collectionType",
                "attributes": {
                    "title": {
                        "type": "string",
                        "required": True,
                    },
                    "author": {
                        "type": "relation",
                        "relation": "manyToOne",
                        "target": "api::author.author",
                    },
                },
            },
        }
    }


@pytest.mark.respx
def test_fetch_schema_actual_v5_format(
    strapi_config: StrapiConfig,
    mock_actual_v5_schema_response: dict[str, Any],
    respx_mock: respx.Router,
) -> None:
    """Test fetching schema with actual v5 format (Issue #28)."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=Response(200, json=mock_actual_v5_schema_response))

    with SyncClient(strapi_config) as client:
        cache = InMemorySchemaCache(client)

        schema = cache.get_schema("api::article.article")

        # Should correctly extract info from flat schema
        assert schema.uid == "api::article.article"
        assert schema.display_name == "Article"
        assert schema.singular_name == "article"
        assert schema.plural_name == "articles"
        assert schema.kind == "collectionType"

        # Fields should be parsed correctly
        assert "title" in schema.fields
        assert "author" in schema.fields
        assert schema.fields["title"].type == FieldType.STRING
        assert schema.fields["title"].required is True
        assert schema.fields["author"].type == FieldType.RELATION
        assert schema.fields["author"].target == "api::author.author"


@pytest.mark.respx
def test_parse_schema_response_actual_v5_format(
    strapi_config: StrapiConfig,
    mock_actual_v5_schema_response: dict[str, Any],
    respx_mock: respx.Router,
) -> None:
    """Test _parse_schema_response with actual v5 format (Issue #28)."""
    with SyncClient(strapi_config) as client:
        cache = InMemorySchemaCache(client)

        # Simulate the data structure as it comes from the API
        schema_data = mock_actual_v5_schema_response["data"]

        schema = cache._parse_schema_response("api::article.article", schema_data)

        # Should correctly handle nested schema and extract flat info
        assert schema.display_name == "Article"
        assert schema.singular_name == "article"
        assert schema.plural_name == "articles"
        assert schema.kind == "collectionType"


def test_extract_info_from_schema_flat() -> None:
    """Test extract_info_from_schema with flat v5 format."""
    from strapi_kit.utils.schema import extract_info_from_schema

    flat_schema = {
        "displayName": "Article",
        "singularName": "article",
        "pluralName": "articles",
        "description": "Blog articles",
    }

    info = extract_info_from_schema(flat_schema)

    assert info["displayName"] == "Article"
    assert info["singularName"] == "article"
    assert info["pluralName"] == "articles"
    assert info["description"] == "Blog articles"


def test_extract_info_from_schema_nested() -> None:
    """Test extract_info_from_schema with nested format (should still work)."""
    from strapi_kit.utils.schema import extract_info_from_schema

    nested_schema = {
        "info": {
            "displayName": "Article",
            "singularName": "article",
            "pluralName": "articles",
        }
    }

    info = extract_info_from_schema(nested_schema)

    # Should use nested info when present
    assert info["displayName"] == "Article"
    assert info["singularName"] == "article"
    assert info["pluralName"] == "articles"


@pytest.mark.respx
def test_schema_cache_v5_relation_methods(
    strapi_config: StrapiConfig,
    mock_actual_v5_schema_response: dict[str, Any],
    respx_mock: respx.Router,
) -> None:
    """Test schema helper methods work correctly with v5 format."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=Response(200, json=mock_actual_v5_schema_response))

    with SyncClient(strapi_config) as client:
        cache = InMemorySchemaCache(client)
        schema = cache.get_schema("api::article.article")

        # Test relation field detection
        assert schema.is_relation_field("author") is True
        assert schema.is_relation_field("title") is False

        # Test get_field_target
        assert schema.get_field_target("author") == "api::author.author"
        assert schema.get_field_target("title") is None
