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

# Fixtures for ACTUAL Strapi v5 API responses (Issue #28)
# These match the real Strapi v5 response format where displayName, singularName,
# pluralName are at schema top level, NOT nested in schema.info


@pytest.fixture
def mock_actual_v5_content_types_response() -> dict:
    """Mock ACTUAL Strapi v5 response for get_content_types (Issue #28).

    This is the real format Strapi v5 returns, with displayName/singularName/pluralName
    at the schema top level, not nested in schema.info.
    """
    return {
        "data": [
            {
                "uid": "api::article.article",
                "apiID": "article",
                "schema": {
                    "displayName": "Article",  # At top level, NOT in info!
                    "singularName": "article",
                    "pluralName": "articles",
                    "kind": "collectionType",
                    "collectionName": "articles",
                    "attributes": {
                        "title": {"type": "string", "required": True},
                        "content": {"type": "richtext"},
                    },
                },
            },
            {
                "uid": "api::category.category",
                "apiID": "category",
                "schema": {
                    "displayName": "Category",
                    "singularName": "category",
                    "pluralName": "categories",
                    "kind": "collectionType",
                    "attributes": {
                        "name": {"type": "string", "required": True},
                    },
                },
            },
            {
                "uid": "plugin::users-permissions.user",
                "apiID": "user",
                "schema": {
                    "displayName": "User",
                    "singularName": "user",
                    "pluralName": "users",
                    "kind": "collectionType",
                    "attributes": {
                        "username": {"type": "string"},
                        "email": {"type": "email"},
                    },
                },
            },
        ]
    }


@pytest.fixture
def mock_actual_v5_components_response() -> dict:
    """Mock ACTUAL Strapi v5 response for get_components (Issue #28)."""
    return {
        "data": [
            {
                "uid": "shared.seo",
                "category": "shared",
                "schema": {
                    "displayName": "SEO",  # At top level, NOT in info!
                    "description": "SEO metadata",
                    "attributes": {
                        "metaTitle": {"type": "string"},
                        "metaDescription": {"type": "text"},
                    },
                },
            },
            {
                "uid": "blocks.hero",
                "category": "blocks",
                "schema": {
                    "displayName": "Hero Section",
                    "attributes": {
                        "title": {"type": "string"},
                        "subtitle": {"type": "string"},
                    },
                },
            },
        ]
    }


@pytest.fixture
def mock_actual_v5_single_content_type_response() -> dict:
    """Mock ACTUAL Strapi v5 response for get_content_type_schema (Issue #28)."""
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
                    "title": {"type": "string", "required": True},
                    "content": {"type": "richtext"},
                    "author": {
                        "type": "relation",
                        "relation": "manyToOne",
                        "target": "api::author.author",
                    },
                },
            },
        }
    }


# Fixtures for Strapi v5 mock responses with nested info (alternative format)
# These represent an alternative v5 format with info nested


