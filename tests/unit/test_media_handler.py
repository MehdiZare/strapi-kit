"""Tests for media handler."""

from strapi_kit.export.media_handler import MediaHandler


def test_extract_media_references_single() -> None:
    """Test extracting a single media reference."""
    data = {
        "title": "Article",
        "cover": {
            "data": {
                "id": 5,
                "mime": "image/jpeg",
                "url": "/uploads/image.jpg",
            }
        },
    }

    media_ids = MediaHandler.extract_media_references(data)

    assert media_ids == [5]


def test_extract_media_references_multiple() -> None:
    """Test extracting multiple media references."""
    data = {
        "title": "Article",
        "gallery": {
            "data": [
                {"id": 10, "mime": "image/jpeg", "url": "/uploads/img1.jpg"},
                {"id": 11, "mime": "image/png", "url": "/uploads/img2.png"},
                {"id": 12, "mime": "image/gif", "url": "/uploads/img3.gif"},
            ]
        },
    }

    media_ids = MediaHandler.extract_media_references(data)

    assert media_ids == [10, 11, 12]


def test_extract_media_references_mixed() -> None:
    """Test extracting mixed media references."""
    data = {
        "title": "Article",
        "cover": {"data": {"id": 5, "mime": "image/jpeg"}},
        "gallery": {
            "data": [
                {"id": 10, "mime": "image/jpeg"},
                {"id": 11, "mime": "image/png"},
            ]
        },
        "attachment": {"data": {"id": 20, "mime": "application/pdf"}},
    }

    media_ids = MediaHandler.extract_media_references(data)

    assert media_ids == [5, 10, 11, 20]


def test_extract_media_references_null() -> None:
    """Test extracting when media is null."""
    data = {
        "title": "Article",
        "cover": {"data": None},
    }

    media_ids = MediaHandler.extract_media_references(data)

    assert media_ids == []


def test_extract_media_references_no_media() -> None:
    """Test extracting when there are no media references."""
    data = {
        "title": "Article",
        "content": "Some text content",
        "published": True,
    }

    media_ids = MediaHandler.extract_media_references(data)

    assert media_ids == []


def test_extract_media_references_ignores_relations() -> None:
    """Test that media extraction ignores relation fields."""
    data = {
        "title": "Article",
        "author": {"data": {"id": 99}},  # Relation (no mime)
        "cover": {"data": {"id": 5, "mime": "image/jpeg"}},  # Media (has mime)
    }

    media_ids = MediaHandler.extract_media_references(data)

    # Should only extract media (with mime), not relations
    assert media_ids == [5]


def test_update_media_references_single() -> None:
    """Test updating a single media reference."""
    data = {
        "title": "Article",
        "cover": {
            "data": {
                "id": 5,
                "mime": "image/jpeg",
                "url": "/uploads/image.jpg",
            }
        },
    }

    mapping = {5: 50}
    updated = MediaHandler.update_media_references(data, mapping)

    assert updated["cover"] == 50


def test_update_media_references_multiple() -> None:
    """Test updating multiple media references."""
    data = {
        "title": "Article",
        "gallery": {
            "data": [
                {"id": 10, "mime": "image/jpeg"},
                {"id": 11, "mime": "image/png"},
            ]
        },
    }

    mapping = {10: 100, 11: 110}
    updated = MediaHandler.update_media_references(data, mapping)

    assert updated["gallery"] == [100, 110]


def test_update_media_references_mixed() -> None:
    """Test updating mixed media references."""
    data = {
        "title": "Article",
        "cover": {"data": {"id": 5, "mime": "image/jpeg"}},
        "gallery": {
            "data": [
                {"id": 10, "mime": "image/jpeg"},
                {"id": 11, "mime": "image/png"},
            ]
        },
    }

    mapping = {5: 50, 10: 100, 11: 110}
    updated = MediaHandler.update_media_references(data, mapping)

    assert updated["cover"] == 50
    assert updated["gallery"] == [100, 110]


def test_update_media_references_partial_mapping() -> None:
    """Test updating when mapping is incomplete."""
    data = {
        "gallery": {
            "data": [
                {"id": 10, "mime": "image/jpeg"},
                {"id": 11, "mime": "image/png"},
            ]
        },
    }

    mapping = {10: 100}  # Only one ID mapped
    updated = MediaHandler.update_media_references(data, mapping)

    # Mapped id becomes dest write id; unmapped entries are omitted
    assert updated["gallery"] == [100]


