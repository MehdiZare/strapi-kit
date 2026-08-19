"""Tests for relation resolver."""

import logging

import pytest

from strapi_kit.cache.schema_cache import InMemorySchemaCache
from strapi_kit.export.relation_resolver import RelationResolver
from strapi_kit.models.schema import ContentTypeSchema, FieldSchema, FieldType, RelationType


def _component_cache(*schemas: ContentTypeSchema) -> InMemorySchemaCache:
    cache = InMemorySchemaCache(client=None)  # type: ignore[arg-type]
    for schema in schemas:
        cache.cache_component_schema(schema.uid, schema)
    return cache


def test_resolve_relations() -> None:
    """Test resolving relations with ID mapping."""
    relations = {
        "author": [5],
        "categories": [1, 2],
    }

    id_mapping = {
        "api::author.author": {5: 50},
        "api::category.category": {1: 10, 2: 20},
    }

    # Resolve author
    resolved_author = RelationResolver.resolve_relations(
        {"author": relations["author"]},
        id_mapping,
        "api::author.author",
    )
    assert resolved_author == {"author": [50]}

    # Resolve categories
    resolved_categories = RelationResolver.resolve_relations(
        {"categories": relations["categories"]},
        id_mapping,
        "api::category.category",
    )
    assert resolved_categories == {"categories": [10, 20]}


def test_resolve_relations_missing_mapping() -> None:
    """Test resolving with missing ID mapping."""
    relations = {"author": [5, 6]}
    id_mapping = {
        "api::author.author": {5: 50}  # 6 is missing
    }

    resolved = RelationResolver.resolve_relations(
        relations,
        id_mapping,
        "api::author.author",
    )

    # Should only include the mapped ID
    assert resolved == {"author": [50]}


def test_resolve_relations_no_mapping() -> None:
    """Test resolving with no mapping available."""
    relations = {"author": [5]}
    id_mapping = {}  # No mapping for this content type

    resolved = RelationResolver.resolve_relations(
        relations,
        id_mapping,
        "api::author.author",
    )

    assert resolved == {}


def test_build_relation_payload_single() -> None:
    """Test building payload for single relation."""
    relations = {"author": [10]}

    payload = RelationResolver.build_relation_payload(relations)

    # Single relation should use single ID, not array
    assert payload == {"author": 10}


def test_build_relation_payload_multiple() -> None:
    """Test building payload for multiple relations."""
    relations = {"categories": [10, 11, 12]}

    payload = RelationResolver.build_relation_payload(relations)

    # Multiple relations should use array
    assert payload == {"categories": [10, 11, 12]}


def test_build_relation_payload_mixed() -> None:
    """Test building payload with mixed relations."""
    relations = {
        "author": [10],
        "categories": [11, 12],
        "featured_image": [20],
    }

    payload = RelationResolver.build_relation_payload(relations)

    assert payload == {
        "author": 10,
        "categories": [11, 12],
        "featured_image": 20,
    }


def test_build_relation_payload_empty() -> None:
    """Test building payload with no relations."""
    relations: dict[str, list[int]] = {}

    payload = RelationResolver.build_relation_payload(relations)

    assert payload == {}


def test_build_relation_payload_empty_list() -> None:
    """Test building payload with empty relation list (clears relation)."""
    relations = {"author": []}

    payload = RelationResolver.build_relation_payload(relations)

    # Empty list should be included to clear the relation
    assert payload == {"author": []}


def test_build_v5_payload_writes_nested_component_relation() -> None:
    """Nested seo[0].author is merged into the component object, not dropped."""
    seo_schema = ContentTypeSchema(
        uid="shared.seo",
        display_name="SEO",
        fields={
            "metaTitle": FieldSchema(type=FieldType.STRING),
            "author": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_ONE,
                target="api::author.author",
            ),
        },
    )
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "title": FieldSchema(type=FieldType.STRING),
            "seo": FieldSchema(
                type=FieldType.COMPONENT,
                component="shared.seo",
                repeatable=True,
            ),
        },
    )
    entity_data = {"title": "Hello", "seo": [{"metaTitle": "T"}]}
    skipped: list[str] = []
    payload = RelationResolver.build_v5_relation_payload(
        {"seo[0].author": ["auth-dest"]},
        article_schema,
        _component_cache(seo_schema),
        entity_data=entity_data,
        skipped=skipped,
    )
    assert skipped == []
    assert payload["seo"][0]["metaTitle"] == "T"
    assert payload["seo"][0]["author"] == "auth-dest"