@pytest.fixture
def mock_v5_content_types_response() -> dict:
    """Mock Strapi v5 response for get_content_types with nested schema."""
    return {
        "data": [
            {
                "uid": "api::article.article",
                "apiID": "article",
                "schema": {
                    "kind": "collectionType",
                    "collectionName": "articles",
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
                    "pluginOptions": {"i18n": {"localized": True}},
                },
            },
            {
                "uid": "api::category.category",
                "apiID": "category",
                "schema": {
                    "kind": "collectionType",
                    "collectionName": "categories",
                    "info": {
                        "displayName": "Category",
                        "singularName": "category",
                        "pluralName": "categories",
                    },
                    "attributes": {
                        "name": {"type": "string", "required": True},
                    },
                },
            },
            {
                "uid": "plugin::users-permissions.user",
                "apiID": "user",
                "schema": {
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
            },
        ]
    }


@pytest.fixture
def mock_v5_components_response() -> dict:
    """Mock Strapi v5 response for get_components with nested schema."""
    return {
        "data": [
            {
                "uid": "shared.seo",
                "category": "shared",
                "schema": {
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
            },
            {
                "uid": "blocks.hero",
                "category": "blocks",
                "schema": {
                    "info": {
                        "displayName": "Hero Section",
                    },
                    "attributes": {
                        "title": {"type": "string"},
                        "subtitle": {"type": "string"},
                        "image": {"type": "media"},
                    },
                },
            },
        ]
    }


@pytest.fixture
def mock_v5_single_content_type_response() -> dict:
    """Mock Strapi v5 response for get_content_type_schema with nested schema."""
    return {
        "data": {
            "uid": "api::article.article",
            "apiID": "article",
            "schema": {
                "kind": "collectionType",
                "collectionName": "articles",
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
                "pluginOptions": {"i18n": {"localized": True}},
            },
        }
    }


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


class TestSyncContentTypeBuilderV5:
    """Tests for SyncClient Content-Type Builder methods with Strapi v5 responses (Issue #25)."""

    @respx.mock
    def test_get_content_types_v5(
        self,
        strapi_config: StrapiConfig,
        mock_v5_content_types_response: dict,
    ) -> None:
        """Test listing content types with v5 nested schema format."""
        respx.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json=mock_v5_content_types_response)
        )

        with SyncClient(strapi_config) as client:
            content_types = client.get_content_types()

            # Should exclude plugin content types by default
            assert len(content_types) == 2
            assert all(isinstance(ct, ContentTypeListItem) for ct in content_types)
            assert all(ct.uid.startswith("api::") for ct in content_types)

            # Check first content type - should be normalized from v5 format
            article = content_types[0]
            assert article.uid == "api::article.article"
            assert article.kind == "collectionType"
            assert article.info.display_name == "Article"
            assert article.info.singular_name == "article"
            assert article.info.plural_name == "articles"
            assert "title" in article.attributes
            assert article.plugin_options == {"i18n": {"localized": True}}

    @respx.mock
    def test_get_content_types_v5_include_plugins(
        self,
        strapi_config: StrapiConfig,
        mock_v5_content_types_response: dict,
    ) -> None:
        """Test listing content types including plugins with v5 format."""
        respx.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json=mock_v5_content_types_response)
        )

        with SyncClient(strapi_config) as client:
            content_types = client.get_content_types(include_plugins=True)

            # Should include all content types
            assert len(content_types) == 3
            plugin_types = [ct for ct in content_types if ct.uid.startswith("plugin::")]
            assert len(plugin_types) == 1
            assert plugin_types[0].uid == "plugin::users-permissions.user"

    @respx.mock
    def test_get_components_v5(
        self,
        strapi_config: StrapiConfig,
        mock_v5_components_response: dict,
    ) -> None:
        """Test listing components with v5 nested schema format."""
        respx.get("http://localhost:1337/api/content-type-builder/components").mock(
            return_value=Response(200, json=mock_v5_components_response)
        )

        with SyncClient(strapi_config) as client:
            components = client.get_components()

            assert len(components) == 2
            assert all(isinstance(c, ComponentListItem) for c in components)

            # Check first component - should be normalized from v5 format
            seo = components[0]
            assert seo.uid == "shared.seo"
            assert seo.category == "shared"
            assert seo.info.display_name == "SEO"
            assert "metaTitle" in seo.attributes

    @respx.mock
    def test_get_content_type_schema_v5(
        self,
        strapi_config: StrapiConfig,
        mock_v5_single_content_type_response: dict,
    ) -> None:
        """Test getting single content type schema with v5 format."""
        uid = "api::article.article"
        respx.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
            return_value=Response(200, json=mock_v5_single_content_type_response)
        )

        with SyncClient(strapi_config) as client:
            schema = client.get_content_type_schema(uid)

            assert isinstance(schema, CTBContentTypeSchema)
            assert schema.uid == uid
            assert schema.kind == "collectionType"
            assert schema.display_name == "Article"
            assert schema.singular_name == "article"
            assert schema.plural_name == "articles"

            # Test helper methods work with v5 normalized data
            assert schema.get_field_type("title") == "string"
            assert schema.is_relation_field("author") is True
            assert schema.is_component_field("seo") is True
            assert schema.get_relation_target("author") == "api::author.author"
            assert schema.get_component_uid("seo") == "shared.seo"