def test_update_media_references_no_mapping() -> None:
    """Test updating when there's no mapping."""
    data = {
        "cover": {"data": {"id": 5, "mime": "image/jpeg"}},
    }

    mapping = {}  # Empty mapping
    updated = MediaHandler.update_media_references(data, mapping)

    # Unmapped one-side media is a write-shape clear, not the source id/blob
    assert updated["cover"] is None


def test_update_media_references_preserves_non_media_fields() -> None:
    """Test that non-media fields are preserved."""
    data = {
        "title": "Article",
        "content": "Some content",
        "published": True,
        "cover": {"data": {"id": 5, "mime": "image/jpeg"}},
    }

    mapping = {5: 50}
    updated = MediaHandler.update_media_references(data, mapping)

    assert updated["title"] == "Article"
    assert updated["content"] == "Some content"
    assert updated["published"] is True
    assert updated["cover"] == 50


def test_update_media_references_null_media() -> None:
    """Test updating when media is null."""
    data = {
        "title": "Article",
        "cover": {"data": None},
    }

    mapping = {5: 50}
    updated = MediaHandler.update_media_references(data, mapping)

    assert updated["cover"] is None


def test_update_media_references_ignores_relations() -> None:
    """Test that relation fields are not updated."""
    data = {
        "title": "Article",
        "author": {"data": {"id": 99}},  # Relation (no mime)
        "cover": {"data": {"id": 5, "mime": "image/jpeg"}},  # Media
    }

    mapping = {5: 50, 99: 999}
    updated = MediaHandler.update_media_references(data, mapping)

    assert updated["cover"] == 50

    # Relation should remain unchanged (no mime field means it's not media)
    assert updated["author"]["data"]["id"] == 99


def test_extract_media_references_nested_component_v5() -> None:
    """populate=* media inside a component is at the field root, not under data."""
    data = {
        "title": "Article",
        "seo": {
            "ogImage": {
                "id": 7,
                "documentId": "media-src",
                "mime": "image/jpeg",
                "url": "/uploads/og.jpg",
            }
        },
    }

    assert MediaHandler.extract_media_references(data) == [7]


def test_update_media_references_drops_source_document_id() -> None:
    """Remap must not leave a source documentId that v5 would reconnect."""
    data = {
        "cover": {
            "id": 5,
            "documentId": "media-src",
            "mime": "image/jpeg",
        },
        "seo": {
            "ogImage": {
                "id": 7,
                "documentId": "og-src",
                "mime": "image/png",
            }
        },
    }

    updated = MediaHandler.update_media_references(
        data,
        {5: 50, 7: 70},
        media_doc_mapping={"media-src": "media-dest", "og-src": "og-dest"},
    )

    assert updated["cover"] == "media-dest"
    assert updated["seo"]["ogImage"] == "og-dest"


def test_update_media_references_schema_skips_relation_data_wrapper() -> None:
    """With a schema, v4 {data: null} on a relation is not treated as media (#120)."""
    from strapi_kit.models.schema import ContentTypeSchema, FieldSchema, FieldType, RelationType

    schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "title": FieldSchema(type=FieldType.STRING),
            "author": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_ONE,
                target="api::author.author",
            ),
            "cover": FieldSchema(type=FieldType.MEDIA),
        },
    )
    data = {
        "title": "Hello",
        "author": {"data": None},
        "cover": {"id": 5, "documentId": "media-src", "mime": "image/jpeg"},
    }
    updated = MediaHandler.update_media_references(
        data,
        {5: 50},
        media_doc_mapping={"media-src": "media-dest"},
        schema=schema,
    )
    assert updated["author"] == {"data": None}
    assert updated["cover"] == "media-dest"