def test_build_v5_payload_writes_dynamic_zone_relation() -> None:
    """DZ items keep __component and receive the dest documentId."""
    seo_schema = ContentTypeSchema(
        uid="shared.seo",
        display_name="SEO",
        fields={
            "author": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_ONE,
                target="api::author.author",
            ),
        },
    )
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "blocks": FieldSchema(
                type=FieldType.DYNAMIC_ZONE,
                components=["shared.seo"],
            ),
        },
    )
    entity_data = {"blocks": [{"__component": "shared.seo"}]}
    payload = RelationResolver.build_v5_relation_payload(
        {"blocks[0].author": ["auth-dest"]},
        article_schema,
        _component_cache(seo_schema),
        entity_data=entity_data,
        skipped=[],
    )
    assert payload["blocks"][0]["__component"] == "shared.seo"
    assert payload["blocks"][0]["author"] == "auth-dest"


def test_build_v5_payload_records_skipped_nested_without_entity_data() -> None:
    """Without the component shell, nested keys cannot be written."""
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={"title": FieldSchema(type=FieldType.STRING)},
    )
    skipped: list[str] = []
    payload = RelationResolver.build_v5_relation_payload(
        {"seo[0].author": ["auth-dest"]},
        article_schema,
        entity_data={"title": "Hello"},
        skipped=skipped,
    )
    assert payload == {}
    assert skipped == ["seo[0].author"]


def test_extract_component_dispatches_on_list_shape() -> None:
    """A list payload is walked even when the schema flag is not repeatable."""
    seo_schema = ContentTypeSchema(
        uid="shared.seo",
        display_name="SEO",
        fields={
            "author": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_ONE,
                target="api::author.author",
            ),
        },
    )
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "seo": FieldSchema(
                type=FieldType.COMPONENT,
                component="shared.seo",
                repeatable=False,
            ),
        },
    )
    data = {
        "seo": [{"author": {"id": 1, "documentId": "auth-src"}}],
    }
    relations = RelationResolver.extract_relations_with_schema(
        data, article_schema, _component_cache(seo_schema)
    )
    assert relations == {"seo[0].author": ["auth-src"]}


def test_extract_component_dispatches_on_dict_shape() -> None:
    """A dict payload is walked even when the schema flag is repeatable."""
    seo_schema = ContentTypeSchema(
        uid="shared.seo",
        display_name="SEO",
        fields={
            "author": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_ONE,
                target="api::author.author",
            ),
        },
    )
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "seo": FieldSchema(
                type=FieldType.COMPONENT,
                component="shared.seo",
                repeatable=True,
            ),
        },
    )
    data = {"seo": {"author": {"id": 1, "documentId": "auth-src"}}}
    relations = RelationResolver.extract_relations_with_schema(
        data, article_schema, _component_cache(seo_schema)
    )
    assert relations == {"seo.author": ["auth-src"]}


def test_strip_component_dispatches_on_list_shape() -> None:
    """A list payload is stripped even when the schema flag is not repeatable."""
    seo_schema = ContentTypeSchema(
        uid="shared.seo",
        display_name="SEO",
        fields={
            "metaTitle": FieldSchema(type=FieldType.STRING),
            "author": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_ONE,
                target="api::author.author",
            ),
        },
    )
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "title": FieldSchema(type=FieldType.STRING),
            "seo": FieldSchema(
                type=FieldType.COMPONENT,
                component="shared.seo",
                repeatable=False,
            ),
        },
    )
    data = {
        "title": "Hello",
        "seo": [{"metaTitle": "T", "author": {"documentId": "auth-src"}}],
    }
    stripped = RelationResolver.strip_relations_with_schema(
        data, article_schema, _component_cache(seo_schema)
    )
    assert stripped == {"title": "Hello", "seo": [{"metaTitle": "T"}]}


def test_strip_component_dispatches_on_dict_shape() -> None:
    """A dict payload is stripped even when the schema flag is repeatable."""
    seo_schema = ContentTypeSchema(
        uid="shared.seo",
        display_name="SEO",
        fields={
            "metaTitle": FieldSchema(type=FieldType.STRING),
            "author": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_ONE,
                target="api::author.author",
            ),
        },
    )
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "title": FieldSchema(type=FieldType.STRING),
            "seo": FieldSchema(
                type=FieldType.COMPONENT,
                component="shared.seo",
                repeatable=True,
            ),
        },
    )
    data = {
        "title": "Hello",
        "seo": {"metaTitle": "T", "author": {"documentId": "auth-src"}},
    }
    stripped = RelationResolver.strip_relations_with_schema(
        data, article_schema, _component_cache(seo_schema)
    )
    assert stripped == {"title": "Hello", "seo": {"metaTitle": "T"}}


def test_strip_component_keeps_payload_when_schema_missing() -> None:
    """A list payload with an unfetchable component schema is left unchanged."""
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "seo": FieldSchema(
                type=FieldType.COMPONENT,
                component="shared.seo",
                repeatable=False,
            ),
        },
    )
    data = {"seo": [{"metaTitle": "T", "author": {"documentId": "auth-src"}}]}
    stripped = RelationResolver.strip_relations_with_schema(
        data, article_schema, _component_cache()
    )
    assert stripped == data


