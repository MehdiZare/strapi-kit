"""Tests for Content-Type Builder API methods."""

from typing import Any

import pytest
import respx
from httpx import Response

from strapi_kit import AsyncClient, StrapiConfig, SyncClient
from strapi_kit.exceptions import NotFoundError, ValidationError
from strapi_kit.models.content_type import (
    ComponentListItem,
    ContentTypeListItem,
)
from strapi_kit.models.content_type import (
    ContentTypeSchema as CTBContentTypeSchema,
)

_MISSING = object()


def make_v5_content_type_item(
    *,
    uid: str = "api::article.article",
    display_name: str = "Article",
    schema_draft_and_publish: object = _MISSING,
    options_draft_and_publish: object = _MISSING,
    extra_options: dict[str, Any] | None = None,
    top_level_draft_and_publish: object = _MISSING,
    include_published_at: bool = False,
) -> dict[str, Any]:
    """Build an actual Strapi v5 CTB content-type item (Issue #45)."""
    attributes: dict[str, Any] = {"title": {"type": "string", "required": True}}
    if include_published_at:
        attributes["publishedAt"] = {"type": "datetime"}

    schema: dict[str, Any] = {
        "displayName": display_name,
        "singularName": "article",
        "pluralName": "articles",
        "kind": "collectionType",
        "collectionName": "articles",
        "attributes": attributes,
    }
    if schema_draft_and_publish is not _MISSING:
        schema["draftAndPublish"] = schema_draft_and_publish

    options: dict[str, Any] = dict(extra_options or {})
    if options_draft_and_publish is not _MISSING:
        options["draftAndPublish"] = options_draft_and_publish
    if options:
        schema["options"] = options

    item: dict[str, Any] = {
        "uid": uid,
        "apiID": "article",
        "schema": schema,
    }
    if top_level_draft_and_publish is not _MISSING:
        item["draftAndPublish"] = top_level_draft_and_publish
    return item