class TestAsyncContentTypeBuilderV5:
    """Tests for AsyncClient Content-Type Builder methods with Strapi v5 responses (Issue #25)."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_content_types_v5(
        self,
        strapi_config: StrapiConfig,
        mock_v5_content_types_response: dict,
    ) -> None:
        """Test listing content types with v5 nested schema format."""
        respx.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json=mock_v5_content_types_response)
        )

        async with AsyncClient(strapi_config) as client:
            content_types = await client.get_content_types()

            # Should exclude plugin content types by default
            assert len(content_types) == 2
            assert all(isinstance(ct, ContentTypeListItem) for ct in content_types)

            # Check normalization worked
            article = content_types[0]
            assert article.uid == "api::article.article"
            assert article.info.display_name == "Article"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_components_v5(
        self,
        strapi_config: StrapiConfig,
        mock_v5_components_response: dict,
    ) -> None:
        """Test listing components with v5 nested schema format."""
        respx.get("http://localhost:1337/api/content-type-builder/components").mock(
            return_value=Response(200, json=mock_v5_components_response)
        )

        async with AsyncClient(strapi_config) as client:
            components = await client.get_components()

            assert len(components) == 2
            assert all(isinstance(c, ComponentListItem) for c in components)

            # Check normalization worked
            seo = components[0]
            assert seo.uid == "shared.seo"
            assert seo.category == "shared"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_content_type_schema_v5(
        self,
        strapi_config: StrapiConfig,
        mock_v5_single_content_type_response: dict,
    ) -> None:
        """Test getting single content type schema with v5 format."""
        uid = "api::article.article"
        respx.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
            return_value=Response(200, json=mock_v5_single_content_type_response)
        )

        async with AsyncClient(strapi_config) as client:
            schema = await client.get_content_type_schema(uid)

            assert isinstance(schema, CTBContentTypeSchema)
            assert schema.uid == uid
            assert schema.display_name == "Article"


class TestV5NormalizationHelpers:
    """Tests for v5 normalization helper methods."""

    def test_normalize_content_type_item_v5_format(self, strapi_config: StrapiConfig) -> None:
        """Test normalizing v5 content type item with nested schema."""
        with SyncClient(strapi_config) as client:
            v5_item = {
                "uid": "api::article.article",
                "apiID": "article",
                "schema": {
                    "kind": "collectionType",
                    "info": {"displayName": "Article"},
                    "attributes": {"title": {"type": "string"}},
                    "pluginOptions": {"i18n": {"localized": True}},
                },
            }

            normalized = client._normalize_content_type_item(v5_item)

            assert normalized["uid"] == "api::article.article"
            assert normalized["kind"] == "collectionType"
            assert normalized["info"] == {"displayName": "Article"}
            assert normalized["attributes"] == {"title": {"type": "string"}}
            assert normalized["pluginOptions"] == {"i18n": {"localized": True}}
            # apiID should not be in normalized output
            assert "apiID" not in normalized
            assert "schema" not in normalized

    def test_normalize_content_type_item_v4_format(self, strapi_config: StrapiConfig) -> None:
        """Test normalizing v4 content type item (passthrough)."""
        with SyncClient(strapi_config) as client:
            v4_item = {
                "uid": "api::article.article",
                "kind": "collectionType",
                "info": {"displayName": "Article"},
                "attributes": {"title": {"type": "string"}},
            }

            normalized = client._normalize_content_type_item(v4_item)

            # Should be unchanged
            assert normalized == v4_item

    def test_normalize_component_item_v5_format(self, strapi_config: StrapiConfig) -> None:
        """Test normalizing v5 component item with nested schema."""
        with SyncClient(strapi_config) as client:
            v5_item = {
                "uid": "shared.seo",
                "category": "shared",
                "schema": {
                    "info": {"displayName": "SEO"},
                    "attributes": {"metaTitle": {"type": "string"}},
                },
            }

            normalized = client._normalize_component_item(v5_item)

            assert normalized["uid"] == "shared.seo"
            assert normalized["category"] == "shared"
            assert normalized["info"] == {"displayName": "SEO"}
            assert normalized["attributes"] == {"metaTitle": {"type": "string"}}
            assert "schema" not in normalized

    def test_normalize_component_item_v4_format(self, strapi_config: StrapiConfig) -> None:
        """Test normalizing v4 component item (passthrough)."""
        with SyncClient(strapi_config) as client:
            v4_item = {
                "uid": "shared.seo",
                "category": "shared",
                "info": {"displayName": "SEO"},
                "attributes": {"metaTitle": {"type": "string"}},
            }

            normalized = client._normalize_component_item(v4_item)

            # Should be unchanged
            assert normalized == v4_item


class TestActualV5Format:
    """Tests for ACTUAL Strapi v5 API format (Issue #28).

    Strapi v5 places displayName, singularName, pluralName at schema top level,
    NOT nested in schema.info. This class tests that the fix correctly handles
    this real-world format.
    """

    @respx.mock
    def test_get_content_types_actual_v5(
        self,
        strapi_config: StrapiConfig,
        mock_actual_v5_content_types_response: dict,
    ) -> None:
        """Test listing content types with actual v5 format (Issue #28)."""
        respx.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json=mock_actual_v5_content_types_response)
        )

        with SyncClient(strapi_config) as client:
            content_types = client.get_content_types()

            # Should exclude plugin content types by default
            assert len(content_types) == 2
            assert all(isinstance(ct, ContentTypeListItem) for ct in content_types)
            assert all(ct.uid.startswith("api::") for ct in content_types)

            # Check first content type - should correctly extract info from flat schema
            article = content_types[0]
            assert article.uid == "api::article.article"
            assert article.kind == "collectionType"
            # These should be extracted from schema top level, not schema.info
            assert article.info.display_name == "Article"
            assert article.info.singular_name == "article"
            assert article.info.plural_name == "articles"
            assert "title" in article.attributes

    @respx.mock
    def test_get_content_types_actual_v5_include_plugins(
        self,
        strapi_config: StrapiConfig,
        mock_actual_v5_content_types_response: dict,
    ) -> None:
        """Test listing content types including plugins with actual v5 format."""
        respx.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json=mock_actual_v5_content_types_response)
        )

        with SyncClient(strapi_config) as client:
            content_types = client.get_content_types(include_plugins=True)

            assert len(content_types) == 3
            plugin_types = [ct for ct in content_types if ct.uid.startswith("plugin::")]
            assert len(plugin_types) == 1
            assert plugin_types[0].uid == "plugin::users-permissions.user"
            # Verify info is correctly extracted
            assert plugin_types[0].info.display_name == "User"

    @respx.mock
    def test_get_components_actual_v5(
        self,
        strapi_config: StrapiConfig,
        mock_actual_v5_components_response: dict,
    ) -> None:
        """Test listing components with actual v5 format (Issue #28)."""
        respx.get("http://localhost:1337/api/content-type-builder/components").mock(
            return_value=Response(200, json=mock_actual_v5_components_response)
        )

        with SyncClient(strapi_config) as client:
            components = client.get_components()

            assert len(components) == 2
            assert all(isinstance(c, ComponentListItem) for c in components)

            # Check first component - should correctly extract info from flat schema
            seo = components[0]
            assert seo.uid == "shared.seo"
            assert seo.category == "shared"
            assert seo.info.display_name == "SEO"
            assert "metaTitle" in seo.attributes

    @respx.mock
    def test_get_content_type_schema_actual_v5(
        self,
        strapi_config: StrapiConfig,
        mock_actual_v5_single_content_type_response: dict,
    ) -> None:
        """Test getting single content type schema with actual v5 format (Issue #28)."""
        uid = "api::article.article"
        respx.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
            return_value=Response(200, json=mock_actual_v5_single_content_type_response)
        )

        with SyncClient(strapi_config) as client:
            schema = client.get_content_type_schema(uid)

            assert isinstance(schema, CTBContentTypeSchema)
            assert schema.uid == uid
            assert schema.kind == "collectionType"
            # These should be extracted from schema top level
            assert schema.display_name == "Article"
            assert schema.singular_name == "article"
            assert schema.plural_name == "articles"

            # Test helper methods work
            assert schema.get_field_type("title") == "string"
            assert schema.is_relation_field("author") is True
            assert schema.get_relation_target("author") == "api::author.author"

    def test_normalize_content_type_item_actual_v5_format(
        self, strapi_config: StrapiConfig
    ) -> None:
        """Test normalizing actual v5 content type item with flat schema (Issue #28)."""
        with SyncClient(strapi_config) as client:
            # This is the ACTUAL v5 format - no nested info!
            actual_v5_item = {
                "uid": "api::article.article",
                "apiID": "article",
                "schema": {
                    "displayName": "Article",  # At top level!
                    "singularName": "article",
                    "pluralName": "articles",
                    "kind": "collectionType",
                    "attributes": {"title": {"type": "string"}},
                },
            }

            normalized = client._normalize_content_type_item(actual_v5_item)

            assert normalized["uid"] == "api::article.article"
            assert normalized["kind"] == "collectionType"
            # Info should be extracted from flat schema properties
            assert normalized["info"]["displayName"] == "Article"
            assert normalized["info"]["singularName"] == "article"
            assert normalized["info"]["pluralName"] == "articles"
            assert normalized["attributes"] == {"title": {"type": "string"}}
            assert "apiID" not in normalized
            assert "schema" not in normalized

    def test_normalize_component_item_actual_v5_format(self, strapi_config: StrapiConfig) -> None:
        """Test normalizing actual v5 component item with flat schema (Issue #28)."""
        with SyncClient(strapi_config) as client:
            # This is the ACTUAL v5 format - no nested info!
            actual_v5_item = {
                "uid": "shared.seo",
                "category": "shared",
                "schema": {
                    "displayName": "SEO",  # At top level!
                    "description": "SEO metadata",
                    "attributes": {"metaTitle": {"type": "string"}},
                },
            }

            normalized = client._normalize_component_item(actual_v5_item)

            assert normalized["uid"] == "shared.seo"
            assert normalized["category"] == "shared"
            # Info should be extracted from flat schema properties
            assert normalized["info"]["displayName"] == "SEO"
            assert normalized["info"]["description"] == "SEO metadata"
            assert normalized["attributes"] == {"metaTitle": {"type": "string"}}
            assert "schema" not in normalized

    def test_extract_info_from_schema_flat_format(self, strapi_config: StrapiConfig) -> None:
        """Test _extract_info_from_schema with flat v5 format."""
        with SyncClient(strapi_config) as client:
            flat_schema = {
                "displayName": "Article",
                "singularName": "article",
                "pluralName": "articles",
                "description": "Blog articles",
                "kind": "collectionType",
                "attributes": {},
            }

            info = client._extract_info_from_schema(flat_schema)

            assert info["displayName"] == "Article"
            assert info["singularName"] == "article"
            assert info["pluralName"] == "articles"
            assert info["description"] == "Blog articles"

    def test_extract_info_from_schema_nested_format(self, strapi_config: StrapiConfig) -> None:
        """Test _extract_info_from_schema with nested v5 format (should still work)."""
        with SyncClient(strapi_config) as client:
            nested_schema = {
                "info": {
                    "displayName": "Article",
                    "singularName": "article",
                    "pluralName": "articles",
                },
                "kind": "collectionType",
                "attributes": {},
            }

            info = client._extract_info_from_schema(nested_schema)

            # Should use nested info when present
            assert info["displayName"] == "Article"
            assert info["singularName"] == "article"
            assert info["pluralName"] == "articles"

    def test_extract_info_from_schema_empty(self, strapi_config: StrapiConfig) -> None:
        """Test _extract_info_from_schema with empty schema."""
        with SyncClient(strapi_config) as client:
            empty_schema: dict = {}

            info = client._extract_info_from_schema(empty_schema)

            assert info["displayName"] == ""
            assert info["singularName"] is None
            assert info["pluralName"] is None