def test_extract_nested_component_dispatches_on_list_shape() -> None:
    """Nested components also walk list payloads when repeatable is false."""
    byline_schema = ContentTypeSchema(
        uid="shared.byline",
        display_name="Byline",
        fields={
            "author": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_ONE,
                target="api::author.author",
            ),
        },
    )
    seo_schema = ContentTypeSchema(
        uid="shared.seo",
        display_name="SEO",
        fields={
            "byline": FieldSchema(
                type=FieldType.COMPONENT,
                component="shared.byline",
                repeatable=False,
            ),
        },
    )
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "seo": FieldSchema(
                type=FieldType.COMPONENT,
                component="shared.seo",
                repeatable=False,
            ),
        },
    )
    data = {
        "seo": {"byline": [{"author": {"id": 1, "documentId": "auth-src"}}]},
    }
    relations = RelationResolver.extract_relations_with_schema(
        data, article_schema, _component_cache(byline_schema, seo_schema)
    )
    assert relations == {"seo.byline[0].author": ["auth-src"]}


def test_extract_component_unwraps_v4_data_wrapper() -> None:
    """A v4 ``{data: {...}}`` component wrapper is unwrapped before walking."""
    seo_schema = ContentTypeSchema(
        uid="shared.seo",
        display_name="SEO",
        fields={
            "author": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_ONE,
                target="api::author.author",
            ),
        },
    )
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "seo": FieldSchema(
                type=FieldType.COMPONENT,
                component="shared.seo",
                repeatable=False,
            ),
        },
    )
    data = {"seo": {"data": {"author": {"id": 1, "documentId": "auth-src"}}}}
    relations = RelationResolver.extract_relations_with_schema(
        data, article_schema, _component_cache(seo_schema)
    )
    assert relations == {"seo.author": ["auth-src"]}


def test_extract_component_unwraps_v4_list_wrapper() -> None:
    """A v4 ``{data: [...]}`` wrapper walks each list item."""
    seo_schema = ContentTypeSchema(
        uid="shared.seo",
        display_name="SEO",
        fields={
            "author": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_ONE,
                target="api::author.author",
            ),
        },
    )
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "seo": FieldSchema(
                type=FieldType.COMPONENT,
                component="shared.seo",
                repeatable=True,
            ),
        },
    )
    data = {"seo": {"data": [{"author": {"id": 1, "documentId": "auth-src"}}]}}
    relations = RelationResolver.extract_relations_with_schema(
        data, article_schema, _component_cache(seo_schema)
    )
    assert relations == {"seo[0].author": ["auth-src"]}


def test_extract_component_warns_on_scalar_payload(caplog: pytest.LogCaptureFixture) -> None:
    """A scalar component value is skipped and logged."""
    seo_schema = ContentTypeSchema(
        uid="shared.seo",
        display_name="SEO",
        fields={
            "author": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_ONE,
                target="api::author.author",
            ),
        },
    )
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "seo": FieldSchema(
                type=FieldType.COMPONENT,
                component="shared.seo",
                repeatable=False,
            ),
        },
    )
    with caplog.at_level(logging.WARNING):
        relations = RelationResolver.extract_relations_with_schema(
            {"seo": "oops"}, article_schema, _component_cache(seo_schema)
        )
    assert relations == {}
    assert any("Unexpected component payload" in rec.message for rec in caplog.records)