def test_update_media_references_schema_walks_component_media() -> None:
    """Schema walk remaps FieldType.MEDIA inside a component (#120)."""
    from strapi_kit.cache.schema_cache import InMemorySchemaCache
    from strapi_kit.models.schema import ContentTypeSchema, FieldSchema, FieldType

    seo_schema = ContentTypeSchema(
        uid="shared.seo",
        display_name="SEO",
        fields={
            "metaTitle": FieldSchema(type=FieldType.STRING),
            "ogImage": FieldSchema(type=FieldType.MEDIA),
        },
    )
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "seo": FieldSchema(type=FieldType.COMPONENT, component="shared.seo"),
        },
    )
    cache = InMemorySchemaCache(client=None)  # type: ignore[arg-type]
    cache.cache_component_schema("shared.seo", seo_schema)
    data = {
        "seo": {
            "metaTitle": "T",
            "ogImage": {"id": 7, "documentId": "og-src", "mime": "image/png"},
        }
    }
    updated = MediaHandler.update_media_references(
        data,
        {7: 70},
        media_doc_mapping={"og-src": "og-dest"},
        schema=article_schema,
        schema_cache=cache,
    )
    assert updated["seo"]["metaTitle"] == "T"
    assert updated["seo"]["ogImage"] == "og-dest"


def test_update_media_references_schema_unknown_field_uses_heuristic() -> None:
    """Unknown fields fall back to the mime heuristic, not a raw blob."""
    from strapi_kit.models.schema import ContentTypeSchema, FieldSchema, FieldType, RelationType

    schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "author": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_ONE,
                target="api::author.author",
            ),
            "cover": FieldSchema(type=FieldType.MEDIA),
        },
    )
    data = {
        "author": {"data": None},
        "cover": {"id": 5, "documentId": "media-src", "mime": "image/jpeg"},
        "legacyOg": {"id": 9, "documentId": "extra-src", "mime": "image/png"},
    }
    updated = MediaHandler.update_media_references(
        data,
        {5: 50, 9: 90},
        media_doc_mapping={"media-src": "media-dest", "extra-src": "extra-dest"},
        schema=schema,
    )
    assert updated["author"] == {"data": None}
    assert updated["cover"] == "media-dest"
    assert updated["legacyOg"] == "extra-dest"


def test_update_media_references_unresolved_component_uses_heuristic() -> None:
    """Cache-miss component schemas remap nested media via the mime heuristic."""
    from strapi_kit.models.schema import ContentTypeSchema, FieldSchema, FieldType

    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "seo": FieldSchema(type=FieldType.COMPONENT, component="shared.seo"),
        },
    )
    data = {
        "seo": {
            "metaTitle": "T",
            "ogImage": {"id": 7, "documentId": "og-src", "mime": "image/png"},
        }
    }
    updated = MediaHandler.update_media_references(
        data,
        {7: 70},
        media_doc_mapping={"og-src": "og-dest"},
        schema=article_schema,
        schema_cache=None,
    )
    assert updated["seo"]["metaTitle"] == "T"
    assert updated["seo"]["ogImage"] == "og-dest"


def test_update_media_references_unresolved_dynamic_zone_uses_heuristic() -> None:
    """Unresolved dynamic-zone items remap nested media and keep __component."""
    from strapi_kit.models.schema import ContentTypeSchema, FieldSchema, FieldType

    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "blocks": FieldSchema(type=FieldType.DYNAMIC_ZONE, components=["shared.seo"]),
        },
    )
    data = {
        "blocks": [
            {
                "__component": "shared.seo",
                "ogImage": {"id": 7, "documentId": "og-src", "mime": "image/png"},
            }
        ]
    }
    updated = MediaHandler.update_media_references(
        data,
        {7: 70},
        media_doc_mapping={"og-src": "og-dest"},
        schema=article_schema,
        schema_cache=None,
    )
    assert updated["blocks"][0]["__component"] == "shared.seo"
    assert updated["blocks"][0]["ogImage"] == "og-dest"


def test_update_media_references_schema_v4_media_without_mime() -> None:
    """A typed MEDIA field unwraps v4 {data: {id}} even when mime is absent."""
    from strapi_kit.models.schema import ContentTypeSchema, FieldSchema, FieldType

    schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={"cover": FieldSchema(type=FieldType.MEDIA)},
    )
    updated = MediaHandler.update_media_references(
        {"cover": {"data": {"id": 3}}},
        {3: 30},
        schema=schema,
    )
    assert updated["cover"] == 30


