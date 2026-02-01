"""Tests for Content-Type Builder API methods."""

import pytest
import respx
from httpx import Response

from strapi_kit import AsyncClient, StrapiConfig, SyncClient
from strapi_kit.exceptions import NotFoundError
from strapi_kit.models.content_type import (
    ComponentListItem,
    ContentTypeListItem,
)
from strapi_kit.models.content_type import (
    ContentTypeSchema as CTBContentTypeSchema,
)

# Fixtures for mock responses


@pytest.fixture
def mock_content_types_response() -> dict:
    """Mock response for get_content_types."""
    return {
        "data": [
            {
                "uid": "api::article.article",
                "kind": "collectionType",
                "info": {
                    "displayName": "Article",
                    "singularName": "article",
                    "pluralName": "articles",
                    "description": "Blog articles",
                },
                "attributes": {
                    "title": {"type": "string", "required": True},
                    "content": {"type": "richtext"},
                    "author": {
                        "type": "relation",
                        "relation": "manyToOne",
                        "target": "api::author.author",
                    },
                },
            },
            {
                "uid": "api::category.category",
                "kind": "collectionType",
                "info": {
                    "displayName": "Category",
                    "singularName": "category",
                    "pluralName": "categories",
                },
                "attributes": {
                    "name": {"type": "string", "required": True},
                },
            },
            {
                "uid": "plugin::users-permissions.user",
                "kind": "collectionType",
                "info": {
                    "displayName": "User",
                    "singularName": "user",
                    "pluralName": "users",
                },
                "attributes": {
                    "username": {"type": "string"},
                    "email": {"type": "email"},
                },
            },
        ]
    }


@pytest.fixture
def mock_components_response() -> dict:
    """Mock response for get_components."""
    return {
        "data": [
            {
                "uid": "shared.seo",
                "category": "shared",
                "info": {
                    "displayName": "SEO",
                    "description": "SEO metadata",
                },
                "attributes": {
                    "metaTitle": {"type": "string"},
                    "metaDescription": {"type": "text"},
                    "metaImage": {"type": "media"},
                },
            },
            {
                "uid": "blocks.hero",
                "category": "blocks",
                "info": {
                    "displayName": "Hero Section",
                },
                "attributes": {
                    "title": {"type": "string"},
                    "subtitle": {"type": "string"},
                    "image": {"type": "media"},
                },
            },
        ]
    }


@pytest.fixture
def mock_single_content_type_response() -> dict:
    """Mock response for get_content_type_schema."""
    return {
        "data": {
            "uid": "api::article.article",
            "kind": "collectionType",
            "info": {
                "displayName": "Article",
                "singularName": "article",
                "pluralName": "articles",
                "description": "Blog articles",
            },
            "attributes": {
                "title": {"type": "string", "required": True, "maxLength": 255},
                "slug": {"type": "uid", "targetField": "title"},
                "content": {"type": "richtext"},
                "publishedAt": {"type": "datetime"},
                "author": {
                    "type": "relation",
                    "relation": "manyToOne",
                    "target": "api::author.author",
                    "inversedBy": "articles",
                },
                "category": {
                    "type": "relation",
                    "relation": "manyToOne",
                    "target": "api::category.category",
                },
                "seo": {
                    "type": "component",
                    "component": "shared.seo",
                },
                "tags": {
                    "type": "relation",
                    "relation": "manyToMany",
                    "target": "api::tag.tag",
                },
            },
            "options": {
                "draftAndPublish": True,
            },
        }
    }