def test_extract_component_warns_on_non_dict_list_item(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Non-dict list items are skipped; dict siblings are still walked."""
    seo_schema = ContentTypeSchema(
        uid="shared.seo",
        display_name="SEO",
        fields={
            "author": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_ONE,
                target="api::author.author",
            ),
        },
    )
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "seo": FieldSchema(
                type=FieldType.COMPONENT,
                component="shared.seo",
                repeatable=True,
            ),
        },
    )
    data = {"seo": ["x", {"author": {"id": 1, "documentId": "auth-src"}}]}
    with caplog.at_level(logging.WARNING):
        relations = RelationResolver.extract_relations_with_schema(
            data, article_schema, _component_cache(seo_schema)
        )
    assert relations == {"seo[1].author": ["auth-src"]}
    assert any("Unexpected component list item" in rec.message for rec in caplog.records)


def _seo_article_schemas(*, repeatable: bool) -> tuple[ContentTypeSchema, ContentTypeSchema]:
    seo_schema = ContentTypeSchema(
        uid="shared.seo",
        display_name="SEO",
        fields={
            "metaTitle": FieldSchema(type=FieldType.STRING),
            "author": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_ONE,
                target="api::author.author",
            ),
        },
    )
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "title": FieldSchema(type=FieldType.STRING),
            "seo": FieldSchema(
                type=FieldType.COMPONENT,
                component="shared.seo",
                repeatable=repeatable,
            ),
        },
    )
    return seo_schema, article_schema


def test_strip_component_unwraps_v4_list_wrapper() -> None:
    """Strip unwraps ``{data: [...]}`` before removing nested relations."""
    seo_schema, article_schema = _seo_article_schemas(repeatable=True)
    data = {
        "title": "Hello",
        "seo": {"data": [{"metaTitle": "T", "author": {"documentId": "auth-src"}}]},
    }
    stripped = RelationResolver.strip_relations_with_schema(
        data, article_schema, _component_cache(seo_schema)
    )
    assert stripped == {"title": "Hello", "seo": [{"metaTitle": "T"}]}


def test_strip_component_unwraps_v4_dict_wrapper() -> None:
    """Strip unwraps ``{data: {...}}`` before removing nested relations."""
    seo_schema, article_schema = _seo_article_schemas(repeatable=False)
    data = {
        "title": "Hello",
        "seo": {"data": {"metaTitle": "T", "author": {"documentId": "auth-src"}}},
    }
    stripped = RelationResolver.strip_relations_with_schema(
        data, article_schema, _component_cache(seo_schema)
    )
    assert stripped == {"title": "Hello", "seo": {"metaTitle": "T"}}


def test_unwrap_keeps_component_with_data_sibling() -> None:
    """A component that also has a ``data`` field is not treated as a wrapper."""
    seo_schema = ContentTypeSchema(
        uid="shared.seo",
        display_name="SEO",
        fields={
            "metaTitle": FieldSchema(type=FieldType.STRING),
            "data": FieldSchema(type=FieldType.JSON),
            "author": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_ONE,
                target="api::author.author",
            ),
        },
    )
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "seo": FieldSchema(
                type=FieldType.COMPONENT,
                component="shared.seo",
                repeatable=False,
            ),
        },
    )
    data = {
        "seo": {
            "metaTitle": "T",
            "data": {"note": "keep"},
            "author": {"documentId": "auth-src"},
        }
    }
    relations = RelationResolver.extract_relations_with_schema(
        data, article_schema, _component_cache(seo_schema)
    )
    stripped = RelationResolver.strip_relations_with_schema(
        data, article_schema, _component_cache(seo_schema)
    )
    assert relations == {"seo.author": ["auth-src"]}
    assert stripped == {"seo": {"metaTitle": "T", "data": {"note": "keep"}}}


def test_strip_component_warns_on_scalar_payload(caplog: pytest.LogCaptureFixture) -> None:
    """A scalar component value is kept and logged."""
    seo_schema, article_schema = _seo_article_schemas(repeatable=False)
    with caplog.at_level(logging.WARNING):
        stripped = RelationResolver.strip_relations_with_schema(
            {"title": "Hello", "seo": "oops"},
            article_schema,
            _component_cache(seo_schema),
        )
    assert stripped == {"title": "Hello", "seo": "oops"}
    assert any("Unexpected component payload" in rec.message for rec in caplog.records)
    assert any("seo" in rec.message for rec in caplog.records)


def test_strip_component_warns_on_non_dict_list_item(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Non-dict list items are kept and logged; dict siblings are stripped."""
    seo_schema, article_schema = _seo_article_schemas(repeatable=True)
    data = {
        "title": "Hello",
        "seo": ["x", {"metaTitle": "T", "author": {"documentId": "auth-src"}}],
    }
    with caplog.at_level(logging.WARNING):
        stripped = RelationResolver.strip_relations_with_schema(
            data, article_schema, _component_cache(seo_schema)
        )
    assert stripped == {"title": "Hello", "seo": ["x", {"metaTitle": "T"}]}
    assert any("Unexpected component list item" in rec.message for rec in caplog.records)


def test_extract_ids_rejects_bool() -> None:
    """bool is a subclass of int but is not a relation id (#150)."""
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "featured": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_ONE,
                target="api::author.author",
            ),
            "categories": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_MANY,
                target="api::category.category",
            ),
        },
    )
    assert RelationResolver.extract_relations_with_schema({"featured": True}, article_schema) == {}
    assert RelationResolver.extract_relations_with_schema({"featured": False}, article_schema) == {}
    assert (
        RelationResolver.extract_relations_with_schema(
            {"categories": [True, False]}, article_schema
        )
        == {}
    )
    assert RelationResolver.extract_relations_with_schema(
        {"categories": [1, True, "cat-src"]}, article_schema
    ) == {"categories": [1, "cat-src"]}
    assert (
        RelationResolver.extract_relations_with_schema({"featured": {"id": True}}, article_schema)
        == {}
    )