def test_update_media_references_schema_walks_dynamic_zone_media() -> None:
    """Resolved dynamic-zone items remap media and preserve __component."""
    from strapi_kit.cache.schema_cache import InMemorySchemaCache
    from strapi_kit.models.schema import ContentTypeSchema, FieldSchema, FieldType

    seo_schema = ContentTypeSchema(
        uid="shared.seo",
        display_name="SEO",
        fields={
            "metaTitle": FieldSchema(type=FieldType.STRING),
            "ogImage": FieldSchema(type=FieldType.MEDIA),
        },
    )
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "blocks": FieldSchema(type=FieldType.DYNAMIC_ZONE, components=["shared.seo"]),
        },
    )
    cache = InMemorySchemaCache(client=None)  # type: ignore[arg-type]
    cache.cache_component_schema("shared.seo", seo_schema)
    data = {
        "blocks": [
            {
                "__component": "shared.seo",
                "metaTitle": "T",
                "ogImage": {"id": 7, "documentId": "og-src", "mime": "image/png"},
            }
        ]
    }
    updated = MediaHandler.update_media_references(
        data,
        {7: 70},
        media_doc_mapping={"og-src": "og-dest"},
        schema=article_schema,
        schema_cache=cache,
    )
    assert updated["blocks"][0]["__component"] == "shared.seo"
    assert updated["blocks"][0]["metaTitle"] == "T"
    assert updated["blocks"][0]["ogImage"] == "og-dest"


def test_update_media_references_schema_walks_repeatable_component_list() -> None:
    """Repeatable COMPONENT lists remap media on each item."""
    from strapi_kit.cache.schema_cache import InMemorySchemaCache
    from strapi_kit.models.schema import ContentTypeSchema, FieldSchema, FieldType

    seo_schema = ContentTypeSchema(
        uid="shared.seo",
        display_name="SEO",
        fields={
            "metaTitle": FieldSchema(type=FieldType.STRING),
            "ogImage": FieldSchema(type=FieldType.MEDIA),
        },
    )
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "seo": FieldSchema(type=FieldType.COMPONENT, component="shared.seo", repeatable=True),
        },
    )
    cache = InMemorySchemaCache(client=None)  # type: ignore[arg-type]
    cache.cache_component_schema("shared.seo", seo_schema)
    data = {
        "seo": [
            {
                "metaTitle": "A",
                "ogImage": {"id": 7, "documentId": "og-src", "mime": "image/png"},
            },
            {
                "metaTitle": "B",
                "ogImage": {"id": 8, "documentId": "og-src-2", "mime": "image/jpeg"},
            },
        ]
    }
    updated = MediaHandler.update_media_references(
        data,
        {7: 70, 8: 80},
        media_doc_mapping={"og-src": "og-dest", "og-src-2": "og-dest-2"},
        schema=article_schema,
        schema_cache=cache,
    )
    assert updated["seo"][0]["metaTitle"] == "A"
    assert updated["seo"][0]["ogImage"] == "og-dest"
    assert updated["seo"][1]["ogImage"] == "og-dest-2"


def test_update_media_references_component_dispatches_on_list_shape() -> None:
    """A list value is walked even when the schema flag is not repeatable."""
    from strapi_kit.cache.schema_cache import InMemorySchemaCache
    from strapi_kit.models.schema import ContentTypeSchema, FieldSchema, FieldType

    seo_schema = ContentTypeSchema(
        uid="shared.seo",
        display_name="SEO",
        fields={"ogImage": FieldSchema(type=FieldType.MEDIA)},
    )
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "seo": FieldSchema(type=FieldType.COMPONENT, component="shared.seo", repeatable=False),
        },
    )
    cache = InMemorySchemaCache(client=None)  # type: ignore[arg-type]
    cache.cache_component_schema("shared.seo", seo_schema)
    data = {
        "seo": [
            {"ogImage": {"id": 7, "documentId": "og-src", "mime": "image/png"}},
        ]
    }
    updated = MediaHandler.update_media_references(
        data,
        {7: 70},
        media_doc_mapping={"og-src": "og-dest"},
        schema=article_schema,
        schema_cache=cache,
    )
    assert updated["seo"][0]["ogImage"] == "og-dest"