V5_DRAFT_AND_PUBLISH_WIRE_SHAPES: list[tuple[str, dict[str, Any], bool | None]] = [
    ("schema_only", {"schema_draft_and_publish": True}, True),
    ("options_only", {"options_draft_and_publish": True}, True),
    (
        "both",
        {"schema_draft_and_publish": True, "options_draft_and_publish": True},
        True,
    ),
    ("absent", {}, None),
]

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

    @pytest.mark.respx
    def test_get_content_types(
        self,
        strapi_config: StrapiConfig,
        mock_content_types_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test listing content types without plugins."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
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
            assert article.draft_and_publish is None
            assert article.options is None

    @pytest.mark.respx
    def test_get_content_types_include_plugins(
        self,
        strapi_config: StrapiConfig,
        mock_content_types_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test listing content types including plugins."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json=mock_content_types_response)
        )

        with SyncClient(strapi_config) as client:
            content_types = client.get_content_types(include_plugins=True)

            # Should include all content types
            assert len(content_types) == 3
            plugin_types = [ct for ct in content_types if ct.uid.startswith("plugin::")]
            assert len(plugin_types) == 1
            assert plugin_types[0].uid == "plugin::users-permissions.user"

    @pytest.mark.respx
    def test_get_components(
        self,
        strapi_config: StrapiConfig,
        mock_components_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test listing components."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/components").mock(
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

    @pytest.mark.respx
    def test_get_content_type_schema(
        self,
        strapi_config: StrapiConfig,
        mock_single_content_type_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test getting single content type schema."""
        uid = "api::article.article"
        respx_mock.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
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
            assert schema.draft_and_publish is True
            assert schema.options == {"draftAndPublish": True}

    @pytest.mark.respx
    def test_get_content_type_schema_helper_methods(
        self,
        strapi_config: StrapiConfig,
        mock_single_content_type_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test schema helper methods."""
        uid = "api::article.article"
        respx_mock.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
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

    @pytest.mark.respx
    def test_get_content_type_schema_not_found(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
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
        respx_mock.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
            return_value=Response(404, json=error_response)
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError):
                client.get_content_type_schema(uid)


class TestAsyncContentTypeBuilder:
    """Tests for AsyncClient Content-Type Builder methods."""

    @pytest.mark.respx
    async def test_get_content_types(
        self,
        strapi_config: StrapiConfig,
        mock_content_types_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test listing content types without plugins."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json=mock_content_types_response)
        )

        async with AsyncClient(strapi_config) as client:
            content_types = await client.get_content_types()

            # Should exclude plugin content types by default
            assert len(content_types) == 2
            assert all(isinstance(ct, ContentTypeListItem) for ct in content_types)

    @pytest.mark.respx
    async def test_get_content_types_include_plugins(
        self,
        strapi_config: StrapiConfig,
        mock_content_types_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test listing content types including plugins."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json=mock_content_types_response)
        )

        async with AsyncClient(strapi_config) as client:
            content_types = await client.get_content_types(include_plugins=True)

            assert len(content_types) == 3

    @pytest.mark.respx
    async def test_get_components(
        self,
        strapi_config: StrapiConfig,
        mock_components_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test listing components."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/components").mock(
            return_value=Response(200, json=mock_components_response)
        )

        async with AsyncClient(strapi_config) as client:
            components = await client.get_components()

            assert len(components) == 2
            assert all(isinstance(c, ComponentListItem) for c in components)

    @pytest.mark.respx
    async def test_get_content_type_schema(
        self,
        strapi_config: StrapiConfig,
        mock_single_content_type_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test getting single content type schema."""
        uid = "api::article.article"
        respx_mock.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
            return_value=Response(200, json=mock_single_content_type_response)
        )

        async with AsyncClient(strapi_config) as client:
            schema = await client.get_content_type_schema(uid)

            assert isinstance(schema, CTBContentTypeSchema)
            assert schema.uid == uid
            assert schema.display_name == "Article"

    @pytest.mark.respx
    async def test_get_content_type_schema_not_found(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
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
        respx_mock.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
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
        assert item.draft_and_publish is None
        assert item.options is None

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

    @pytest.mark.respx
    def test_empty_content_types(
        self, strapi_config: StrapiConfig, respx_mock: respx.Router
    ) -> None:
        """Test handling empty content types response."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json={"data": []})
        )

        with SyncClient(strapi_config) as client:
            content_types = client.get_content_types()
            assert content_types == []

    @pytest.mark.respx
    def test_empty_components(self, strapi_config: StrapiConfig, respx_mock: respx.Router) -> None:
        """Test handling empty components response."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/components").mock(
            return_value=Response(200, json={"data": []})
        )

        with SyncClient(strapi_config) as client:
            components = client.get_components()
            assert components == []


class TestSyncContentTypeBuilderV5:
    """Tests for SyncClient Content-Type Builder methods with Strapi v5 responses (Issue #25)."""

    @pytest.mark.respx
    def test_get_content_types_v5(
        self,
        strapi_config: StrapiConfig,
        mock_v5_content_types_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test listing content types with v5 nested schema format."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
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
            assert article.draft_and_publish is None
            assert article.options is None

    @pytest.mark.respx
    def test_get_content_types_v5_include_plugins(
        self,
        strapi_config: StrapiConfig,
        mock_v5_content_types_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test listing content types including plugins with v5 format."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json=mock_v5_content_types_response)
        )

        with SyncClient(strapi_config) as client:
            content_types = client.get_content_types(include_plugins=True)

            # Should include all content types
            assert len(content_types) == 3
            plugin_types = [ct for ct in content_types if ct.uid.startswith("plugin::")]
            assert len(plugin_types) == 1
            assert plugin_types[0].uid == "plugin::users-permissions.user"

    @pytest.mark.respx
    def test_get_components_v5(
        self,
        strapi_config: StrapiConfig,
        mock_v5_components_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test listing components with v5 nested schema format."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/components").mock(
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

    @pytest.mark.respx
    def test_get_content_type_schema_v5(
        self,
        strapi_config: StrapiConfig,
        mock_v5_single_content_type_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test getting single content type schema with v5 format."""
        uid = "api::article.article"
        respx_mock.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
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
            assert schema.draft_and_publish is True
            assert schema.options == {"draftAndPublish": True}

            # Test helper methods work with v5 normalized data
            assert schema.get_field_type("title") == "string"
            assert schema.is_relation_field("author") is True
            assert schema.is_component_field("seo") is True
            assert schema.get_relation_target("author") == "api::author.author"
            assert schema.get_component_uid("seo") == "shared.seo"


class TestAsyncContentTypeBuilderV5:
    """Tests for AsyncClient Content-Type Builder methods with Strapi v5 responses (Issue #25)."""

    @pytest.mark.respx
    async def test_get_content_types_v5(
        self,
        strapi_config: StrapiConfig,
        mock_v5_content_types_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test listing content types with v5 nested schema format."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
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

    @pytest.mark.respx
    async def test_get_components_v5(
        self,
        strapi_config: StrapiConfig,
        mock_v5_components_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test listing components with v5 nested schema format."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/components").mock(
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

    @pytest.mark.respx
    async def test_get_content_type_schema_v5(
        self,
        strapi_config: StrapiConfig,
        mock_v5_single_content_type_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test getting single content type schema with v5 format."""
        uid = "api::article.article"
        respx_mock.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
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
            assert normalized["draftAndPublish"] is None
            assert normalized["options"] is None

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

    @pytest.mark.respx
    def test_get_content_types_actual_v5(
        self,
        strapi_config: StrapiConfig,
        mock_actual_v5_content_types_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test listing content types with actual v5 format (Issue #28)."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
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

    @pytest.mark.respx
    def test_get_content_types_actual_v5_include_plugins(
        self,
        strapi_config: StrapiConfig,
        mock_actual_v5_content_types_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test listing content types including plugins with actual v5 format."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
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

    @pytest.mark.respx
    def test_get_components_actual_v5(
        self,
        strapi_config: StrapiConfig,
        mock_actual_v5_components_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test listing components with actual v5 format (Issue #28)."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/components").mock(
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

    @pytest.mark.respx
    def test_get_content_type_schema_actual_v5(
        self,
        strapi_config: StrapiConfig,
        mock_actual_v5_single_content_type_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test getting single content type schema with actual v5 format (Issue #28)."""
        uid = "api::article.article"
        respx_mock.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
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
            assert schema.draft_and_publish is None
            assert schema.options is None

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
            assert normalized["draftAndPublish"] is None
            assert normalized["options"] is None

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

    def test_extract_info_from_schema_flat_format(self) -> None:
        """Test extract_info_from_schema with flat v5 format."""
        from strapi_kit.utils.schema import extract_info_from_schema

        flat_schema = {
            "displayName": "Article",
            "singularName": "article",
            "pluralName": "articles",
            "description": "Blog articles",
            "kind": "collectionType",
            "attributes": {},
        }

        info = extract_info_from_schema(flat_schema)

        assert info["displayName"] == "Article"
        assert info["singularName"] == "article"
        assert info["pluralName"] == "articles"
        assert info["description"] == "Blog articles"

    def test_extract_info_from_schema_nested_format(self) -> None:
        """Test extract_info_from_schema with nested v5 format (should still work)."""
        from strapi_kit.utils.schema import extract_info_from_schema

        nested_schema = {
            "info": {
                "displayName": "Article",
                "singularName": "article",
                "pluralName": "articles",
            },
            "kind": "collectionType",
            "attributes": {},
        }

        info = extract_info_from_schema(nested_schema)

        # Should use nested info when present
        assert info["displayName"] == "Article"
        assert info["singularName"] == "article"
        assert info["pluralName"] == "articles"

    def test_extract_info_from_schema_empty(self) -> None:
        """Test extract_info_from_schema with empty schema."""
        from strapi_kit.utils.schema import extract_info_from_schema

        empty_schema: dict = {}

        info = extract_info_from_schema(empty_schema)

        assert info["displayName"] == ""
        assert info["singularName"] is None
        assert info["pluralName"] is None


class TestActualV5FormatAsync:
    """Async tests for ACTUAL Strapi v5 API format (Issue #28)."""

    @pytest.mark.respx
    async def test_get_content_types_actual_v5(
        self,
        strapi_config: StrapiConfig,
        mock_actual_v5_content_types_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test listing content types with actual v5 format (Issue #28)."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json=mock_actual_v5_content_types_response)
        )

        async with AsyncClient(strapi_config) as client:
            content_types = await client.get_content_types()

            assert len(content_types) == 2
            article = content_types[0]
            assert article.info.display_name == "Article"
            assert article.info.singular_name == "article"
            assert article.info.plural_name == "articles"

    @pytest.mark.respx
    async def test_get_components_actual_v5(
        self,
        strapi_config: StrapiConfig,
        mock_actual_v5_components_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test listing components with actual v5 format (Issue #28)."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/components").mock(
            return_value=Response(200, json=mock_actual_v5_components_response)
        )

        async with AsyncClient(strapi_config) as client:
            components = await client.get_components()

            assert len(components) == 2
            seo = components[0]
            assert seo.info.display_name == "SEO"

    @pytest.mark.respx
    async def test_get_content_type_schema_actual_v5(
        self,
        strapi_config: StrapiConfig,
        mock_actual_v5_single_content_type_response: dict,
        respx_mock: respx.Router,
    ) -> None:
        """Test getting single content type schema with actual v5 format (Issue #28)."""
        uid = "api::article.article"
        respx_mock.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
            return_value=Response(200, json=mock_actual_v5_single_content_type_response)
        )

        async with AsyncClient(strapi_config) as client:
            schema = await client.get_content_type_schema(uid)

            assert schema.display_name == "Article"
            assert schema.singular_name == "article"
            assert schema.plural_name == "articles"
            assert schema.draft_and_publish is None
            assert schema.options is None


class TestDraftAndPublishExtraction:
    """True / False / None pins for Draft & Publish (Issue #45)."""

    def test_extract_true_from_each_source(self) -> None:
        """True if any known location has a boolean True."""
        from strapi_kit.utils.schema import extract_draft_and_publish

        assert extract_draft_and_publish({"draftAndPublish": True}) is True
        assert extract_draft_and_publish({"draft_and_publish": True}) is True
        assert extract_draft_and_publish({"options": {"draftAndPublish": True}}) is True
        assert extract_draft_and_publish({"options": {"draft_and_publish": True}}) is True
        assert extract_draft_and_publish({"schema": {"draftAndPublish": True}}) is True
        assert extract_draft_and_publish({"schema": {"options": {"draftAndPublish": True}}}) is True

    def test_extract_false_only_when_boolean_false_seen(self) -> None:
        """False only when a boolean False was seen and no True was seen."""
        from strapi_kit.utils.schema import extract_draft_and_publish

        assert extract_draft_and_publish({"draftAndPublish": False}) is False
        assert extract_draft_and_publish({"options": {"draftAndPublish": False}}) is False
        assert extract_draft_and_publish({"schema": {"draftAndPublish": False}}) is False
        assert (
            extract_draft_and_publish({"schema": {"options": {"draftAndPublish": False}}}) is False
        )

    def test_extract_none_when_flag_absent(self) -> None:
        """Absence is None, not False."""
        from strapi_kit.utils.schema import extract_draft_and_publish

        assert extract_draft_and_publish({}) is None
        assert extract_draft_and_publish({"options": {}}) is None
        assert extract_draft_and_publish({"schema": {"kind": "collectionType"}}) is None
        assert extract_draft_and_publish({"schema": {"options": {"other": True}}}) is None

    def test_extract_does_not_guess_from_published_at(self) -> None:
        """publishedAt must not imply Draft & Publish."""
        from strapi_kit.utils.schema import extract_draft_and_publish

        item = {
            "schema": {
                "attributes": {"publishedAt": {"type": "datetime"}},
            }
        }
        assert extract_draft_and_publish(item) is None

    def test_extract_ignores_non_boolean_values(self) -> None:
        """Only boolean True/False count as a declared flag."""
        from strapi_kit.utils.schema import extract_draft_and_publish

        assert extract_draft_and_publish({"draftAndPublish": "yes"}) is None
        assert extract_draft_and_publish({"draftAndPublish": 1}) is None
        assert extract_draft_and_publish({"draftAndPublish": None}) is None

    def test_true_wins_over_false(self) -> None:
        """Any True wins even if another location is False."""
        from strapi_kit.utils.schema import extract_draft_and_publish

        item = {
            "schema": {"draftAndPublish": True},
            "options": {"draftAndPublish": False},
        }
        assert extract_draft_and_publish(item) is True

    def test_extract_options_merges_schema_over_top_level(self) -> None:
        """Nested schema.options wins on key conflicts; other keys are kept."""
        from strapi_kit.utils.schema import extract_content_type_options

        item = {
            "options": {"draftAndPublish": True, "foo": 1},
            "schema": {"options": {"draftAndPublish": False, "bar": 2}},
        }
        assert extract_content_type_options(item) == {
            "draftAndPublish": False,
            "foo": 1,
            "bar": 2,
        }

    def test_apply_sources_merges_options_when_top_level_exists(self) -> None:
        """Direct model_validate still merges schema.options into options."""
        from strapi_kit.utils.schema import apply_draft_and_publish_sources

        payload = apply_draft_and_publish_sources(
            {
                "uid": "api::article.article",
                "info": {"displayName": "Article"},
                "options": {"foo": 1},
                "schema": {"options": {"draftAndPublish": True, "bar": 2}},
            }
        )
        assert payload["draftAndPublish"] is True
        assert payload["options"] == {"foo": 1, "draftAndPublish": True, "bar": 2}

    def test_apply_sources_leaves_non_dict_unchanged(self) -> None:
        """Non-dict payloads are returned as-is."""
        from strapi_kit.utils.schema import apply_draft_and_publish_sources

        assert apply_draft_and_publish_sources(None) is None
        assert apply_draft_and_publish_sources(["x"]) == ["x"]

    def test_list_item_merges_options_layers(self) -> None:
        """ContentTypeListItem merges top-level and schema.options."""
        item = ContentTypeListItem.model_validate(
            {
                "uid": "api::article.article",
                "info": {"displayName": "Article"},
                "options": {"populateCreatorFields": True},
                "schema": {"options": {"draftAndPublish": False}},
            }
        )
        assert item.draft_and_publish is False
        assert item.options == {
            "populateCreatorFields": True,
            "draftAndPublish": False,
        }

    def test_list_item_none_by_default(self) -> None:
        """ContentTypeListItem defaults draft_and_publish to None."""
        item = ContentTypeListItem.model_validate(
            {"uid": "api::page.page", "info": {"displayName": "Page"}}
        )
        assert item.draft_and_publish is None
        assert item.options is None

    def test_list_item_false_from_options(self) -> None:
        """Boolean False on options is not treated as missing."""
        item = ContentTypeListItem.model_validate(
            {
                "uid": "api::page.page",
                "info": {"displayName": "Page"},
                "options": {"draftAndPublish": False, "populateCreatorFields": True},
            }
        )
        assert item.draft_and_publish is False
        assert item.options == {"draftAndPublish": False, "populateCreatorFields": True}

    def test_list_item_true_from_schema_source(self) -> None:
        """Nested schema.draftAndPublish is visible on the list item."""
        item = ContentTypeListItem.model_validate(
            {
                "uid": "api::article.article",
                "info": {"displayName": "Article"},
                "schema": {"draftAndPublish": True},
            }
        )
        assert item.draft_and_publish is True

    def test_schema_model_none_by_default(self) -> None:
        """ContentTypeSchema defaults draft_and_publish to None."""
        schema = CTBContentTypeSchema.model_validate(
            {
                "uid": "api::article.article",
                "info": {"displayName": "Article"},
                "attributes": {},
            }
        )
        assert schema.draft_and_publish is None
        assert schema.options is None

    def test_schema_model_false_pin(self) -> None:
        """ContentTypeSchema preserves explicit False."""
        schema = CTBContentTypeSchema.model_validate(
            {
                "uid": "api::article.article",
                "info": {"displayName": "Article"},
                "options": {"draftAndPublish": False},
            }
        )
        assert schema.draft_and_publish is False


class TestDraftAndPublishWireShapes:
    """Four live v5 wire shapes on list + single-schema (Issue #45)."""

    @pytest.mark.respx
    @pytest.mark.parametrize(
        ("shape", "kwargs", "expected"),
        V5_DRAFT_AND_PUBLISH_WIRE_SHAPES,
    )
    def test_get_content_types_wire_shapes(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
        shape: str,
        kwargs: dict[str, Any],
        expected: bool | None,
    ) -> None:
        """get_content_types populates D&P from each v5 wire location."""
        item = make_v5_content_type_item(**kwargs)
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json={"data": [item]})
        )

        with SyncClient(strapi_config) as client:
            content_types = client.get_content_types()

        assert len(content_types) == 1
        article = content_types[0]
        assert article.uid == "api::article.article"
        assert article.info.display_name == "Article"
        assert article.draft_and_publish is expected

        if shape == "absent":
            assert article.options is None
        else:
            assert article.options is not None
            assert article.options["draftAndPublish"] is True

    @pytest.mark.respx
    @pytest.mark.parametrize(
        ("shape", "kwargs", "expected"),
        V5_DRAFT_AND_PUBLISH_WIRE_SHAPES,
    )
    def test_get_content_type_schema_wire_shapes(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
        shape: str,
        kwargs: dict[str, Any],
        expected: bool | None,
    ) -> None:
        """get_content_type_schema populates D&P from each v5 wire location."""
        item = make_v5_content_type_item(**kwargs)
        uid = item["uid"]
        respx_mock.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
            return_value=Response(200, json={"data": item})
        )

        with SyncClient(strapi_config) as client:
            schema = client.get_content_type_schema(uid)

        assert schema.uid == uid
        assert schema.display_name == "Article"
        assert schema.draft_and_publish is expected

        if shape == "absent":
            assert schema.options is None
        else:
            assert schema.options is not None
            assert schema.options["draftAndPublish"] is True

    @pytest.mark.respx
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"schema_draft_and_publish": False},
            {"options_draft_and_publish": False},
            {"schema_draft_and_publish": False, "options_draft_and_publish": False},
            {"top_level_draft_and_publish": False},
        ],
    )
    def test_get_content_types_false_pins(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
        kwargs: dict[str, Any],
    ) -> None:
        """Explicit False on list items is not treated as missing."""
        item = make_v5_content_type_item(**kwargs)
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json={"data": [item]})
        )

        with SyncClient(strapi_config) as client:
            content_types = client.get_content_types()

        assert content_types[0].draft_and_publish is False

    @pytest.mark.respx
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"schema_draft_and_publish": False},
            {"options_draft_and_publish": False},
            {"schema_draft_and_publish": False, "options_draft_and_publish": False},
            {"top_level_draft_and_publish": False},
        ],
    )
    def test_get_content_type_schema_false_pins(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
        kwargs: dict[str, Any],
    ) -> None:
        """Explicit False on single-schema is not treated as missing."""
        item = make_v5_content_type_item(**kwargs)
        uid = item["uid"]
        respx_mock.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
            return_value=Response(200, json={"data": item})
        )

        with SyncClient(strapi_config) as client:
            schema = client.get_content_type_schema(uid)

        assert schema.draft_and_publish is False

    @pytest.mark.respx
    def test_get_content_types_retains_other_option_keys(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
    ) -> None:
        """Non-D&P option keys survive flattening."""
        item = make_v5_content_type_item(
            options_draft_and_publish=False,
            extra_options={"populateCreatorFields": True},
        )
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json={"data": [item]})
        )

        with SyncClient(strapi_config) as client:
            content_types = client.get_content_types()

        article = content_types[0]
        assert article.draft_and_publish is False
        assert article.options == {
            "populateCreatorFields": True,
            "draftAndPublish": False,
        }

    @pytest.mark.respx
    def test_published_at_does_not_imply_draft_and_publish(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
    ) -> None:
        """A publishedAt attribute must not make draft_and_publish False or True."""
        item = make_v5_content_type_item(include_published_at=True)
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json={"data": [item]})
        )

        with SyncClient(strapi_config) as client:
            content_types = client.get_content_types()

        assert content_types[0].draft_and_publish is None
        assert "publishedAt" in content_types[0].attributes

    def test_normalize_retains_schema_only_flag(self, strapi_config: StrapiConfig) -> None:
        """Flattening keeps schema-only draftAndPublish after dropping schema."""
        with SyncClient(strapi_config) as client:
            item = make_v5_content_type_item(schema_draft_and_publish=True)
            normalized = client._normalize_content_type_item(item)

        assert "schema" not in normalized
        assert normalized["draftAndPublish"] is True
        assert normalized["options"] == {"draftAndPublish": True}
        assert normalized["info"]["displayName"] == "Article"

    @pytest.mark.respx
    def test_live_strapi_format_content_type_shape(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
    ) -> None:
        """Stock formatContentType spreads getOptions() onto schema (not options)."""
        item = {
            "uid": "api::article.article",
            "apiID": "article",
            "schema": {
                "draftAndPublish": True,
                "populateCreatorFields": True,
                "displayName": "Article",
                "singularName": "article",
                "pluralName": "articles",
                "description": "",
                "kind": "collectionType",
                "collectionName": "articles",
                "attributes": {"title": {"type": "string"}},
                "visible": True,
                "restrictRelationsTo": None,
            },
        }
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json={"data": [item]})
        )

        with SyncClient(strapi_config) as client:
            content_types = client.get_content_types()

        article = content_types[0]
        assert article.draft_and_publish is True
        assert article.options is not None
        assert article.options["populateCreatorFields"] is True
        assert article.options["draftAndPublish"] is True
        assert article.options["visible"] is True
        assert article.options["restrictRelationsTo"] is None
        assert "displayName" not in article.options
        assert "attributes" not in article.options

    @pytest.mark.respx
    def test_get_content_types_top_level_options_on_nested_item(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
    ) -> None:
        """Top-level item.options is a D&P source even when schema has no options."""
        item = make_v5_content_type_item()
        item["options"] = {"draftAndPublish": True, "populateCreatorFields": True}
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json={"data": [item]})
        )

        with SyncClient(strapi_config) as client:
            content_types = client.get_content_types()

        article = content_types[0]
        assert article.draft_and_publish is True
        assert article.options == {
            "draftAndPublish": True,
            "populateCreatorFields": True,
        }