class TestActualV5FormatAsync:
    """Async tests for ACTUAL Strapi v5 API format (Issue #28)."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_content_types_actual_v5(
        self,
        strapi_config: StrapiConfig,
        mock_actual_v5_content_types_response: dict,
    ) -> None:
        """Test listing content types with actual v5 format (Issue #28)."""
        respx.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json=mock_actual_v5_content_types_response)
        )

        async with AsyncClient(strapi_config) as client:
            content_types = await client.get_content_types()

            assert len(content_types) == 2
            article = content_types[0]
            assert article.info.display_name == "Article"
            assert article.info.singular_name == "article"
            assert article.info.plural_name == "articles"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_components_actual_v5(
        self,
        strapi_config: StrapiConfig,
        mock_actual_v5_components_response: dict,
    ) -> None:
        """Test listing components with actual v5 format (Issue #28)."""
        respx.get("http://localhost:1337/api/content-type-builder/components").mock(
            return_value=Response(200, json=mock_actual_v5_components_response)
        )

        async with AsyncClient(strapi_config) as client:
            components = await client.get_components()

            assert len(components) == 2
            seo = components[0]
            assert seo.info.display_name == "SEO"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_content_type_schema_actual_v5(
        self,
        strapi_config: StrapiConfig,
        mock_actual_v5_single_content_type_response: dict,
    ) -> None:
        """Test getting single content type schema with actual v5 format (Issue #28)."""
        uid = "api::article.article"
        respx.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
            return_value=Response(200, json=mock_actual_v5_single_content_type_response)
        )

        async with AsyncClient(strapi_config) as client:
            schema = await client.get_content_type_schema(uid)

            assert schema.display_name == "Article"
            assert schema.singular_name == "article"
            assert schema.plural_name == "articles"