class TestSyncContentTypeBuilder:
    """Tests for SyncClient Content-Type Builder methods."""

    @respx.mock
    def test_get_content_types(
        self,
        strapi_config: StrapiConfig,
        mock_content_types_response: dict,
    ) -> None:
        """Test listing content types without plugins."""
        respx.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json=mock_content_types_response)
        )

        with SyncClient(strapi_config) as client:
            content_types = client.get_content_types()

            # Should exclude plugin content types by default
            assert len(content_types) == 2
            assert all(isinstance(ct, ContentTypeListItem) for ct in content_types)
            assert all(ct.uid.startswith("api::") for ct in content_types)

            # Check first content type
            article = content_types[0]
            assert article.uid == "api::article.article"
            assert article.kind == "collectionType"
            assert article.info.display_name == "Article"
            assert article.info.singular_name == "article"
            assert article.info.plural_name == "articles"
            assert "title" in article.attributes

    @respx.mock
    def test_get_content_types_include_plugins(
        self,
        strapi_config: StrapiConfig,
        mock_content_types_response: dict,
    ) -> None:
        """Test listing content types including plugins."""
        respx.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json=mock_content_types_response)
        )

        with SyncClient(strapi_config) as client:
            content_types = client.get_content_types(include_plugins=True)

            # Should include all content types
            assert len(content_types) == 3
            plugin_types = [ct for ct in content_types if ct.uid.startswith("plugin::")]
            assert len(plugin_types) == 1
            assert plugin_types[0].uid == "plugin::users-permissions.user"

    @respx.mock
    def test_get_components(
        self,
        strapi_config: StrapiConfig,
        mock_components_response: dict,
    ) -> None:
        """Test listing components."""
        respx.get("http://localhost:1337/api/content-type-builder/components").mock(
            return_value=Response(200, json=mock_components_response)
        )

        with SyncClient(strapi_config) as client:
            components = client.get_components()

            assert len(components) == 2
            assert all(isinstance(c, ComponentListItem) for c in components)

            # Check first component
            seo = components[0]
            assert seo.uid == "shared.seo"
            assert seo.category == "shared"
            assert seo.info.display_name == "SEO"
            assert "metaTitle" in seo.attributes

    @respx.mock
    def test_get_content_type_schema(
        self,
        strapi_config: StrapiConfig,
        mock_single_content_type_response: dict,
    ) -> None:
        """Test getting single content type schema."""
        uid = "api::article.article"
        respx.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
            return_value=Response(200, json=mock_single_content_type_response)
        )

        with SyncClient(strapi_config) as client:
            schema = client.get_content_type_schema(uid)

            assert isinstance(schema, CTBContentTypeSchema)
            assert schema.uid == uid
            assert schema.kind == "collectionType"
            assert schema.display_name == "Article"
            assert schema.singular_name == "article"
            assert schema.plural_name == "articles"

    @respx.mock
    def test_get_content_type_schema_helper_methods(
        self,
        strapi_config: StrapiConfig,
        mock_single_content_type_response: dict,
    ) -> None:
        """Test schema helper methods."""
        uid = "api::article.article"
        respx.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
            return_value=Response(200, json=mock_single_content_type_response)
        )

        with SyncClient(strapi_config) as client:
            schema = client.get_content_type_schema(uid)

            # Test field type detection
            assert schema.get_field_type("title") == "string"
            assert schema.get_field_type("content") == "richtext"
            assert schema.get_field_type("author") == "relation"
            assert schema.get_field_type("seo") == "component"
            assert schema.get_field_type("nonexistent") is None

            # Test relation detection
            assert schema.is_relation_field("author") is True
            assert schema.is_relation_field("title") is False
            assert schema.is_relation_field("seo") is False

            # Test component detection
            assert schema.is_component_field("seo") is True
            assert schema.is_component_field("author") is False

            # Test relation target
            assert schema.get_relation_target("author") == "api::author.author"
            assert schema.get_relation_target("title") is None

            # Test component UID
            assert schema.get_component_uid("seo") == "shared.seo"
            assert schema.get_component_uid("author") is None

    @respx.mock
    def test_get_content_type_schema_not_found(
        self,
        strapi_config: StrapiConfig,
    ) -> None:
        """Test handling of non-existent content type."""
        uid = "api::nonexistent.nonexistent"
        error_response = {
            "error": {
                "status": 404,
                "name": "NotFoundError",
                "message": f"Content type not found: {uid}",
            }
        }
        respx.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
            return_value=Response(404, json=error_response)
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError):
                client.get_content_type_schema(uid)