class TestUnparsableContentTypes:
    """Unparsable CTB items raise unless skip_unparsable is set (Issue #45)."""

    @staticmethod
    def _mixed_payload() -> dict[str, Any]:
        return {
            "data": [
                make_v5_content_type_item(),
                {"uid": "api::broken.broken"},
            ]
        }

    @pytest.mark.respx
    def test_unparsable_item_raises_by_default(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
    ) -> None:
        """Malformed items raise ValidationError by default."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json=self._mixed_payload())
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="Failed to parse content type"):
                client.get_content_types()

    @pytest.mark.respx
    def test_unparsable_item_skipped_when_opted_in(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
    ) -> None:
        """skip_unparsable=True logs and continues past malformed items."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json=self._mixed_payload())
        )

        with SyncClient(strapi_config) as client:
            content_types = client.get_content_types(skip_unparsable=True)

        assert len(content_types) == 1
        assert content_types[0].uid == "api::article.article"
        assert content_types[0].draft_and_publish is None

    @pytest.mark.respx
    async def test_async_unparsable_item_raises_by_default(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
    ) -> None:
        """AsyncClient also raises on unparsable items by default."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json=self._mixed_payload())
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="Failed to parse content type"):
                await client.get_content_types()

    @pytest.mark.respx
    async def test_async_unparsable_item_skipped_when_opted_in(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
    ) -> None:
        """AsyncClient skip_unparsable=True keeps valid items."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json=self._mixed_payload())
        )

        async with AsyncClient(strapi_config) as client:
            content_types = await client.get_content_types(skip_unparsable=True)

        assert len(content_types) == 1
        assert content_types[0].uid == "api::article.article"

    @pytest.mark.respx
    def test_non_object_item_raises_by_default(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
    ) -> None:
        """A non-object list item raises ValidationError, not AttributeError."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(
                200,
                json={"data": [make_v5_content_type_item(), "not-an-object"]},
            )
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="Failed to parse content type"):
                client.get_content_types()

    @pytest.mark.respx
    def test_non_object_item_skipped_when_opted_in(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
    ) -> None:
        """skip_unparsable=True skips non-object items."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(
                200,
                json={"data": [make_v5_content_type_item(), "not-an-object"]},
            )
        )

        with SyncClient(strapi_config) as client:
            content_types = client.get_content_types(skip_unparsable=True)

        assert len(content_types) == 1
        assert content_types[0].uid == "api::article.article"

    @pytest.mark.respx
    def test_non_list_data_raises_validation_error(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
    ) -> None:
        """A dict (or other non-list) data payload raises ValidationError."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json={"data": {"uid": "api::article.article"}})
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="must be a list"):
                client.get_content_types()

    @pytest.mark.respx
    def test_null_data_is_empty_list(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
    ) -> None:
        """data: null is treated as an empty list."""
        respx_mock.get("http://localhost:1337/api/content-type-builder/content-types").mock(
            return_value=Response(200, json={"data": None})
        )

        with SyncClient(strapi_config) as client:
            assert client.get_content_types() == []

    @pytest.mark.respx
    def test_schema_response_non_object_raises(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
    ) -> None:
        """get_content_type_schema raises ValidationError when data is not an object."""
        uid = "api::article.article"
        respx_mock.get(f"http://localhost:1337/api/content-type-builder/content-types/{uid}").mock(
            return_value=Response(200, json={"data": ["not-an-object"]})
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="Invalid content type schema response"):
                client.get_content_type_schema(uid)


def _valid_component_item() -> dict[str, Any]:
    return {
        "uid": "shared.seo",
        "category": "shared",
        "info": {"displayName": "SEO"},
        "attributes": {"metaTitle": {"type": "string"}},
    }


class TestUnparsableComponents:
    """Unparsable CTB components raise unless skip_unparsable is set (#79)."""

    @staticmethod
    def _mixed_payload() -> dict[str, Any]:
        return {"data": [_valid_component_item(), {"uid": "broken.broken"}]}

    @pytest.mark.respx
    def test_unparsable_component_raises_by_default(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
    ) -> None:
        respx_mock.get("http://localhost:1337/api/content-type-builder/components").mock(
            return_value=Response(200, json=self._mixed_payload())
        )

        with SyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="Failed to parse component"):
                client.get_components()

    @pytest.mark.respx
    def test_unparsable_component_skipped_when_opted_in(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
    ) -> None:
        respx_mock.get("http://localhost:1337/api/content-type-builder/components").mock(
            return_value=Response(200, json=self._mixed_payload())
        )

        with SyncClient(strapi_config) as client:
            components = client.get_components(skip_unparsable=True)

        assert len(components) == 1
        assert components[0].uid == "shared.seo"

    @pytest.mark.respx
    async def test_async_unparsable_component_raises_by_default(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
    ) -> None:
        respx_mock.get("http://localhost:1337/api/content-type-builder/components").mock(
            return_value=Response(200, json=self._mixed_payload())
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(ValidationError, match="Failed to parse component"):
                await client.get_components()

    @pytest.mark.respx
    async def test_async_unparsable_component_skipped_when_opted_in(
        self,
        strapi_config: StrapiConfig,
        respx_mock: respx.Router,
    ) -> None:
        respx_mock.get("http://localhost:1337/api/content-type-builder/components").mock(
            return_value=Response(200, json=self._mixed_payload())
        )

        async with AsyncClient(strapi_config) as client:
            components = await client.get_components(skip_unparsable=True)

        assert len(components) == 1
        assert components[0].uid == "shared.seo"