class TestAsyncContentTypeBuilder:
    """Tests for AsyncClient Content-Type Builder methods."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_content_types(
        self,
        strapi_config: StrapiConfig,
        mock_content_types_response: dict,
    ) -> None:
        """Test listing content types without plugins."""
        respx.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json=mock_content_types_response)
        )

        async with AsyncClient(strapi_config) as client:
            content_types = await client.get_content_types()

            # Should exclude plugin content types by default
            assert len(content_types) == 2
            assert all(isinstance(ct, ContentTypeListItem) for ct in content_types)

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_content_types_include_plugins(
        self,
        strapi_config: StrapiConfig,
        mock_content_types_response: dict,
    ) -> None:
        """Test listing content types including plugins."""
        respx.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json=mock_content_types_response)
        )

        async with AsyncClient(strapi_config) as client:
            content_types = await client.get_content_types(include_plugins=True)

            assert len(content_types) == 3

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_components(
        self,
        strapi_config: StrapiConfig,
        mock_components_response: dict,
    ) -> None:
        """Test listing components."""
        respx.get("http://localhost:1337/api/content-type-builder/components").mock(
            return_value=Response(200, json=mock_components_response)
        )

        async with AsyncClient(strapi_config) as client:
            components = await client.get_components()

            assert len(components) == 2
            assert all(isinstance(c, ComponentListItem) for c in components)

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_content_type_schema(
        self,
        strapi_config: StrapiConfig,
        mock_single_content_type_response: dict,
    ) -> None:
        """Test getting single content type schema."""
        uid = "api::article.article"
        respx.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
            return_value=Response(200, json=mock_single_content_type_response)
        )

        async with AsyncClient(strapi_config) as client:
            schema = await client.get_content_type_schema(uid)

            assert isinstance(schema, CTBContentTypeSchema)
            assert schema.uid == uid
            assert schema.display_name == "Article"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_content_type_schema_not_found(
        self,
        strapi_config: StrapiConfig,
    ) -> None:
        """Test handling of non-existent content type."""
        uid = "api::nonexistent.nonexistent"
        error_response = {
            "error": {
                "status": 404,
                "name": "NotFoundError",
                "message": f"Content type not found: {uid}",
            }
        }
        respx.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
            return_value=Response(404, json=error_response)
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError):
                await client.get_content_type_schema(uid)


class TestContentTypeModels:
    """Tests for Content-Type Builder models."""

    def test_content_type_list_item_validation(self) -> None:
        """Test ContentTypeListItem model validation."""
        data = {
            "uid": "api::article.article",
            "kind": "collectionType",
            "info": {
                "displayName": "Article",
                "singularName": "article",
                "pluralName": "articles",
            },
            "attributes": {"title": {"type": "string"}},
        }
        item = ContentTypeListItem.model_validate(data)

        assert item.uid == "api::article.article"
        assert item.kind == "collectionType"
        assert item.info.display_name == "Article"
        assert item.info.singular_name == "article"
        assert item.info.plural_name == "articles"

    def test_content_type_list_item_defaults(self) -> None:
        """Test ContentTypeListItem with minimal data."""
        data = {
            "uid": "api::page.page",
            "info": {"displayName": "Page"},
        }
        item = ContentTypeListItem.model_validate(data)

        assert item.uid == "api::page.page"
        assert item.kind == "collectionType"  # Default
        assert item.info.display_name == "Page"
        assert item.info.singular_name is None
        assert item.info.plural_name is None
        assert item.attributes == {}

    def test_component_list_item_validation(self) -> None:
        """Test ComponentListItem model validation."""
        data = {
            "uid": "shared.seo",
            "category": "shared",
            "info": {"displayName": "SEO"},
            "attributes": {"metaTitle": {"type": "string"}},
        }
        item = ComponentListItem.model_validate(data)

        assert item.uid == "shared.seo"
        assert item.category == "shared"
        assert item.info.display_name == "SEO"

    def test_ctb_content_type_schema_validation(self) -> None:
        """Test CTBContentTypeSchema model validation."""
        data = {
            "uid": "api::article.article",
            "kind": "collectionType",
            "info": {
                "displayName": "Article",
                "singularName": "article",
                "pluralName": "articles",
            },
            "attributes": {
                "title": {"type": "string"},
                "author": {"type": "relation", "target": "api::author.author"},
                "seo": {"type": "component", "component": "shared.seo"},
            },
        }
        schema = CTBContentTypeSchema.model_validate(data)

        assert schema.uid == "api::article.article"
        assert schema.display_name == "Article"
        assert schema.singular_name == "article"
        assert schema.plural_name == "articles"

    def test_ctb_content_type_schema_properties(self) -> None:
        """Test CTBContentTypeSchema property accessors."""
        data = {
            "uid": "api::article.article",
            "info": {
                "displayName": "Article",
                "singularName": "article",
                "pluralName": "articles",
            },
            "attributes": {},
        }
        schema = CTBContentTypeSchema.model_validate(data)

        # Test property accessors
        assert schema.display_name == "Article"
        assert schema.singular_name == "article"
        assert schema.plural_name == "articles"


class TestEmptyResponses:
    """Tests for handling empty or minimal responses."""

    @respx.mock
    def test_empty_content_types(self, strapi_config: StrapiConfig) -> None:
        """Test handling empty content types response."""
        respx.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json={"data": []})
        )

        with SyncClient(strapi_config) as client:
            content_types = client.get_content_types()
            assert content_types == []

    @respx.mock
    def test_empty_components(self, strapi_config: StrapiConfig) -> None:
        """Test handling empty components response."""
        respx.get("http://localhost:1337/api/content-type-builder/components").mock(
            return_value=Response(200, json={"data": []})
        )

        with SyncClient(strapi_config) as client:
            components = client.get_components()
            assert components == []
