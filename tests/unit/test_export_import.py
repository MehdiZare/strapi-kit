"""Tests for export and import functionality."""

from datetime import datetime
from pathlib import Path

import httpx
import pytest
import respx

from strapi_kit import StrapiConfig, StrapiExporter, StrapiImporter
from strapi_kit.client.sync_client import SyncClient
from strapi_kit.exceptions import FormatError, ImportExportError
from strapi_kit.export.jsonl_writer import JSONLExportWriter
from strapi_kit.models import (
    ConflictResolution,
    ExportData,
    ExportedEntity,
    ExportedMediaFile,
    ExportMetadata,
    ImportOptions,
    ImportResult,
)
from strapi_kit.models.schema import ContentTypeSchema, FieldSchema, FieldType, RelationType
from strapi_kit.utils.uid import uid_to_endpoint

_COLLECTION_LOCALE_ALL: list[tuple[respx.Router, str, dict[str, set[str]]]] = []


def _collection_locale_all_docs(respx_mock: respx.Router, collection: str) -> dict[str, set[str]]:
    """documentId -> present locales for ``GET /api/{collection}?locale=all``."""
    docs: dict[str, set[str]] | None = None
    for router, coll, stored in _COLLECTION_LOCALE_ALL:
        if router is respx_mock and coll == collection:
            docs = stored
            break
    if docs is None:
        docs = {}
        _COLLECTION_LOCALE_ALL.append((respx_mock, collection, docs))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("locale") not in {"all", "*"}:
            return httpx.Response(200, json={"data": []})
        document_id = request.url.params.get("filters[documentId][$eq]")
        present = docs.get(document_id or "", set())
        if not present:
            return httpx.Response(200, json={"data": []})
        loc = sorted(present)[0]
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 1,
                        "documentId": document_id,
                        "title": loc,
                        "locale": loc,
                    }
                ]
            },
        )

    respx_mock.get(url__regex=rf"http://localhost:1337/api/{collection}(\?.*)?$").mock(
        side_effect=handler
    )
    return docs


def _mock_document_missing(respx_mock: respx.Router, collection: str, document_id: str) -> None:
    """Both published and draft existence probes 404."""
    respx_mock.get(f"http://localhost:1337/api/{collection}/{document_id}").mock(
        return_value=httpx.Response(404, json={"error": {"status": 404, "message": "Not found"}})
    )
    _collection_locale_all_docs(respx_mock, collection)[document_id] = set()


def _mock_document_exists(
    respx_mock: respx.Router,
    collection: str,
    document_id: str,
    *,
    dest_id: int,
) -> None:
    """Published existence probe returns the dest row."""
    respx_mock.get(f"http://localhost:1337/api/{collection}/{document_id}").mock(
        return_value=httpx.Response(200, json={"data": {"id": dest_id, "documentId": document_id}})
    )


def _nested_component_schemas() -> tuple[ContentTypeSchema, ContentTypeSchema, ContentTypeSchema]:
    """Article + author + repeatable seo.author component used by nested import tests."""
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
    author_schema = ContentTypeSchema(
        uid="api::author.author",
        display_name="Author",
        plural_name="authors",
        fields={"name": FieldSchema(type=FieldType.STRING)},
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
    return seo_schema, author_schema, article_schema


def _nested_component_export(*, include_component_schemas: bool = True) -> ExportData:
    """In-memory export of author + article with ``seo[0].author``."""
    seo_schema, author_schema, article_schema = _nested_component_schemas()
    return ExportData(
        metadata=ExportMetadata(
            strapi_version="v5",
            source_url="http://localhost:1337",
            content_types=["api::author.author", "api::article.article"],
            total_entities=2,
            schemas={
                "api::author.author": author_schema,
                "api::article.article": article_schema,
            },
            component_schemas={"shared.seo": seo_schema} if include_component_schemas else {},
        ),
        entities={
            "api::author.author": [
                ExportedEntity(
                    id=1,
                    document_id="auth-src",
                    content_type="api::author.author",
                    data={"name": "Ada"},
                )
            ],
            "api::article.article": [
                ExportedEntity(
                    id=2,
                    document_id="art-src",
                    content_type="api::article.article",
                    data={"title": "Hello", "seo": [{"metaTitle": "T"}]},
                    relations={"seo[0].author": ["auth-src"]},
                )
            ],
        },
    )


def _write_export_jsonl(jsonl_path: Path, export_data: ExportData) -> None:
    """Stream an in-memory export to JSONL."""
    with JSONLExportWriter(jsonl_path) as writer:
        writer.write_metadata(export_data.metadata)
        for content_type in export_data.metadata.content_types:
            for entity in export_data.entities.get(content_type, []):
                writer.write_entity(entity)


def _write_nested_component_jsonl(jsonl_path: Path) -> None:
    """Stream the nested-component fixture to JSONL."""
    _write_export_jsonl(jsonl_path, _nested_component_export())


def _mock_nested_component_writes(
    respx_mock: respx.Router, *, mock_component_ctb: bool = False
) -> tuple[respx.Route, respx.Route | None]:
    """Create/PUT mocks for the nested-component fixture.

    Returns:
        ``(relation_route, component_route)``. ``component_route`` is only
        set when ``mock_component_ctb`` is true.
    """
    _mock_document_missing(respx_mock, "authors", "auth-src")
    _mock_document_missing(respx_mock, "articles", "art-src")
    respx_mock.post("http://localhost:1337/api/authors").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 9, "documentId": "auth-new", "name": "Ada"}}
        )
    )
    respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "documentId": "art-new", "title": "Hello"}}
        )
    )
    relation_route = respx_mock.put("http://localhost:1337/api/articles/art-new").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "documentId": "art-new", "title": "Hello"}}
        )
    )
    component_route = None
    if mock_component_ctb:
        component_route = respx_mock.get(
            "http://localhost:1337/api/content-type-builder/components/shared.seo"
        ).mock(return_value=httpx.Response(500, json={"error": {"message": "offline dest"}}))
    return relation_route, component_route


@pytest.fixture
def strapi_config() -> StrapiConfig:
    """Create test configuration."""
    return StrapiConfig(
        base_url="http://localhost:1337",
        api_token="test-token",
    )


@pytest.fixture
def sample_export_data() -> ExportData:
    """Create sample export data for testing."""
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "title": FieldSchema(type=FieldType.STRING),
            "content": FieldSchema(type=FieldType.RICH_TEXT),
        },
    )
    metadata = ExportMetadata(
        strapi_version="v5",
        source_url="http://localhost:1337",
        content_types=["api::article.article"],
        total_entities=2,
        schemas={"api::article.article": article_schema},
    )

    entities = {
        "api::article.article": [
            ExportedEntity(
                id=1,
                document_id="doc1",
                content_type="api::article.article",
                data={"title": "Article 1", "content": "Content 1"},
            ),
            ExportedEntity(
                id=2,
                document_id="doc2",
                content_type="api::article.article",
                data={"title": "Article 2", "content": "Content 2"},
            ),
        ]
    }

    return ExportData(metadata=metadata, entities=entities)


@pytest.fixture
def mock_article_schema_response() -> dict:
    """Create mock schema response for articles."""
    return {
        "data": {
            "schema": {
                "displayName": "Article",
                "singularName": "article",
                "pluralName": "articles",
                "kind": "collectionType",
                "attributes": {
                    "title": {"type": "string", "required": True},
                    "content": {"type": "richtext"},
                },
            }
        }
    }


# Export Tests


@pytest.mark.respx
def test_export_content_types(
    strapi_config: StrapiConfig, mock_article_schema_response: dict, respx_mock: respx.Router
) -> None:
    """Test exporting content types."""
    # Mock schema fetch (required for schema-aware relation extraction)
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=httpx.Response(200, json=mock_article_schema_response))

    # Mock paginated response
    respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"id": 1, "documentId": "doc1", "title": "Article 1"},
                    {"id": 2, "documentId": "doc2", "title": "Article 2"},
                ],
                "meta": {
                    "pagination": {
                        "page": 1,
                        "pageSize": 100,
                        "pageCount": 1,
                        "total": 2,
                    }
                },
            },
        )
    )

    with SyncClient(strapi_config) as client:
        exporter = StrapiExporter(client)
        export_data = exporter.export_content_types(["api::article.article"], include_media=False)

        assert isinstance(export_data, ExportData)
        assert len(export_data.entities) == 1
        assert "api::article.article" in export_data.entities
        assert len(export_data.entities["api::article.article"]) == 2
        assert export_data.get_entity_count() == 2


@pytest.mark.respx
def test_export_requests_status_draft(
    strapi_config: StrapiConfig, mock_article_schema_response: dict, respx_mock: respx.Router
) -> None:
    """Exporter inherits streamer completeness (v5 status=draft)."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=httpx.Response(200, json=mock_article_schema_response))
    route = respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 1, "documentId": "doc1", "title": "Draft"}],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )

    with SyncClient(strapi_config) as client:
        StrapiExporter(client).export_content_types(["api::article.article"], include_media=False)

    assert route.calls.last.request.url.params["status"] == "draft"


@pytest.mark.respx
def test_export_published_only_omits_status(
    strapi_config: StrapiConfig, mock_article_schema_response: dict, respx_mock: respx.Router
) -> None:
    """document_status=None is published-only (no status=)."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=httpx.Response(200, json=mock_article_schema_response))
    route = respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 1, "documentId": "doc1", "title": "Live"}],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )

    with SyncClient(strapi_config) as client:
        StrapiExporter(client).export_content_types(
            ["api::article.article"],
            include_media=False,
            document_status=None,
        )

    assert "status" not in route.calls.last.request.url.params


@pytest.mark.respx
def test_export_to_jsonl_requests_status_draft(
    strapi_config: StrapiConfig,
    mock_article_schema_response: dict,
    respx_mock: respx.Router,
    tmp_path: Path,
) -> None:
    """JSONL export uses the same default document_status as in-memory export."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=httpx.Response(200, json=mock_article_schema_response))
    route = respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 1, "documentId": "doc1", "title": "Draft"}],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )

    with SyncClient(strapi_config) as client:
        StrapiExporter(client).export_to_jsonl(
            ["api::article.article"],
            tmp_path / "export.jsonl",
            include_media=False,
        )

    assert route.calls.last.request.url.params["status"] == "draft"


@pytest.mark.respx
def test_export_to_jsonl_published_only_omits_status(
    strapi_config: StrapiConfig,
    mock_article_schema_response: dict,
    respx_mock: respx.Router,
    tmp_path: Path,
) -> None:
    """JSONL export honors document_status=None."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=httpx.Response(200, json=mock_article_schema_response))
    route = respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 1, "documentId": "doc1", "title": "Live"}],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )

    with SyncClient(strapi_config) as client:
        StrapiExporter(client).export_to_jsonl(
            ["api::article.article"],
            tmp_path / "export.jsonl",
            include_media=False,
            document_status=None,
        )

    assert "status" not in route.calls.last.request.url.params


@pytest.mark.respx
def test_export_with_progress_callback(
    strapi_config: StrapiConfig, mock_article_schema_response: dict, respx_mock: respx.Router
) -> None:
    """Test export with progress callback."""
    # Mock schema fetch
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=httpx.Response(200, json=mock_article_schema_response))

    respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 1, "documentId": "doc1", "title": "Article 1"}],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )

    progress_calls = []

    def progress_callback(current: int, total: int, message: str) -> None:
        progress_calls.append((current, total, message))

    with SyncClient(strapi_config) as client:
        exporter = StrapiExporter(client)
        export_data = exporter.export_content_types(
            ["api::article.article"],
            include_media=False,
            progress_callback=progress_callback,
        )

        assert export_data.get_entity_count() == 1
        assert len(progress_calls) >= 2  # At least start and end


@pytest.mark.respx
def test_export_multiple_content_types(
    strapi_config: StrapiConfig, mock_article_schema_response: dict, respx_mock: respx.Router
) -> None:
    """Test exporting multiple content types."""
    # Mock schema fetches
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=httpx.Response(200, json=mock_article_schema_response))

    mock_author_schema = {
        "data": {
            "schema": {
                "displayName": "Author",
                "singularName": "author",
                "pluralName": "authors",
                "kind": "collectionType",
                "attributes": {"name": {"type": "string", "required": True}},
            }
        }
    }
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::author.author"
    ).mock(return_value=httpx.Response(200, json=mock_author_schema))

    respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 1, "documentId": "doc1", "title": "Article 1"}],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )

    respx_mock.get("http://localhost:1337/api/authors").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 1, "documentId": "doc1", "name": "Author 1"}],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )

    with SyncClient(strapi_config) as client:
        exporter = StrapiExporter(client)
        export_data = exporter.export_content_types(
            ["api::article.article", "api::author.author"], include_media=False
        )

        assert len(export_data.entities) == 2
        assert "api::article.article" in export_data.entities
        assert "api::author.author" in export_data.entities


def test_save_and_load_export_file(sample_export_data: ExportData, tmp_path: Path) -> None:
    """Test saving and loading export data."""
    export_file = tmp_path / "test_export.json"

    # Save
    StrapiExporter.save_to_file(sample_export_data, export_file)
    assert export_file.exists()

    # Load
    loaded_data = StrapiExporter.load_from_file(export_file)

    assert isinstance(loaded_data, ExportData)
    assert loaded_data.metadata.strapi_version == sample_export_data.metadata.strapi_version
    assert len(loaded_data.entities) == len(sample_export_data.entities)
    assert loaded_data.get_entity_count() == sample_export_data.get_entity_count()


def test_uid_to_endpoint() -> None:
    """Test UID to endpoint conversion with proper pluralization."""
    assert uid_to_endpoint("api::article.article") == "articles"
    assert uid_to_endpoint("api::author.author") == "authors"
    # Handles irregular plurals correctly
    assert uid_to_endpoint("api::category.category") == "categories"
    assert uid_to_endpoint("api::class.class") == "classes"
    # Uses model name (after dot), not API name (before dot)
    assert uid_to_endpoint("api::blog.post") == "posts"
    assert uid_to_endpoint("api::shop.product") == "products"


# Import Tests


@pytest.mark.respx
def test_import_data_dry_run(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
    respx_mock: respx.Router,
) -> None:
    """Dry-run probes existence but does not write."""
    _mock_document_missing(respx_mock, "articles", "doc1")
    _mock_document_missing(respx_mock, "articles", "doc2")
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )
    with SyncClient(strapi_config) as client:
        importer = StrapiImporter(client)
        options = ImportOptions(dry_run=True)

        result = importer.import_data(sample_export_data, options)

        assert result.dry_run
        assert result.entities_imported == 2
        assert result.entities_failed == 0
        assert create_route.call_count == 0
        assert result.id_mapping == {}
        assert result.doc_id_mapping == {}
        assert result.doc_id_to_new_id == {}
        assert result.doc_id_to_new_document_id == {}


@pytest.mark.respx
def test_import_skip_and_update_dry_run_does_not_write(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
    respx_mock: respx.Router,
) -> None:
    """SKIP/UPDATE dry-run probe existing locales but do not write."""
    respx_mock.get("http://localhost:1337/api/articles/doc1").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 42, "documentId": "doc1", "title": "Old"}}
        )
    )
    _mock_document_missing(respx_mock, "articles", "doc2")
    update_route = respx_mock.put("http://localhost:1337/api/articles/doc1").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not update"}})
    )
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )

    with SyncClient(strapi_config) as client:
        skip_result = StrapiImporter(client).import_data(
            sample_export_data,
            ImportOptions(dry_run=True, conflict_resolution=ConflictResolution.SKIP),
        )
        assert skip_result.entities_skipped == 1
        assert skip_result.entities_imported == 1
        assert update_route.call_count == 0
        assert create_route.call_count == 0
        assert skip_result.id_mapping["api::article.article"] == {1: 42}
        assert 2 not in skip_result.id_mapping["api::article.article"]
        assert 0 not in skip_result.id_mapping["api::article.article"].values()
        assert skip_result.doc_id_mapping["api::article.article"] == {1: "doc1"}
        assert skip_result.doc_id_to_new_id["api::article.article"] == {"doc1": 42}
        assert skip_result.doc_id_to_new_document_id["api::article.article"] == {"doc1": "doc1"}

        update_result = StrapiImporter(client).import_data(
            sample_export_data,
            ImportOptions(dry_run=True, conflict_resolution=ConflictResolution.UPDATE),
        )
        assert update_result.entities_updated == 1
        assert update_result.entities_imported == 1
        assert update_route.call_count == 0
        assert create_route.call_count == 0
        assert update_result.id_mapping["api::article.article"] == {1: 42}
        assert 2 not in update_result.id_mapping["api::article.article"]
        assert 0 not in update_result.id_mapping["api::article.article"].values()
        assert update_result.doc_id_mapping["api::article.article"] == {1: "doc1"}
        assert update_result.doc_id_to_new_id["api::article.article"] == {"doc1": 42}
        assert update_result.doc_id_to_new_document_id["api::article.article"] == {"doc1": "doc1"}


@pytest.mark.respx
def test_import_skip_dry_run_does_not_map_source_document_id_without_dest_doc(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
    respx_mock: respx.Router,
) -> None:
    """Existing dest without documentId must not record the source id as dest (#131)."""
    respx_mock.get("http://localhost:1337/api/articles/doc1").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": 42, "attributes": {"title": "Old"}}},
        )
    )
    _mock_document_missing(respx_mock, "articles", "doc2")

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(
            sample_export_data,
            ImportOptions(dry_run=True, conflict_resolution=ConflictResolution.SKIP),
        )

    assert result.entities_skipped == 1
    assert result.id_mapping["api::article.article"] == {1: 42}
    assert 1 not in result.doc_id_mapping.get("api::article.article", {})
    assert "doc1" not in result.doc_id_to_new_document_id.get("api::article.article", {})
    assert result.doc_id_to_new_id["api::article.article"] == {"doc1": 42}


@pytest.mark.respx
def test_import_data_creates_entities(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
    respx_mock: respx.Router,
) -> None:
    """Test import actually creates entities."""
    _mock_document_missing(respx_mock, "articles", "doc1")
    _mock_document_missing(respx_mock, "articles", "doc2")
    # Mock create responses
    respx_mock.post("http://localhost:1337/api/articles").mock(
        side_effect=[
            httpx.Response(
                200,
                json={"data": {"id": 10, "documentId": "new_doc1", "title": "Article 1"}},
            ),
            httpx.Response(
                200,
                json={"data": {"id": 11, "documentId": "new_doc2", "title": "Article 2"}},
            ),
        ]
    )

    with SyncClient(strapi_config) as client:
        importer = StrapiImporter(client)
        result = importer.import_data(sample_export_data)

        assert not result.dry_run
        assert result.entities_imported == 2
        assert result.entities_failed == 0
        assert result.success

        # Check ID mapping
        assert "api::article.article" in result.id_mapping
        assert result.id_mapping["api::article.article"][1] == 10
        assert result.id_mapping["api::article.article"][2] == 11


@pytest.mark.respx
def test_import_with_validation_error(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
    respx_mock: respx.Router,
) -> None:
    """Test import handles validation errors."""
    _mock_document_missing(respx_mock, "articles", "doc1")
    _mock_document_missing(respx_mock, "articles", "doc2")
    # First succeeds, second fails
    respx_mock.post("http://localhost:1337/api/articles").mock(
        side_effect=[
            httpx.Response(
                200,
                json={"data": {"id": 10, "documentId": "new_doc1"}},
            ),
            httpx.Response(
                400,
                json={"error": {"message": "Validation failed"}},
            ),
        ]
    )

    with SyncClient(strapi_config) as client:
        importer = StrapiImporter(client)
        result = importer.import_data(sample_export_data)

        assert result.entities_imported == 1
        assert result.entities_failed == 1
        assert not result.success
        assert len(result.errors) > 0


@pytest.mark.respx
def test_import_with_progress_callback(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
    respx_mock: respx.Router,
) -> None:
    """Test import with progress callback."""
    _mock_document_missing(respx_mock, "articles", "doc1")
    _mock_document_missing(respx_mock, "articles", "doc2")
    respx_mock.post("http://localhost:1337/api/articles").mock(
        side_effect=[
            httpx.Response(200, json={"data": {"id": 10, "documentId": "doc1"}}),
            httpx.Response(200, json={"data": {"id": 11, "documentId": "doc2"}}),
        ]
    )

    progress_calls = []

    def progress_callback(current: int, total: int, message: str) -> None:
        progress_calls.append((current, total, message))

    with SyncClient(strapi_config) as client:
        importer = StrapiImporter(client)
        options = ImportOptions(progress_callback=progress_callback)

        result = importer.import_data(sample_export_data, options)

        assert result.success
        assert len(progress_calls) >= 2  # At least validation and completion


@pytest.mark.respx
def test_import_validation_warns_on_version_mismatch(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
    respx_mock: respx.Router,
) -> None:
    """Test import validation warns about version mismatches."""
    # Modify export data to have different version
    sample_export_data.metadata.strapi_version = "v4"
    _mock_document_missing(respx_mock, "articles", "doc1")
    _mock_document_missing(respx_mock, "articles", "doc2")

    config = StrapiConfig(
        base_url=strapi_config.base_url,
        api_token=strapi_config.api_token,
        api_version="v5",
    )

    with SyncClient(config) as client:
        importer = StrapiImporter(client)
        options = ImportOptions(dry_run=True)

        result = importer.import_data(sample_export_data, options)

        # Should have warning about version mismatch
        assert any("version" in warning.lower() for warning in result.warnings)


@pytest.mark.respx
def test_import_skips_existing_draft_document(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
    respx_mock: respx.Router,
) -> None:
    """Draft-only documents must not be treated as missing (no second create)."""

    def articles_doc1(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("status") == "draft":
            return httpx.Response(
                200,
                json={"data": {"id": 42, "documentId": "doc1", "title": "Draft"}},
            )
        return httpx.Response(404, json={"error": {"status": 404, "message": "Not found"}})

    respx_mock.get("http://localhost:1337/api/articles/doc1").mock(side_effect=articles_doc1)
    _mock_document_missing(respx_mock, "articles", "doc2")
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": 11, "documentId": "new_doc2", "title": "Article 2"}},
        )
    )

    with SyncClient(strapi_config) as client:
        importer = StrapiImporter(client)
        result = importer.import_data(
            sample_export_data,
            ImportOptions(conflict_resolution=ConflictResolution.SKIP),
        )

    assert result.entities_skipped == 1
    assert result.entities_imported == 1
    assert result.id_mapping["api::article.article"][1] == 42
    assert create_route.call_count == 1


@pytest.mark.respx
def test_import_existence_auth_error_does_not_create(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
    respx_mock: respx.Router,
) -> None:
    """A 401 on the existence probe must not look like a missing document."""
    respx_mock.get("http://localhost:1337/api/articles/doc1").mock(
        return_value=httpx.Response(401, json={"error": {"message": "Unauthorized"}})
    )
    _mock_document_missing(respx_mock, "articles", "doc2")
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": 11, "documentId": "new_doc2", "title": "Article 2"}},
        )
    )

    with SyncClient(strapi_config) as client:
        importer = StrapiImporter(client)
        result = importer.import_data(sample_export_data)

    assert result.entities_failed == 1
    assert result.entities_imported == 1
    assert not result.success
    assert create_route.call_count == 1


@pytest.mark.respx
def test_import_from_jsonl_fail_aborts_on_existing(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
    respx_mock: respx.Router,
    tmp_path: Path,
) -> None:
    """JSONL ConflictResolution.FAIL must abort, not record a per-entity error."""
    jsonl_path = tmp_path / "export.jsonl"
    with JSONLExportWriter(jsonl_path) as writer:
        writer.write_metadata(sample_export_data.metadata)
        for entity in sample_export_data.entities["api::article.article"]:
            writer.write_entity(entity)

    respx_mock.get("http://localhost:1337/api/articles/doc1").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": 42, "documentId": "doc1", "title": "Live"}},
        )
    )
    _mock_document_missing(respx_mock, "articles", "doc2")
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": 11, "documentId": "new_doc2", "title": "Article 2"}},
        )
    )

    with SyncClient(strapi_config) as client:
        importer = StrapiImporter(client)
        with pytest.raises(ImportExportError, match="already exists"):
            importer.import_from_jsonl(
                jsonl_path,
                ImportOptions(conflict_resolution=ConflictResolution.FAIL),
            )

    assert create_route.call_count == 1


@pytest.mark.respx
def test_import_from_jsonl_skip_records_document_id_mapping(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
    respx_mock: respx.Router,
    tmp_path: Path,
) -> None:
    """JSONL SKIP must record dest documentIds for relation resolution."""
    jsonl_path = tmp_path / "export.jsonl"
    with JSONLExportWriter(jsonl_path) as writer:
        writer.write_metadata(sample_export_data.metadata)
        for entity in sample_export_data.entities["api::article.article"]:
            writer.write_entity(entity)

    respx_mock.get("http://localhost:1337/api/articles/doc1").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 42, "documentId": "doc1", "title": "Live"}}
        )
    )
    _mock_document_missing(respx_mock, "articles", "doc2")
    respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 11, "documentId": "new_doc2", "title": "Article 2"}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_from_jsonl(
            jsonl_path,
            ImportOptions(conflict_resolution=ConflictResolution.SKIP),
        )

    assert result.entities_skipped == 1
    assert result.entities_imported == 1
    assert result.doc_id_to_new_document_id["api::article.article"]["doc1"] == "doc1"
    assert result.doc_id_to_new_document_id["api::article.article"]["doc2"] == "new_doc2"


@pytest.mark.respx
def test_import_skip_and_update_conflicts(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
    respx_mock: respx.Router,
) -> None:
    """SKIP leaves the existing row; UPDATE writes over it."""
    respx_mock.get("http://localhost:1337/api/articles/doc1").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 42, "documentId": "doc1", "title": "Old"}}
        )
    )
    _mock_document_missing(respx_mock, "articles", "doc2")
    update_route = respx_mock.put("http://localhost:1337/api/articles/doc1").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 42, "documentId": "doc1", "title": "Article 1"}}
        )
    )
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 11, "documentId": "new_doc2", "title": "Article 2"}}
        )
    )

    with SyncClient(strapi_config) as client:
        skip_result = StrapiImporter(client).import_data(
            sample_export_data,
            ImportOptions(conflict_resolution=ConflictResolution.SKIP),
        )
        assert skip_result.entities_skipped == 1
        assert skip_result.entities_imported == 1
        assert update_route.call_count == 0
        assert skip_result.doc_id_to_new_document_id["api::article.article"]["doc1"] == "doc1"
        assert skip_result.doc_id_to_new_document_id["api::article.article"]["doc2"] == "new_doc2"

        update_result = StrapiImporter(client).import_data(
            sample_export_data,
            ImportOptions(conflict_resolution=ConflictResolution.UPDATE),
        )
        assert update_result.entities_updated == 1
        assert update_result.entities_imported == 1
        assert update_route.call_count == 1
        assert create_route.call_count == 2
        assert update_result.doc_id_to_new_document_id["api::article.article"]["doc1"] == "doc1"


@pytest.mark.respx
def test_import_skip_resolves_relations_via_document_id_mapping(
    strapi_config: StrapiConfig,
    respx_mock: respx.Router,
) -> None:
    """SKIP must record dest documentIds so relation writes do not miss."""
    author_schema = ContentTypeSchema(
        uid="api::author.author",
        display_name="Author",
        plural_name="authors",
        fields={"name": FieldSchema(type=FieldType.STRING)},
    )
    article_schema = ContentTypeSchema(
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
        },
    )
    export_data = ExportData(
        metadata=ExportMetadata(
            strapi_version="v5",
            source_url="http://localhost:1337",
            content_types=["api::author.author", "api::article.article"],
            total_entities=2,
            schemas={
                "api::author.author": author_schema,
                "api::article.article": article_schema,
            },
        ),
        entities={
            "api::author.author": [
                ExportedEntity(
                    id=1,
                    document_id="auth-src",
                    content_type="api::author.author",
                    data={"name": "Ada"},
                )
            ],
            "api::article.article": [
                ExportedEntity(
                    id=2,
                    document_id="art-src",
                    content_type="api::article.article",
                    data={"title": "Hello"},
                    relations={"author": ["auth-src"]},
                )
            ],
        },
    )
    respx_mock.get("http://localhost:1337/api/authors/auth-src").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 9, "documentId": "auth-src", "name": "Ada"}}
        )
    )
    _mock_document_missing(respx_mock, "articles", "art-src")
    respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "documentId": "art-new", "title": "Hello"}}
        )
    )
    relation_route = respx_mock.put("http://localhost:1337/api/articles/art-new").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "documentId": "art-new", "title": "Hello"}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(
            export_data,
            ImportOptions(conflict_resolution=ConflictResolution.SKIP),
        )

    assert result.success is True
    assert result.entities_skipped == 1
    assert result.entities_imported == 1
    assert result.relations_imported == 1
    assert relation_route.called
    import json

    body = json.loads(relation_route.calls.last.request.content)
    assert body["data"]["author"] == "auth-src"


@pytest.mark.respx
def test_import_existence_unrelated_400_does_not_look_missing(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
    respx_mock: respx.Router,
) -> None:
    """A populate/filter 400 on the draft probe must not create a second document."""

    def articles_doc1(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("status") == "draft":
            return httpx.Response(
                400,
                json={"error": {"status": 400, "message": "Invalid key populate"}},
            )
        return httpx.Response(404, json={"error": {"status": 404, "message": "Not found"}})

    respx_mock.get("http://localhost:1337/api/articles/doc1").mock(side_effect=articles_doc1)
    _mock_document_missing(respx_mock, "articles", "doc2")
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": 11, "documentId": "new_doc2", "title": "Article 2"}},
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(sample_export_data)

    assert result.entities_failed == 1
    assert result.entities_imported == 1
    assert not result.success
    assert create_route.call_count == 1


@pytest.mark.respx
def test_import_publishes_when_source_was_live(
    strapi_config: StrapiConfig,
    respx_mock: respx.Router,
) -> None:
    """A live source document must be published after create."""
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={"title": FieldSchema(type=FieldType.STRING)},
    )
    export_data = ExportData(
        metadata=ExportMetadata(
            strapi_version="v5",
            source_url="http://localhost:1337",
            content_types=["api::article.article"],
            total_entities=1,
            schemas={"api::article.article": article_schema},
        ),
        entities={
            "api::article.article": [
                ExportedEntity(
                    id=1,
                    document_id="doc-live",
                    content_type="api::article.article",
                    data={"title": "Live"},
                    published_at=datetime(2026, 8, 16, 12, 0, 0),
                    locale="en",
                )
            ]
        },
    )
    _mock_document_missing(respx_mock, "articles", "doc-live")
    respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 3, "documentId": "doc-new", "title": "Live"}}
        )
    )
    publish_route = respx_mock.put("http://localhost:1337/api/articles/doc-new").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 3, "documentId": "doc-new", "title": "Live"}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(export_data)

    assert result.success is True
    assert result.entities_imported == 1
    assert publish_route.call_count == 1
    assert publish_route.calls.last.request.url.params["status"] == "published"
    assert publish_route.calls.last.request.url.params["locale"] == "en"


@pytest.mark.respx
def test_import_publishes_after_relation_write(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Stock v5 relation PUT must run before publish, or live docs lose links."""
    author_schema = ContentTypeSchema(
        uid="api::author.author",
        display_name="Author",
        plural_name="authors",
        fields={"name": FieldSchema(type=FieldType.STRING)},
    )
    article_schema = ContentTypeSchema(
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
        },
    )
    export_data = ExportData(
        metadata=ExportMetadata(
            strapi_version="v5",
            source_url="http://localhost:1337",
            content_types=["api::author.author", "api::article.article"],
            total_entities=2,
            schemas={
                "api::author.author": author_schema,
                "api::article.article": article_schema,
            },
        ),
        entities={
            "api::author.author": [
                ExportedEntity(
                    id=1,
                    document_id="auth-src",
                    content_type="api::author.author",
                    data={"name": "Ada"},
                    published_at=datetime(2026, 8, 16, 12, 0, 0),
                )
            ],
            "api::article.article": [
                ExportedEntity(
                    id=2,
                    document_id="art-src",
                    content_type="api::article.article",
                    data={"title": "Hello"},
                    relations={"author": ["auth-src"]},
                    published_at=datetime(2026, 8, 16, 12, 0, 0),
                )
            ],
        },
    )
    _mock_document_missing(respx_mock, "authors", "auth-src")
    _mock_document_missing(respx_mock, "articles", "art-src")
    respx_mock.post("http://localhost:1337/api/authors").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 9, "documentId": "auth-new", "name": "Ada"}}
        )
    )
    respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "documentId": "art-new", "title": "Hello"}}
        )
    )
    relation_route = respx_mock.put("http://localhost:1337/api/articles/art-new").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "documentId": "art-new", "title": "Hello"}}
        )
    )
    respx_mock.put("http://localhost:1337/api/authors/auth-new").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 9, "documentId": "auth-new", "name": "Ada"}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(export_data)

    assert result.success is True
    assert result.relations_imported == 1
    relation_idx = None
    publish_idx = None
    for index, call in enumerate(relation_route.calls):
        if call.request.url.params.get("status") == "published":
            publish_idx = index
        else:
            relation_idx = index
    assert relation_idx is not None
    assert publish_idx is not None
    assert relation_idx < publish_idx


@pytest.mark.respx
def test_export_retries_without_locale_on_invalid_key(
    strapi_config: StrapiConfig, mock_article_schema_response: dict, respx_mock: respx.Router
) -> None:
    """Non-i18n types that reject locale=* / locale=all are retried without locale."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=httpx.Response(200, json=mock_article_schema_response))

    def articles(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("locale") in {"all", "*"}:
            return httpx.Response(
                400, json={"error": {"status": 400, "message": "Invalid key locale"}}
            )
        return httpx.Response(
            200,
            json={
                "data": [{"id": 1, "documentId": "doc1", "title": "One"}],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )

    route = respx_mock.get("http://localhost:1337/api/articles").mock(side_effect=articles)

    with SyncClient(strapi_config) as client:
        export_data = StrapiExporter(client).export_content_types(
            ["api::article.article"], include_media=False
        )

    assert route.call_count == 3
    assert route.calls[0].request.url.params["locale"] == "*"
    assert route.calls[1].request.url.params["locale"] == "all"
    assert "locale" not in route.calls[2].request.url.params
    assert export_data.get_entity_count() == 1


@pytest.mark.respx
def test_export_does_not_drop_locale_on_unrelated_400(
    strapi_config: StrapiConfig, mock_article_schema_response: dict, respx_mock: respx.Router
) -> None:
    """A populate/filter 400 must not silently retry as locale-less."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=httpx.Response(200, json=mock_article_schema_response))
    respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            400, json={"error": {"status": 400, "message": "Invalid key populate"}}
        )
    )

    with SyncClient(strapi_config) as client:
        with pytest.raises(ImportExportError, match="Invalid key populate"):
            StrapiExporter(client).export_content_types(
                ["api::article.article"], include_media=False
            )


@pytest.mark.respx
def test_export_records_published_at_and_locale(
    strapi_config: StrapiConfig, mock_article_schema_response: dict, respx_mock: respx.Router
) -> None:
    """Export format 1.1.0 must keep publishedAt and locale from the stream."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(return_value=httpx.Response(200, json=mock_article_schema_response))
    respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 1,
                        "documentId": "doc1",
                        "title": "Live",
                        "locale": "fr",
                        "publishedAt": "2026-08-16T12:00:00.000Z",
                        "localizations": [],
                    }
                ],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )

    with SyncClient(strapi_config) as client:
        export_data = StrapiExporter(client).export_content_types(
            ["api::article.article"], include_media=False
        )

    entity = export_data.entities["api::article.article"][0]
    assert entity.locale == "fr"
    assert entity.published_at is not None
    assert "localizations" not in entity.data


@pytest.mark.respx
def test_export_extracts_flat_v5_populate_relations(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Live export must send populate=* / locale=* and store documentIds."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "schema": {
                        "displayName": "Article",
                        "singularName": "article",
                        "pluralName": "articles",
                        "kind": "collectionType",
                        "attributes": {
                            "title": {"type": "string"},
                            "author": {
                                "type": "relation",
                                "relation": "manyToOne",
                                "target": "api::author.author",
                            },
                            "categories": {
                                "type": "relation",
                                "relation": "manyToMany",
                                "target": "api::category.category",
                            },
                        },
                    }
                }
            },
        )
    )
    route = respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": 1,
                        "documentId": "art1",
                        "title": "Hello",
                        "author": {"id": 9, "documentId": "auth-doc", "name": "Ada"},
                        "categories": [
                            {"id": 2, "documentId": "cat-a", "name": "A"},
                            {"id": 3, "documentId": "cat-b", "name": "B"},
                        ],
                    }
                ],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )

    with SyncClient(strapi_config) as client:
        export_data = StrapiExporter(client).export_content_types(
            ["api::article.article"], include_media=False
        )

    params = route.calls.last.request.url.params
    assert params["populate"] == "*"
    assert params["locale"] == "*"
    entity = export_data.entities["api::article.article"][0]
    assert entity.relations["author"] == ["auth-doc"]
    assert entity.relations["categories"] == ["cat-a", "cat-b"]
    assert "author" not in entity.data
    assert "categories" not in entity.data
    assert entity.data["title"] == "Hello"


@pytest.mark.respx
def test_import_writes_many_side_relation_set(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Many-side v5 writes must use {set: [documentIds]}, not a bare string."""
    category_schema = ContentTypeSchema(
        uid="api::category.category",
        display_name="Category",
        plural_name="categories",
        fields={"name": FieldSchema(type=FieldType.STRING)},
    )
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "title": FieldSchema(type=FieldType.STRING),
            "categories": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_MANY,
                target="api::category.category",
            ),
        },
    )
    export_data = ExportData(
        metadata=ExportMetadata(
            strapi_version="v5",
            source_url="http://localhost:1337",
            content_types=["api::category.category", "api::article.article"],
            total_entities=3,
            schemas={
                "api::category.category": category_schema,
                "api::article.article": article_schema,
            },
        ),
        entities={
            "api::category.category": [
                ExportedEntity(
                    id=1,
                    document_id="cat-a",
                    content_type="api::category.category",
                    data={"name": "A"},
                ),
                ExportedEntity(
                    id=2,
                    document_id="cat-b",
                    content_type="api::category.category",
                    data={"name": "B"},
                ),
            ],
            "api::article.article": [
                ExportedEntity(
                    id=3,
                    document_id="art1",
                    content_type="api::article.article",
                    data={"title": "Hello"},
                    relations={"categories": ["cat-a", "cat-b"]},
                )
            ],
        },
    )
    _mock_document_missing(respx_mock, "categories", "cat-a")
    _mock_document_missing(respx_mock, "categories", "cat-b")
    _mock_document_missing(respx_mock, "articles", "art1")
    respx_mock.post("http://localhost:1337/api/categories").mock(
        side_effect=[
            httpx.Response(200, json={"data": {"id": 10, "documentId": "new-a", "name": "A"}}),
            httpx.Response(200, json={"data": {"id": 11, "documentId": "new-b", "name": "B"}}),
        ]
    )
    respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "documentId": "new-art", "title": "Hello"}}
        )
    )
    relation_route = respx_mock.put("http://localhost:1337/api/articles/new-art").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "documentId": "new-art", "title": "Hello"}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(export_data)

    assert result.success is True
    assert result.relations_imported == 1
    import json

    body = json.loads(relation_route.calls.last.request.content)
    assert body["data"]["categories"] == {"set": ["new-a", "new-b"]}


@pytest.mark.respx
def test_export_uses_schema_plural_name_not_uid(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Irregular pluralName must win over UID pluralization."""
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::post.post"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "schema": {
                        "displayName": "Post",
                        "singularName": "post",
                        "pluralName": "blog-posts",
                        "kind": "collectionType",
                        "attributes": {"title": {"type": "string"}},
                    }
                }
            },
        )
    )
    posts_route = respx_mock.get("http://localhost:1337/api/blog-posts").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 1, "documentId": "p1", "title": "Hello"}],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )
    uid_route = respx_mock.get("http://localhost:1337/api/posts").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not be called"}})
    )

    with SyncClient(strapi_config) as client:
        export_data = StrapiExporter(client).export_content_types(
            ["api::post.post"], include_media=False
        )

    assert posts_route.called
    assert uid_route.call_count == 0
    assert export_data.get_entity_count() == 1


def test_extract_relations_v5_flat_objects() -> None:
    """Schema extract must read documentId on flat v5 populate objects."""
    from strapi_kit.export.relation_resolver import RelationResolver

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
            "categories": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_MANY,
                target="api::category.category",
            ),
            "title": FieldSchema(type=FieldType.STRING),
        },
    )
    data = {
        "title": "Hello",
        "author": {"id": 1, "documentId": "auth-doc", "name": "Ada"},
        "categories": [
            {"id": 2, "documentId": "cat-a", "name": "A"},
            {"id": 3, "documentId": "cat-b", "name": "B"},
        ],
    }
    relations = RelationResolver.extract_relations_with_schema(data, schema)
    assert relations["author"] == ["auth-doc"]
    assert relations["categories"] == ["cat-a", "cat-b"]
    stripped = RelationResolver.strip_relations_with_schema(data, schema)
    assert "author" not in stripped
    assert "categories" not in stripped
    assert stripped["title"] == "Hello"


def test_extract_relations_v4_wrapper_still_works() -> None:
    """v4 {data: {id}} populate must still extract after the v5 unwrap change."""
    from strapi_kit.export.relation_resolver import RelationResolver

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
            "title": FieldSchema(type=FieldType.STRING),
        },
    )
    data = {
        "title": "Hello",
        "author": {"data": {"id": 5, "attributes": {"name": "Ada"}}},
    }
    relations = RelationResolver.extract_relations_with_schema(data, schema)
    assert relations["author"] == [5]


def test_exporter_requires_schema(strapi_config: StrapiConfig) -> None:
    """Export must not invent a collection path from the UID."""
    from strapi_kit.exceptions import ImportExportError

    with SyncClient(strapi_config) as client:
        exporter = StrapiExporter(client)
        with pytest.raises(ImportExportError, match="pluralName"):
            exporter._get_endpoint("api::article.article")


# Model Tests


def test_export_metadata_model() -> None:
    """Test ExportMetadata model."""
    metadata = ExportMetadata(
        strapi_version="v5",
        source_url="http://localhost:1337",
        content_types=["api::article.article"],
        total_entities=10,
    )

    assert metadata.version == "1.1.0"
    assert metadata.strapi_version == "v5"
    assert isinstance(metadata.exported_at, datetime)


def test_exported_entity_model() -> None:
    """Test ExportedEntity model."""
    entity = ExportedEntity(
        id=1,
        document_id="doc1",
        content_type="api::article.article",
        data={"title": "Test"},
        relations={"author": [5]},
    )

    assert entity.id == 1
    assert entity.data["title"] == "Test"
    assert entity.relations["author"] == [5]


def test_exported_media_file_path_traversal_rejected() -> None:
    """Test that path traversal attempts are rejected in media file paths."""
    # Path with parent directory traversal
    with pytest.raises(FormatError) as exc_info:
        ExportedMediaFile(
            id=1,
            url="/uploads/image.jpg",
            name="image.jpg",
            mime="image/jpeg",
            size=1024,
            hash="abc123",
            local_path="../../../etc/passwd",
        )
    assert "path traversal" in str(exc_info.value).lower()

    # Absolute path starting with /
    with pytest.raises(FormatError) as exc_info:
        ExportedMediaFile(
            id=2,
            url="/uploads/image.jpg",
            name="image.jpg",
            mime="image/jpeg",
            size=1024,
            hash="def456",
            local_path="/etc/passwd",
        )
    assert "path traversal" in str(exc_info.value).lower()

    # Windows-style absolute path
    with pytest.raises(FormatError) as exc_info:
        ExportedMediaFile(
            id=3,
            url="/uploads/image.jpg",
            name="image.jpg",
            mime="image/jpeg",
            size=1024,
            hash="ghi789",
            local_path="\\windows\\system32\\config",
        )
    assert "path traversal" in str(exc_info.value).lower()


def test_exported_media_file_windows_drive_path_rejected() -> None:
    """Test that Windows drive-letter absolute paths are rejected."""
    # Windows drive-letter path (C:\)
    with pytest.raises(FormatError) as exc_info:
        ExportedMediaFile(
            id=4,
            url="/uploads/image.jpg",
            name="image.jpg",
            mime="image/jpeg",
            size=1024,
            hash="jkl012",
            local_path="C:\\Windows\\System32\\config.sys",
        )
    assert "path traversal" in str(exc_info.value).lower()

    # Windows drive-letter with forward slashes
    with pytest.raises(FormatError) as exc_info:
        ExportedMediaFile(
            id=5,
            url="/uploads/image.jpg",
            name="image.jpg",
            mime="image/jpeg",
            size=1024,
            hash="mno345",
            local_path="D:/Data/secrets.txt",
        )
    assert "path traversal" in str(exc_info.value).lower()


def test_exported_media_file_valid_paths() -> None:
    """Test that valid relative paths are accepted."""
    # Simple filename
    media1 = ExportedMediaFile(
        id=1,
        url="/uploads/image.jpg",
        name="image.jpg",
        mime="image/jpeg",
        size=1024,
        hash="abc123",
        local_path="image.jpg",
    )
    assert media1.local_path == "image.jpg"

    # Nested relative path
    media2 = ExportedMediaFile(
        id=2,
        url="/uploads/photos/image.jpg",
        name="image.jpg",
        mime="image/jpeg",
        size=1024,
        hash="def456",
        local_path="photos/image.jpg",
    )
    assert media2.local_path == "photos/image.jpg"


def test_import_result_helpers() -> None:
    """Test ImportResult helper methods."""
    from strapi_kit.models import ImportResult

    result = ImportResult(success=True, dry_run=False)
    result.entities_imported = 10
    result.entities_skipped = 2
    result.entities_failed = 1

    assert result.get_total_processed() == 13

    result.add_error("Test error")
    result.add_warning("Test warning")

    assert len(result.errors) == 1
    assert len(result.warnings) == 1


# Schema Export/Import Tests


@pytest.mark.respx
def test_export_includes_schemas(strapi_config: StrapiConfig, respx_mock: respx.Router) -> None:
    """Test that export always includes schemas for relation resolution."""
    # Mock entity response
    respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 1, "documentId": "doc1", "title": "Article 1"}],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )

    # Mock schema response
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "kind": "collectionType",
                    "info": {
                        "displayName": "Article",
                        "singularName": "article",
                        "pluralName": "articles",
                    },
                    "attributes": {
                        "title": {"type": "string", "required": True},
                        "author": {
                            "type": "relation",
                            "relation": "manyToOne",
                            "target": "api::author.author",
                        },
                    },
                }
            },
        )
    )

    with SyncClient(strapi_config) as client:
        exporter = StrapiExporter(client)
        export_data = exporter.export_content_types(["api::article.article"], include_media=False)

        # Verify schemas are always included
        assert "api::article.article" in export_data.metadata.schemas
        schema = export_data.metadata.schemas["api::article.article"]
        assert schema.uid == "api::article.article"
        assert schema.display_name == "Article"
        assert "title" in schema.fields
        assert "author" in schema.fields


@pytest.mark.respx
def test_export_includes_walked_component_schemas(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Export metadata includes component schemas referenced by the type (#118)."""
    respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 0}},
            },
        )
    )
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "kind": "collectionType",
                    "info": {
                        "displayName": "Article",
                        "singularName": "article",
                        "pluralName": "articles",
                    },
                    "attributes": {
                        "title": {"type": "string"},
                        "seo": {
                            "type": "component",
                            "component": "shared.seo",
                            "repeatable": True,
                        },
                    },
                }
            },
        )
    )
    respx_mock.get("http://localhost:1337/api/content-type-builder/components/shared.seo").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "uid": "shared.seo",
                    "info": {"displayName": "SEO"},
                    "attributes": {
                        "metaTitle": {"type": "string"},
                        "author": {
                            "type": "relation",
                            "relation": "manyToOne",
                            "target": "api::author.author",
                        },
                    },
                }
            },
        )
    )

    with SyncClient(strapi_config) as client:
        export_data = StrapiExporter(client).export_content_types(
            ["api::article.article"], include_media=False
        )

    assert "shared.seo" in export_data.metadata.component_schemas
    seo = export_data.metadata.component_schemas["shared.seo"]
    assert seo.fields["author"].target == "api::author.author"


@pytest.mark.respx
def test_export_component_schemas_scoped_to_current_export(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Reused exporter metadata only includes components walked this call."""
    empty_collection = {
        "data": [],
        "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 0}},
    }
    respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(200, json=empty_collection)
    )
    respx_mock.get("http://localhost:1337/api/authors").mock(
        return_value=httpx.Response(200, json=empty_collection)
    )
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "kind": "collectionType",
                    "info": {
                        "displayName": "Article",
                        "singularName": "article",
                        "pluralName": "articles",
                    },
                    "attributes": {
                        "seo": {
                            "type": "component",
                            "component": "shared.seo",
                            "repeatable": True,
                        },
                    },
                }
            },
        )
    )
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::author.author"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "kind": "collectionType",
                    "info": {
                        "displayName": "Author",
                        "singularName": "author",
                        "pluralName": "authors",
                    },
                    "attributes": {"name": {"type": "string"}},
                }
            },
        )
    )
    respx_mock.get("http://localhost:1337/api/content-type-builder/components/shared.seo").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "uid": "shared.seo",
                    "info": {"displayName": "SEO"},
                    "attributes": {"metaTitle": {"type": "string"}},
                }
            },
        )
    )

    with SyncClient(strapi_config) as client:
        exporter = StrapiExporter(client)
        first = exporter.export_content_types(["api::article.article"], include_media=False)
        second = exporter.export_content_types(["api::author.author"], include_media=False)

    assert "shared.seo" in first.metadata.component_schemas
    assert "shared.seo" not in second.metadata.component_schemas


@pytest.mark.respx
def test_prefetch_component_error_not_relabeled_as_plural_name(
    strapi_config: StrapiConfig, respx_mock: respx.Router, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Component prefetch failures keep their own error, not a pluralName wrap."""
    respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 0}},
            },
        )
    )
    respx_mock.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "kind": "collectionType",
                    "info": {
                        "displayName": "Article",
                        "singularName": "article",
                        "pluralName": "articles",
                    },
                    "attributes": {"title": {"type": "string"}},
                }
            },
        )
    )

    def boom(self: object, schema: object) -> set[str]:
        raise ValueError("component parse failed")

    monkeypatch.setattr(
        "strapi_kit.cache.schema_cache.InMemorySchemaCache.prefetch_components", boom
    )

    with SyncClient(strapi_config) as client:
        with pytest.raises(ImportExportError, match="component parse failed") as exc_info:
            StrapiExporter(client).export_content_types(
                ["api::article.article"], include_media=False
            )
    assert "pluralName" not in str(exc_info.value)


@pytest.mark.respx
def test_import_nested_relation_uses_exported_component_schemas(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Nested write works from export component_schemas; dest CTB is not called (#118)."""
    import json

    export_data = _nested_component_export()
    relation_route, component_route = _mock_nested_component_writes(
        respx_mock, mock_component_ctb=True
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(export_data)

    assert result.success is True
    assert result.relations_imported == 1
    assert component_route is not None
    assert component_route.call_count == 0
    body = json.loads(relation_route.calls.last.request.content)
    assert body["data"]["seo"][0]["author"] == "auth-new"


@pytest.mark.respx
def test_import_from_jsonl_uses_exported_component_schemas(
    strapi_config: StrapiConfig, respx_mock: respx.Router, tmp_path: Path
) -> None:
    """JSONL import caches metadata.component_schemas; dest CTB is not called."""
    import json

    jsonl_path = tmp_path / "export.jsonl"
    _write_nested_component_jsonl(jsonl_path)
    relation_route, component_route = _mock_nested_component_writes(
        respx_mock, mock_component_ctb=True
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_from_jsonl(jsonl_path)

    assert result.success is True
    assert result.relations_imported == 1
    assert component_route is not None
    assert component_route.call_count == 0
    body = json.loads(relation_route.calls.last.request.content)
    assert body["data"]["seo"][0]["author"] == "auth-new"


@pytest.mark.respx
def test_import_resolves_relations_with_schema(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Test that import resolves relations correctly using schemas."""
    from strapi_kit.models.schema import ContentTypeSchema, FieldSchema, FieldType, RelationType

    # Create export data with schemas
    article_schema = ContentTypeSchema(
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
        },
    )

    author_schema = ContentTypeSchema(
        uid="api::author.author",
        display_name="Author",
        plural_name="authors",
        fields={
            "name": FieldSchema(type=FieldType.STRING),
        },
    )

    metadata = ExportMetadata(
        strapi_version="v5",
        source_url="http://localhost:1337",
        content_types=["api::author.author", "api::article.article"],
        total_entities=2,
        schemas={
            "api::article.article": article_schema,
            "api::author.author": author_schema,
        },
    )

    entities = {
        "api::author.author": [
            ExportedEntity(
                id=5,
                document_id="author-doc1",
                content_type="api::author.author",
                data={"name": "John Doe"},
                relations={},
            )
        ],
        "api::article.article": [
            ExportedEntity(
                id=1,
                document_id="article-doc1",
                content_type="api::article.article",
                data={"title": "Article 1"},
                relations={"author": [5]},  # Relation to author ID 5
            )
        ],
    }

    export_data = ExportData(metadata=metadata, entities=entities)

    _mock_document_missing(respx_mock, "authors", "author-doc1")
    _mock_document_missing(respx_mock, "articles", "article-doc1")

    # Mock author creation
    respx_mock.post("http://localhost:1337/api/authors").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": 100, "documentId": "new-author-doc1", "name": "John Doe"}},
        )
    )

    # Mock article creation
    respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": 200, "documentId": "new-article-doc1", "title": "Article 1"}},
        )
    )

    relation_route = respx_mock.put("http://localhost:1337/api/articles/new-article-doc1").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": 200, "documentId": "new-article-doc1", "title": "Article 1"}},
        )
    )

    with SyncClient(strapi_config) as client:
        importer = StrapiImporter(client)
        options = ImportOptions(skip_relations=False)
        result = importer.import_data(export_data, options)

        assert result.success is True
        assert result.entities_imported == 2
        assert result.relations_imported == 1
        assert relation_route.called
        import json

        body = json.loads(relation_route.calls.last.request.content)
        assert body["data"]["author"] == "new-author-doc1"

        # Verify ID mapping was created
        assert "api::author.author" in result.id_mapping
        assert 5 in result.id_mapping["api::author.author"]
        assert result.id_mapping["api::author.author"][5] == 100

        assert "api::article.article" in result.id_mapping
        assert 1 in result.id_mapping["api::article.article"]
        assert result.id_mapping["api::article.article"][1] == 200


def _article_schema() -> ContentTypeSchema:
    return ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={"title": FieldSchema(type=FieldType.STRING)},
    )


def _locale_entities(
    *,
    en_first: bool = True,
    published: bool = False,
) -> list[ExportedEntity]:
    published_at = datetime(2026, 8, 16, 12, 0, 0) if published else None
    en = ExportedEntity(
        id=1,
        document_id="shared-doc",
        content_type="api::article.article",
        data={"title": "Hello"},
        locale="en",
        published_at=published_at,
    )
    fr = ExportedEntity(
        id=2,
        document_id="shared-doc",
        content_type="api::article.article",
        data={"title": "Bonjour"},
        locale="fr",
        published_at=published_at,
    )
    return [en, fr] if en_first else [fr, en]


def _locale_export(entities: list[ExportedEntity]) -> ExportData:
    return ExportData(
        metadata=ExportMetadata(
            strapi_version="v5",
            source_url="http://localhost:1337",
            content_types=["api::article.article"],
            total_entities=len(entities),
            schemas={"api::article.article": _article_schema()},
        ),
        entities={"api::article.article": entities},
    )


def _mock_locales(
    respx_mock: respx.Router,
    collection: str,
    document_id: str,
    present: set[str],
    *,
    default_locale: str = "en",
) -> None:
    """Document GET: 200 when ``locale`` is present (or omitted and default is).

    A no-locale GET is the default locale only (stock Strapi). ``locale=all``
    on the collection is registered separately so a dest that only has a
    non-default locale is still found.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        locale = request.url.params.get("locale")
        if locale in present or (locale is None and default_locale in present):
            return httpx.Response(
                200,
                json={
                    "data": {
                        "id": 1,
                        "documentId": document_id,
                        "title": locale or default_locale,
                    }
                },
            )
        return httpx.Response(404, json={"error": {"status": 404, "message": "Not found"}})

    respx_mock.get(f"http://localhost:1337/api/{collection}/{document_id}").mock(
        side_effect=handler
    )
    _collection_locale_all_docs(respx_mock, collection)[document_id] = set(present)


@pytest.mark.respx
def test_import_restores_localization_of_shared_document_id(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """New dest: one POST ?locale=en and one PUT dest?locale=fr."""
    export_data = _locale_export(_locale_entities())
    _mock_document_missing(respx_mock, "articles", "shared-doc")
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 10, "documentId": "dest-doc", "title": "Hello"}}
        )
    )
    update_route = respx_mock.put("http://localhost:1337/api/articles/dest-doc").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 11, "documentId": "dest-doc", "title": "Bonjour"}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(export_data)

    assert result.success is True
    assert result.entities_imported == 2
    assert create_route.call_count == 1
    assert update_route.call_count == 1
    assert create_route.calls[0].request.url.params["locale"] == "en"
    assert update_route.calls[0].request.url.params["locale"] == "fr"
    assert result.doc_id_to_new_document_id["api::article.article"]["shared-doc"] == "dest-doc"


@pytest.mark.respx
def test_import_localization_order_independent(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """fr first still creates once and localizes the other locale."""
    export_data = _locale_export(_locale_entities(en_first=False))
    _mock_document_missing(respx_mock, "articles", "shared-doc")
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 10, "documentId": "dest-doc", "title": "Bonjour"}}
        )
    )
    update_route = respx_mock.put("http://localhost:1337/api/articles/dest-doc").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 11, "documentId": "dest-doc", "title": "Hello"}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(export_data)

    assert result.success is True
    assert result.entities_imported == 2
    assert create_route.call_count == 1
    assert update_route.call_count == 1
    assert create_route.calls[0].request.url.params["locale"] == "fr"
    assert update_route.calls[0].request.url.params["locale"] == "en"


@pytest.mark.respx
def test_import_skip_writes_missing_locale(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """SKIP is per-locale: existing en is skipped, missing fr is written."""
    export_data = _locale_export(_locale_entities())
    _mock_locales(respx_mock, "articles", "shared-doc", {"en"})
    update_route = respx_mock.put("http://localhost:1337/api/articles/shared-doc").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 2, "documentId": "shared-doc", "title": "Bonjour"}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(
            export_data, ImportOptions(conflict_resolution=ConflictResolution.SKIP)
        )

    assert result.success is True
    assert result.entities_skipped == 1
    assert result.entities_imported == 1
    assert update_route.call_count == 1
    assert update_route.calls[0].request.url.params["locale"] == "fr"


@pytest.mark.respx
def test_import_skip_both_locales_exist(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """SKIP both locales when dest already has them."""
    export_data = _locale_export(_locale_entities())
    _mock_locales(respx_mock, "articles", "shared-doc", {"en", "fr"})
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(
            export_data, ImportOptions(conflict_resolution=ConflictResolution.SKIP)
        )

    assert result.success is True
    assert result.entities_skipped == 2
    assert result.entities_imported == 0
    assert create_route.call_count == 0


@pytest.mark.respx
def test_import_fail_writes_missing_locale_then_raises(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """FAIL still raises, but missing sibling locales are written first."""
    export_data = _locale_export(_locale_entities())
    _mock_locales(respx_mock, "articles", "shared-doc", {"en"})
    update_route = respx_mock.put("http://localhost:1337/api/articles/shared-doc").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 2, "documentId": "shared-doc", "title": "Bonjour"}}
        )
    )

    with SyncClient(strapi_config) as client:
        with pytest.raises(ImportExportError, match="already exists"):
            StrapiImporter(client).import_data(
                export_data, ImportOptions(conflict_resolution=ConflictResolution.FAIL)
            )

    assert update_route.call_count == 1
    assert update_route.calls[0].request.url.params["locale"] == "fr"


@pytest.mark.respx
def test_import_fail_writes_missing_locale_when_it_is_first(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """A missing locale is not a conflict even under FAIL."""
    export_data = _locale_export(_locale_entities(en_first=False))
    _mock_locales(respx_mock, "articles", "shared-doc", {"en"})
    update_route = respx_mock.put("http://localhost:1337/api/articles/shared-doc").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 2, "documentId": "shared-doc", "title": "Bonjour"}}
        )
    )

    with SyncClient(strapi_config) as client:
        with pytest.raises(ImportExportError, match="already exists"):
            StrapiImporter(client).import_data(
                export_data, ImportOptions(conflict_resolution=ConflictResolution.FAIL)
            )

    assert update_route.call_count == 1
    assert update_route.calls[0].request.url.params["locale"] == "fr"


@pytest.mark.respx
def test_import_fail_dry_run_probes_and_raises_without_writes(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """FAIL dry-run probes (documentId, locale) and aborts without writing (#121)."""
    export_data = _locale_export(_locale_entities())
    _mock_locales(respx_mock, "articles", "shared-doc", {"en"})
    update_route = respx_mock.put("http://localhost:1337/api/articles/shared-doc").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 2, "documentId": "shared-doc", "title": "Bonjour"}}
        )
    )
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )

    with SyncClient(strapi_config) as client:
        with pytest.raises(ImportExportError, match="already exists"):
            StrapiImporter(client).import_data(
                export_data,
                ImportOptions(dry_run=True, conflict_resolution=ConflictResolution.FAIL),
            )

    assert update_route.call_count == 0
    assert create_route.call_count == 0


@pytest.mark.respx
def test_import_from_jsonl_fail_dry_run_probes_and_raises_without_writes(
    strapi_config: StrapiConfig,
    respx_mock: respx.Router,
    tmp_path: Path,
) -> None:
    """JSONL FAIL dry-run probes locales and aborts without writing (#121)."""
    export_data = _locale_export(_locale_entities())
    jsonl_path = tmp_path / "export.jsonl"
    with JSONLExportWriter(jsonl_path) as writer:
        writer.write_metadata(export_data.metadata)
        for entity in export_data.entities["api::article.article"]:
            writer.write_entity(entity)

    _mock_locales(respx_mock, "articles", "shared-doc", {"en"})
    update_route = respx_mock.put("http://localhost:1337/api/articles/shared-doc").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 2, "documentId": "shared-doc", "title": "Bonjour"}}
        )
    )
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )

    with SyncClient(strapi_config) as client:
        with pytest.raises(ImportExportError, match="already exists"):
            StrapiImporter(client).import_from_jsonl(
                jsonl_path,
                ImportOptions(dry_run=True, conflict_resolution=ConflictResolution.FAIL),
            )

    assert update_route.call_count == 0
    assert create_route.call_count == 0


@pytest.mark.respx
def test_import_from_jsonl_fail_writes_missing_locale(
    strapi_config: StrapiConfig,
    respx_mock: respx.Router,
    tmp_path: Path,
) -> None:
    """JSONL FAIL writes missing locales, then aborts (not a per-row add_error)."""
    export_data = _locale_export(_locale_entities())
    jsonl_path = tmp_path / "export.jsonl"
    with JSONLExportWriter(jsonl_path) as writer:
        writer.write_metadata(export_data.metadata)
        for entity in export_data.entities["api::article.article"]:
            writer.write_entity(entity)

    _mock_locales(respx_mock, "articles", "shared-doc", {"en"})
    update_route = respx_mock.put("http://localhost:1337/api/articles/shared-doc").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 2, "documentId": "shared-doc", "title": "Bonjour"}}
        )
    )

    with SyncClient(strapi_config) as client:
        with pytest.raises(ImportExportError, match="already exists"):
            StrapiImporter(client).import_from_jsonl(
                jsonl_path,
                ImportOptions(conflict_resolution=ConflictResolution.FAIL),
            )

    assert update_route.call_count == 1
    assert update_route.calls[0].request.url.params["locale"] == "fr"


@pytest.mark.respx
def test_import_fail_both_locales_exist_writes_nothing(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """FAIL still raises when every locale already exists, and writes nothing."""
    export_data = _locale_export(_locale_entities())
    _mock_locales(respx_mock, "articles", "shared-doc", {"en", "fr"})
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )
    update_route = respx_mock.put("http://localhost:1337/api/articles/shared-doc").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not update"}})
    )

    with SyncClient(strapi_config) as client:
        with pytest.raises(ImportExportError, match="2 locales already exist") as caught:
            StrapiImporter(client).import_data(
                export_data, ImportOptions(conflict_resolution=ConflictResolution.FAIL)
            )

    assert create_route.call_count == 0
    assert update_route.call_count == 0
    assert caught.value.details["entities_failed"] == 2
    assert caught.value.details["entities_imported"] == 0


@pytest.mark.respx
def test_import_fail_writes_missing_locale_relations_not_existing(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """FAIL writes the missing locale's relations/publish, not the existing one."""
    import json

    author_schema = ContentTypeSchema(
        uid="api::author.author",
        display_name="Author",
        plural_name="authors",
        fields={"name": FieldSchema(type=FieldType.STRING)},
    )
    article_schema = ContentTypeSchema(
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
        },
    )
    published_at = datetime(2026, 8, 16, 12, 0, 0)
    export_data = ExportData(
        metadata=ExportMetadata(
            strapi_version="v5",
            source_url="http://localhost:1337",
            content_types=["api::author.author", "api::article.article"],
            total_entities=3,
            schemas={
                "api::author.author": author_schema,
                "api::article.article": article_schema,
            },
        ),
        entities={
            "api::author.author": [
                ExportedEntity(
                    id=9,
                    document_id="auth-src",
                    content_type="api::author.author",
                    data={"name": "Ada"},
                )
            ],
            "api::article.article": [
                ExportedEntity(
                    id=1,
                    document_id="shared-doc",
                    content_type="api::article.article",
                    data={"title": "Hello"},
                    relations={"author": ["auth-src"]},
                    locale="en",
                    published_at=published_at,
                ),
                ExportedEntity(
                    id=2,
                    document_id="shared-doc",
                    content_type="api::article.article",
                    data={"title": "Bonjour"},
                    relations={"author": ["auth-src"]},
                    locale="fr",
                    published_at=published_at,
                ),
            ],
        },
    )
    _mock_document_missing(respx_mock, "authors", "auth-src")
    _mock_locales(respx_mock, "articles", "shared-doc", {"en"})
    respx_mock.post("http://localhost:1337/api/authors").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 9, "documentId": "auth-new", "name": "Ada"}}
        )
    )
    update_route = respx_mock.put("http://localhost:1337/api/articles/shared-doc").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 2, "documentId": "shared-doc", "title": "Bonjour"}}
        )
    )

    with SyncClient(strapi_config) as client:
        with pytest.raises(ImportExportError, match="already exists") as caught:
            StrapiImporter(client).import_data(
                export_data, ImportOptions(conflict_resolution=ConflictResolution.FAIL)
            )

    locale_puts = [
        call
        for call in update_route.calls
        if call.request.url.params.get("locale") == "fr"
        and call.request.url.params.get("status") != "published"
    ]
    publish_puts = [
        call for call in update_route.calls if call.request.url.params.get("status") == "published"
    ]
    en_relation_puts = [
        call
        for call in update_route.calls
        if call.request.url.params.get("locale") == "en"
        and "author" in json.loads(call.request.content).get("data", {})
    ]
    assert len(locale_puts) == 2
    assert json.loads(locale_puts[0].request.content)["data"]["title"] == "Bonjour"
    assert json.loads(locale_puts[1].request.content)["data"]["author"] == "auth-new"
    assert len(publish_puts) == 1
    assert publish_puts[0].request.url.params["locale"] == "fr"
    assert en_relation_puts == []
    assert caught.value.details["entities_failed"] == 1
    # Author create + missing fr locale. Existing en is failed, not imported.
    assert caught.value.details["entities_imported"] == 2
    assert caught.value.details["relations_imported"] == 1


@pytest.mark.respx
def test_import_relation_put_includes_locale(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Relation writes for a French row include locale=fr."""
    author_schema = ContentTypeSchema(
        uid="api::author.author",
        display_name="Author",
        plural_name="authors",
        fields={"name": FieldSchema(type=FieldType.STRING)},
    )
    article_schema = ContentTypeSchema(
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
        },
    )
    export_data = ExportData(
        metadata=ExportMetadata(
            strapi_version="v5",
            source_url="http://localhost:1337",
            content_types=["api::author.author", "api::article.article"],
            total_entities=2,
            schemas={
                "api::author.author": author_schema,
                "api::article.article": article_schema,
            },
        ),
        entities={
            "api::author.author": [
                ExportedEntity(
                    id=1,
                    document_id="auth-src",
                    content_type="api::author.author",
                    data={"name": "Ada"},
                )
            ],
            "api::article.article": [
                ExportedEntity(
                    id=2,
                    document_id="art-src",
                    content_type="api::article.article",
                    data={"title": "Bonjour"},
                    relations={"author": ["auth-src"]},
                    locale="fr",
                )
            ],
        },
    )
    _mock_document_missing(respx_mock, "authors", "auth-src")
    _mock_document_missing(respx_mock, "articles", "art-src")
    respx_mock.post("http://localhost:1337/api/authors").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 9, "documentId": "auth-new", "name": "Ada"}}
        )
    )
    respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "documentId": "art-new", "title": "Bonjour"}}
        )
    )
    relation_route = respx_mock.put("http://localhost:1337/api/articles/art-new").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "documentId": "art-new", "title": "Bonjour"}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(export_data)

    assert result.success is True
    assert result.relations_imported == 1
    assert relation_route.calls.last.request.url.params["locale"] == "fr"


@pytest.mark.respx
def test_import_data_dry_run_does_not_write_relations(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Dry-run does not write, and missing dests are not mapped as dest ids (#121 #131)."""
    author_schema = ContentTypeSchema(
        uid="api::author.author",
        display_name="Author",
        plural_name="authors",
        fields={"name": FieldSchema(type=FieldType.STRING)},
    )
    article_schema = ContentTypeSchema(
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
        },
    )
    export_data = ExportData(
        metadata=ExportMetadata(
            strapi_version="v5",
            source_url="http://localhost:1337",
            content_types=["api::author.author", "api::article.article"],
            total_entities=2,
            schemas={
                "api::author.author": author_schema,
                "api::article.article": article_schema,
            },
        ),
        entities={
            "api::author.author": [
                ExportedEntity(
                    id=1,
                    document_id="auth-src",
                    content_type="api::author.author",
                    data={"name": "Ada"},
                    published_at=datetime(2026, 8, 16, 12, 0, 0),
                )
            ],
            "api::article.article": [
                ExportedEntity(
                    id=2,
                    document_id="art-src",
                    content_type="api::article.article",
                    data={"title": "Bonjour"},
                    relations={"author": ["auth-src"]},
                    locale="fr",
                    published_at=datetime(2026, 8, 16, 12, 0, 0),
                )
            ],
        },
    )
    _mock_document_missing(respx_mock, "authors", "auth-src")
    _mock_document_missing(respx_mock, "articles", "art-src")
    create_authors = respx_mock.post("http://localhost:1337/api/authors").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )
    create_articles = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )
    # Regression guard: a leaked write that reused the source documentId hits this path.
    source_put = respx_mock.put("http://localhost:1337/api/articles/art-src").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not update"}})
    )
    dest_put = respx_mock.put("http://localhost:1337/api/articles/art-new").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not update"}})
    )
    author_put = respx_mock.put("http://localhost:1337/api/authors/auth-src").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not update"}})
    )

    progress: list[str] = []
    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(
            export_data,
            ImportOptions(
                dry_run=True,
                progress_callback=lambda _cur, _total, msg: progress.append(msg),
            ),
        )

    assert result.dry_run
    assert result.entities_imported == 2
    assert result.relations_imported == 0
    assert result.entities_to_publish == 2
    assert "Importing relations" not in progress
    assert "Reporting relations" in progress
    assert any("not in dest mapping" in warning for warning in result.warnings)
    assert result.id_mapping == {}
    assert result.doc_id_mapping == {}
    assert result.doc_id_to_new_id == {}
    assert result.doc_id_to_new_document_id == {}
    assert create_authors.call_count == 0
    assert create_articles.call_count == 0
    assert source_put.call_count == 0
    assert dest_put.call_count == 0
    assert author_put.call_count == 0


@pytest.mark.respx
def test_import_dry_run_maps_existing_dest_for_missing_locale(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Missing locale of an existing dest still maps the real dest id (#131)."""
    export_data = _locale_export([_locale_entities()[1]])
    _mock_locales(respx_mock, "articles", "shared-doc", {"en"})
    update_route = respx_mock.put("http://localhost:1337/api/articles/shared-doc").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not update"}})
    )
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(export_data, ImportOptions(dry_run=True))

    assert result.dry_run
    assert result.entities_imported == 1
    assert result.entities_failed == 0
    assert result.id_mapping["api::article.article"] == {2: 1}
    assert result.doc_id_mapping["api::article.article"] == {2: "shared-doc"}
    assert result.doc_id_to_new_id["api::article.article"] == {"shared-doc": 1}
    assert result.doc_id_to_new_document_id["api::article.article"] == {"shared-doc": "shared-doc"}
    assert 0 not in result.id_mapping["api::article.article"].values()
    assert update_route.call_count == 0
    assert create_route.call_count == 0


@pytest.mark.respx
def test_import_dry_run_skip_maps_missing_locale_from_existing_mapping(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """A later missing locale reuses the dest already mapped this dry-run (#131)."""
    export_data = _locale_export(_locale_entities())
    _mock_locales(respx_mock, "articles", "shared-doc", {"en"})
    update_route = respx_mock.put("http://localhost:1337/api/articles/shared-doc").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not update"}})
    )
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(
            export_data,
            ImportOptions(dry_run=True, conflict_resolution=ConflictResolution.SKIP),
        )

    assert result.entities_skipped == 1
    assert result.entities_imported == 1
    assert result.id_mapping["api::article.article"] == {1: 1, 2: 1}
    assert result.doc_id_mapping["api::article.article"] == {1: "shared-doc", 2: "shared-doc"}
    assert 0 not in result.id_mapping["api::article.article"].values()
    assert update_route.call_count == 0
    assert create_route.call_count == 0


@pytest.mark.respx
def test_import_from_jsonl_dry_run_maps_existing_dest_only(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
    respx_mock: respx.Router,
    tmp_path: Path,
) -> None:
    """JSONL dry-run maps existing dests and leaves missing dests unmapped (#131)."""
    jsonl_path = tmp_path / "export.jsonl"
    with JSONLExportWriter(jsonl_path) as writer:
        writer.write_metadata(sample_export_data.metadata)
        for entity in sample_export_data.entities["api::article.article"]:
            writer.write_entity(entity)

    respx_mock.get("http://localhost:1337/api/articles/doc1").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 42, "documentId": "doc1", "title": "Old"}}
        )
    )
    _mock_document_missing(respx_mock, "articles", "doc2")
    update_route = respx_mock.put("http://localhost:1337/api/articles/doc1").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not update"}})
    )
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_from_jsonl(
            jsonl_path,
            ImportOptions(dry_run=True, conflict_resolution=ConflictResolution.SKIP),
        )

    assert result.dry_run
    assert result.entities_skipped == 1
    assert result.entities_imported == 1
    assert result.id_mapping["api::article.article"] == {1: 42}
    assert 2 not in result.id_mapping["api::article.article"]
    assert 0 not in result.id_mapping["api::article.article"].values()
    assert result.doc_id_mapping["api::article.article"] == {1: "doc1"}
    assert "doc2" not in result.doc_id_to_new_id.get("api::article.article", {})
    assert update_route.call_count == 0
    assert create_route.call_count == 0


@pytest.mark.respx
def test_import_from_jsonl_dry_run_missing_dests_leave_mapping_empty(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
    respx_mock: respx.Router,
    tmp_path: Path,
) -> None:
    """JSONL dry-run does not pre-create empty per-type mapping dicts (#136)."""
    jsonl_path = tmp_path / "export.jsonl"
    with JSONLExportWriter(jsonl_path) as writer:
        writer.write_metadata(sample_export_data.metadata)
        for entity in sample_export_data.entities["api::article.article"]:
            writer.write_entity(entity)

    _mock_document_missing(respx_mock, "articles", "doc1")
    _mock_document_missing(respx_mock, "articles", "doc2")
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_from_jsonl(jsonl_path, ImportOptions(dry_run=True))

    assert result.entities_imported == 2
    assert result.id_mapping == {}
    assert result.doc_id_mapping == {}
    assert create_route.call_count == 0


@pytest.mark.respx
def test_import_from_jsonl_validates_missing_relation_targets(
    strapi_config: StrapiConfig, respx_mock: respx.Router, tmp_path: Path
) -> None:
    """JSONL preflight warns when a relation target is absent from the export (#136)."""
    export_data = _nested_component_export()
    export_data.entities["api::article.article"][0].relations = {"seo[0].author": [99]}
    jsonl_path = tmp_path / "export.jsonl"
    with JSONLExportWriter(jsonl_path) as writer:
        writer.write_metadata(export_data.metadata)
        for content_type in export_data.metadata.content_types:
            for entity in export_data.entities[content_type]:
                writer.write_entity(entity)

    _mock_document_missing(respx_mock, "authors", "auth-src")
    _mock_document_missing(respx_mock, "articles", "art-src")
    respx_mock.post("http://localhost:1337/api/authors").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 9, "documentId": "auth-new", "name": "Ada"}}
        )
    )
    respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "documentId": "art-new", "title": "Hello"}}
        )
    )
    respx_mock.put("http://localhost:1337/api/articles/art-new").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "documentId": "art-new", "title": "Hello"}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_from_jsonl(jsonl_path)

    assert any("seo[0].author" in warning and "99" in warning for warning in result.warnings)


@pytest.mark.respx
def test_import_from_jsonl_warns_without_media_dir(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
    respx_mock: respx.Router,
    tmp_path: Path,
) -> None:
    """JSONL import_media with no media_dir records the same skip warning (#136)."""
    sample_export_data.metadata.total_media = 1
    jsonl_path = tmp_path / "export.jsonl"
    with JSONLExportWriter(jsonl_path) as writer:
        writer.write_metadata(sample_export_data.metadata)
        for entity in sample_export_data.entities["api::article.article"]:
            writer.write_entity(entity)

    _mock_document_missing(respx_mock, "articles", "doc1")
    _mock_document_missing(respx_mock, "articles", "doc2")
    respx_mock.post("http://localhost:1337/api/articles").mock(
        side_effect=[
            httpx.Response(
                200, json={"data": {"id": 10, "documentId": "new_doc1", "title": "Article 1"}}
            ),
            httpx.Response(
                200, json={"data": {"id": 11, "documentId": "new_doc2", "title": "Article 2"}}
            ),
        ]
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_from_jsonl(jsonl_path)

    assert any("Media directory not specified" in warning for warning in result.warnings)


@pytest.mark.respx
def test_import_from_jsonl_counts_entities_when_metadata_totals_zero(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
    respx_mock: respx.Router,
    tmp_path: Path,
) -> None:
    """Official JSONL metadata leaves totals at 0; preflight counts the file (#136)."""
    sample_export_data.metadata.total_entities = 0
    jsonl_path = tmp_path / "export.jsonl"
    _write_export_jsonl(jsonl_path, sample_export_data)
    _mock_document_missing(respx_mock, "articles", "doc1")
    _mock_document_missing(respx_mock, "articles", "doc2")

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_from_jsonl(jsonl_path, ImportOptions(dry_run=True))

    assert not any("No entities to import" in warning for warning in result.warnings)


@pytest.mark.respx
def test_import_from_jsonl_warns_from_media_manifest_when_total_media_zero(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
    respx_mock: respx.Router,
    tmp_path: Path,
) -> None:
    """A media manifest still triggers the skip warning when total_media is 0 (#136)."""
    sample_export_data.metadata.total_media = 0
    jsonl_path = tmp_path / "export.jsonl"
    with JSONLExportWriter(jsonl_path) as writer:
        writer.write_metadata(sample_export_data.metadata)
        for entity in sample_export_data.entities["api::article.article"]:
            writer.write_entity(entity)
        writer.write_media_manifest(
            [
                ExportedMediaFile(
                    id=1,
                    url="/uploads/image.jpg",
                    name="image.jpg",
                    mime="image/jpeg",
                    size=10,
                    hash="abc",
                    local_path="image.jpg",
                )
            ]
        )
    _mock_document_missing(respx_mock, "articles", "doc1")
    _mock_document_missing(respx_mock, "articles", "doc2")

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_from_jsonl(jsonl_path, ImportOptions(dry_run=True))

    assert any("Media directory not specified" in warning for warning in result.warnings)


@pytest.mark.respx
def test_import_data_dry_run_reports_publish_intent_for_live_rows(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Dry-run counts live rows that would publish without calling publish (#135)."""
    export_data = _locale_export(_locale_entities(published=True)[1:])
    _mock_document_missing(respx_mock, "articles", "shared-doc")
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )
    publish_route = respx_mock.put("http://localhost:1337/api/articles/dest-doc").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not publish"}})
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(export_data, ImportOptions(dry_run=True))

    assert result.entities_imported == 1
    assert result.entities_to_publish == 1
    assert create_route.call_count == 0
    assert publish_route.call_count == 0


@pytest.mark.respx
def test_import_data_dry_run_does_not_write_mapped_relations(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Resolve-only later pass does not PUT when dests already exist (#135)."""
    export_data = _nested_component_export()
    _mock_document_exists(respx_mock, "authors", "auth-src", dest_id=9)
    _mock_document_exists(respx_mock, "articles", "art-src", dest_id=20)
    create_authors = respx_mock.post("http://localhost:1337/api/authors").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )
    create_articles = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )
    author_put = respx_mock.put("http://localhost:1337/api/authors/auth-src").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not update"}})
    )
    article_put = respx_mock.put("http://localhost:1337/api/articles/art-src").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not update"}})
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(export_data, ImportOptions(dry_run=True))

    assert result.entities_skipped == 2
    assert result.relations_imported == 0
    assert result.id_mapping["api::article.article"] == {2: 20}
    assert result.id_mapping["api::author.author"] == {1: 9}
    assert create_authors.call_count == 0
    assert create_articles.call_count == 0
    assert author_put.call_count == 0
    assert article_put.call_count == 0
    assert not any("not in dest mapping" in warning for warning in result.warnings)


@pytest.mark.respx
def test_import_data_dry_run_nested_skip_is_warning(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Dry-run records unwritable nested paths as warnings, not errors (#135)."""
    export_data = _nested_component_export()
    export_data.entities["api::article.article"][0].data = {"title": "Hello"}
    _mock_document_exists(respx_mock, "authors", "auth-src", dest_id=9)
    _mock_document_exists(respx_mock, "articles", "art-src", dest_id=20)
    article_put = respx_mock.put("http://localhost:1337/api/articles/art-src").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not update"}})
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(export_data, ImportOptions(dry_run=True))

    assert any(
        "Skipped nested relations" in warning and "seo[0].author" in warning
        for warning in result.warnings
    )
    assert result.errors == []
    assert result.relations_imported == 0
    assert article_put.call_count == 0


@pytest.mark.respx
def test_import_data_dry_run_update_counts_publish_intent_on_existing_dest(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """UPDATE dry-run counts publish intent for an existing dest and does not PUT (#135)."""
    export_data = _locale_export(_locale_entities(published=True)[:1])
    _mock_locales(respx_mock, "articles", "shared-doc", {"en"})
    update_route = respx_mock.put("http://localhost:1337/api/articles/shared-doc").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not update"}})
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(
            export_data,
            ImportOptions(dry_run=True, conflict_resolution=ConflictResolution.UPDATE),
        )

    assert result.entities_updated == 1
    assert result.entities_to_publish == 1
    assert update_route.call_count == 0


@pytest.mark.respx
def test_import_fail_dry_run_with_relations_does_not_write(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """FAIL dry-run still resolve-reports later and raises without writes (#135)."""
    export_data = _nested_component_export()
    export_data.entities["api::article.article"][0].locale = "en"
    export_data.entities["api::article.article"][0].published_at = datetime(2026, 8, 16, 12, 0, 0)
    _mock_document_exists(respx_mock, "authors", "auth-src", dest_id=9)
    _mock_locales(respx_mock, "articles", "art-src", {"en"})
    article_put = respx_mock.put("http://localhost:1337/api/articles/art-src").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not update"}})
    )
    author_put = respx_mock.put("http://localhost:1337/api/authors/auth-src").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not update"}})
    )

    with SyncClient(strapi_config) as client:
        with pytest.raises(ImportExportError, match="already exists") as caught:
            StrapiImporter(client).import_data(
                export_data,
                ImportOptions(dry_run=True, conflict_resolution=ConflictResolution.FAIL),
            )

    assert article_put.call_count == 0
    assert author_put.call_count == 0
    assert caught.value.details["entities_to_publish"] == 0


@pytest.mark.respx
def test_import_from_jsonl_dry_run_records_unmapped_relation_rows(
    strapi_config: StrapiConfig, respx_mock: respx.Router, tmp_path: Path
) -> None:
    """JSONL dry-run records unmapped relation rows on ImportResult (#136)."""
    jsonl_path = tmp_path / "export.jsonl"
    _write_export_jsonl(jsonl_path, _nested_component_export())
    _mock_document_missing(respx_mock, "authors", "auth-src")
    _mock_document_missing(respx_mock, "articles", "art-src")
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_from_jsonl(jsonl_path, ImportOptions(dry_run=True))

    assert any("not in dest mapping" in warning for warning in result.warnings)
    assert result.id_mapping == {}
    assert result.doc_id_mapping == {}
    assert result.doc_id_to_new_id == {}
    assert result.doc_id_to_new_document_id == {}
    assert create_route.call_count == 0


@pytest.mark.respx
def test_import_from_jsonl_validate_relations_false_skips_preflight(
    strapi_config: StrapiConfig, respx_mock: respx.Router, tmp_path: Path
) -> None:
    """JSONL ``validate_relations=False`` skips export-ID preflight (#136)."""
    export_data = _nested_component_export()
    export_data.entities["api::article.article"][0].relations = {"seo[0].author": [99]}
    jsonl_path = tmp_path / "export.jsonl"
    _write_export_jsonl(jsonl_path, export_data)
    _mock_document_missing(respx_mock, "authors", "auth-src")
    _mock_document_missing(respx_mock, "articles", "art-src")

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_from_jsonl(
            jsonl_path,
            ImportOptions(dry_run=True, validate_relations=False),
        )

    assert not any("99" in warning for warning in result.warnings)


@pytest.mark.respx
def test_import_from_jsonl_preflight_indexes_unselected_types(
    strapi_config: StrapiConfig, respx_mock: respx.Router, tmp_path: Path
) -> None:
    """JSONL preflight sees relation targets even when that type is filtered (#136)."""
    jsonl_path = tmp_path / "export.jsonl"
    _write_nested_component_jsonl(jsonl_path)
    _mock_document_missing(respx_mock, "articles", "art-src")

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_from_jsonl(
            jsonl_path,
            ImportOptions(dry_run=True, content_types=["api::article.article"]),
        )

    assert not any("not in export" in warning for warning in result.warnings)


@pytest.mark.respx
def test_import_from_jsonl_warns_on_version_mismatch(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
    respx_mock: respx.Router,
    tmp_path: Path,
) -> None:
    """JSONL metadata preflight matches ``import_data`` version warnings (#136)."""
    sample_export_data.metadata.strapi_version = "v4"
    jsonl_path = tmp_path / "export.jsonl"
    _write_export_jsonl(jsonl_path, sample_export_data)
    _mock_document_missing(respx_mock, "articles", "doc1")
    _mock_document_missing(respx_mock, "articles", "doc2")
    config = StrapiConfig(
        base_url=strapi_config.base_url,
        api_token=strapi_config.api_token,
        api_version="v5",
    )

    with SyncClient(config) as client:
        result = StrapiImporter(client).import_from_jsonl(jsonl_path, ImportOptions(dry_run=True))

    assert any("differs from target" in warning for warning in result.warnings)


def test_validate_relations_warns_without_export_schema(strapi_config: StrapiConfig) -> None:
    """A related row with no export schema is not a silent preflight skip (#136)."""
    export_data = _nested_component_export()
    export_data.metadata.schemas.pop("api::article.article")
    result = ImportResult(success=False, dry_run=True)
    with SyncClient(strapi_config) as client:
        importer = StrapiImporter(client)
        importer._validate_relations(export_data, result)

    assert any("no schema in export metadata" in warning for warning in result.warnings)


def test_validate_relations_warns_when_path_has_no_target(strapi_config: StrapiConfig) -> None:
    """An unresolvable relation path is recorded, not skipped (#136)."""
    export_data = _nested_component_export()
    export_data.entities["api::article.article"][0].relations = {"missing.path": [1]}
    result = ImportResult(success=False, dry_run=True)
    with SyncClient(strapi_config) as client:
        importer = StrapiImporter(client)
        importer._load_schemas_from_export(export_data)
        importer._validate_relations(export_data, result)

    assert any(
        "missing.path" in warning and "cannot resolve relation target" in warning
        for warning in result.warnings
    )


@pytest.mark.respx
def test_import_publishes_french_live_row_with_locale(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """A live French source row is published with locale=fr."""
    export_data = _locale_export(_locale_entities(published=True)[1:])
    _mock_document_missing(respx_mock, "articles", "shared-doc")
    respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 10, "documentId": "dest-doc", "title": "Bonjour"}}
        )
    )
    publish_route = respx_mock.put("http://localhost:1337/api/articles/dest-doc").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 10, "documentId": "dest-doc", "title": "Bonjour"}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(export_data)

    assert result.success is True
    assert publish_route.call_count == 1
    assert publish_route.calls.last.request.url.params["status"] == "published"
    assert publish_route.calls.last.request.url.params["locale"] == "fr"


@pytest.mark.respx
def test_import_from_jsonl_restores_localization(
    strapi_config: StrapiConfig, respx_mock: respx.Router, tmp_path: Path
) -> None:
    """JSONL follows the same create-then-localize contract."""
    export_data = _locale_export(_locale_entities())
    jsonl_path = tmp_path / "export.jsonl"
    with JSONLExportWriter(jsonl_path) as writer:
        writer.write_metadata(export_data.metadata)
        for entity in export_data.entities["api::article.article"]:
            writer.write_entity(entity)

    _mock_document_missing(respx_mock, "articles", "shared-doc")
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 10, "documentId": "dest-doc", "title": "Hello"}}
        )
    )
    update_route = respx_mock.put("http://localhost:1337/api/articles/dest-doc").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 11, "documentId": "dest-doc", "title": "Bonjour"}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_from_jsonl(jsonl_path)

    assert result.success is True
    assert result.entities_imported == 2
    assert create_route.call_count == 1
    assert update_route.call_count == 1
    assert create_route.calls[0].request.url.params["locale"] == "en"
    assert update_route.calls[0].request.url.params["locale"] == "fr"
    assert result.doc_id_to_new_document_id["api::article.article"]["shared-doc"] == "dest-doc"


@pytest.mark.respx
def test_import_row_without_locale_omits_locale_param(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Rows with no locale do not send locale= on create."""
    _mock_document_missing(respx_mock, "articles", "doc1")
    _mock_document_missing(respx_mock, "articles", "doc2")
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        side_effect=[
            httpx.Response(
                200, json={"data": {"id": 10, "documentId": "new_doc1", "title": "Article 1"}}
            ),
            httpx.Response(
                200, json={"data": {"id": 11, "documentId": "new_doc2", "title": "Article 2"}}
            ),
        ]
    )

    with SyncClient(strapi_config) as client:
        StrapiImporter(client).import_data(
            ExportData(
                metadata=ExportMetadata(
                    strapi_version="v5",
                    source_url="http://localhost:1337",
                    content_types=["api::article.article"],
                    total_entities=2,
                    schemas={"api::article.article": _article_schema()},
                ),
                entities={
                    "api::article.article": [
                        ExportedEntity(
                            id=1,
                            document_id="doc1",
                            content_type="api::article.article",
                            data={"title": "Article 1"},
                        ),
                        ExportedEntity(
                            id=2,
                            document_id="doc2",
                            content_type="api::article.article",
                            data={"title": "Article 2"},
                        ),
                    ]
                },
            )
        )

    assert create_route.call_count == 2
    assert "locale" not in create_route.calls[0].request.url.params
    assert "locale" not in create_route.calls[1].request.url.params


@pytest.mark.respx
def test_import_existence_invalid_key_locale_retries_without_locale(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Invalid key locale on the probe retries that GET without locale."""
    export_data = _locale_export(_locale_entities()[:1])

    def articles(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("locale"):
            return httpx.Response(
                400, json={"error": {"status": 400, "message": "Invalid key locale"}}
            )
        return httpx.Response(404, json={"error": {"status": 404, "message": "Not found"}})

    route = respx_mock.get("http://localhost:1337/api/articles/shared-doc").mock(
        side_effect=articles
    )
    _collection_locale_all_docs(respx_mock, "articles")["shared-doc"] = set()
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 10, "documentId": "dest-doc", "title": "Hello"}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(export_data)

    assert result.success is True
    assert result.entities_imported == 1
    assert create_route.call_count == 1
    assert create_route.calls[0].request.url.params["locale"] == "en"
    locales = [call.request.url.params.get("locale") for call in route.calls]
    assert "en" in locales
    assert None in locales


@pytest.mark.respx
def test_import_skip_same_instance_missing_locale_first(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Dest has en; fr arrives first. SKIP must PUT existing dest, not POST."""
    export_data = _locale_export(_locale_entities(en_first=False))
    _mock_locales(respx_mock, "articles", "shared-doc", {"en"})
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )
    update_route = respx_mock.put("http://localhost:1337/api/articles/shared-doc").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 2, "documentId": "shared-doc", "title": "Bonjour"}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(
            export_data, ImportOptions(conflict_resolution=ConflictResolution.SKIP)
        )

    assert result.success is True
    assert result.entities_imported == 1
    assert result.entities_skipped == 1
    assert create_route.call_count == 0
    assert update_route.call_count == 1
    assert update_route.calls[0].request.url.params["locale"] == "fr"
    assert result.doc_id_to_new_document_id["api::article.article"]["shared-doc"] == "shared-doc"


@pytest.mark.respx
def test_import_skip_same_instance_missing_default_locale(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Dest has fr only; en arrives first. SKIP must PUT dest?locale=en, not POST."""
    export_data = _locale_export(_locale_entities())
    _mock_locales(respx_mock, "articles", "shared-doc", {"fr"})
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )
    update_route = respx_mock.put("http://localhost:1337/api/articles/shared-doc").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 1, "documentId": "shared-doc", "title": "Hello"}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(
            export_data, ImportOptions(conflict_resolution=ConflictResolution.SKIP)
        )

    assert result.success is True
    assert result.entities_imported == 1
    assert result.entities_skipped == 1
    assert create_route.call_count == 0
    assert update_route.call_count == 1
    assert update_route.calls[0].request.url.params["locale"] == "en"
    assert result.doc_id_to_new_document_id["api::article.article"]["shared-doc"] == "shared-doc"


@pytest.mark.respx
def test_import_skip_draft_only_locale(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Published locale miss + draft locale hit must SKIP, not write."""

    def articles(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("locale") == "fr" and request.url.params.get("status") == "draft":
            return httpx.Response(
                200,
                json={"data": {"id": 2, "documentId": "shared-doc", "title": "Bonjour"}},
            )
        return httpx.Response(404, json={"error": {"status": 404, "message": "Not found"}})

    respx_mock.get("http://localhost:1337/api/articles/shared-doc").mock(side_effect=articles)
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )
    update_route = respx_mock.put("http://localhost:1337/api/articles/shared-doc").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not update"}})
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(
            _locale_export(_locale_entities()[1:]),
            ImportOptions(conflict_resolution=ConflictResolution.SKIP),
        )

    assert result.success is True
    assert result.entities_skipped == 1
    assert result.entities_imported == 0
    assert create_route.call_count == 0
    assert update_route.call_count == 0
    assert result.id_mapping["api::article.article"][2] == 2


@pytest.mark.respx
def test_import_existence_invalid_key_populate_with_locale_does_not_fallback(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """A populate 400 on ``?locale=`` must not retry without locale or create."""

    def articles(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("locale"):
            return httpx.Response(
                400, json={"error": {"status": 400, "message": "Invalid key populate"}}
            )
        return httpx.Response(404, json={"error": {"status": 404, "message": "Not found"}})

    route = respx_mock.get("http://localhost:1337/api/articles/shared-doc").mock(
        side_effect=articles
    )
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 10, "documentId": "dest-doc", "title": "Hello"}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(_locale_export(_locale_entities()[:1]))

    assert result.entities_failed == 1
    assert result.entities_imported == 0
    assert create_route.call_count == 0
    assert any(isinstance(error, str) and "populate" in error.lower() for error in result.errors)
    assert all(call.request.url.params.get("locale") == "en" for call in route.calls)


@pytest.mark.respx
def test_import_existence_invalid_key_locale_draft_retry_keeps_status(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Invalid key locale on the draft GET must retry with status=draft kept."""

    def articles(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("locale"):
            return httpx.Response(
                400, json={"error": {"status": 400, "message": "Invalid key locale"}}
            )
        if request.url.params.get("status") == "draft":
            return httpx.Response(
                200, json={"data": {"id": 42, "documentId": "shared-doc", "title": "Draft"}}
            )
        return httpx.Response(404, json={"error": {"status": 404, "message": "Not found"}})

    route = respx_mock.get("http://localhost:1337/api/articles/shared-doc").mock(
        side_effect=articles
    )
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(
            _locale_export(_locale_entities()[:1]),
            ImportOptions(conflict_resolution=ConflictResolution.SKIP),
        )

    assert result.success is True
    assert result.entities_skipped == 1
    assert create_route.call_count == 0
    draft_no_locale = [
        call
        for call in route.calls
        if call.request.url.params.get("status") == "draft"
        and "locale" not in call.request.url.params
    ]
    assert draft_no_locale


@pytest.mark.respx
def test_import_update_existing_and_missing_locale(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """UPDATE overwrites the existing locale and localizes the missing one."""
    export_data = _locale_export(_locale_entities())
    _mock_locales(respx_mock, "articles", "shared-doc", {"en"})
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(500, json={"error": {"message": "should not create"}})
    )
    update_route = respx_mock.put("http://localhost:1337/api/articles/shared-doc").mock(
        side_effect=[
            httpx.Response(
                200, json={"data": {"id": 1, "documentId": "shared-doc", "title": "Hello"}}
            ),
            httpx.Response(
                200, json={"data": {"id": 2, "documentId": "shared-doc", "title": "Bonjour"}}
            ),
        ]
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(
            export_data, ImportOptions(conflict_resolution=ConflictResolution.UPDATE)
        )

    assert result.success is True
    assert result.entities_updated == 1
    assert result.entities_imported == 1
    assert create_route.call_count == 0
    assert update_route.call_count == 2
    assert update_route.calls[0].request.url.params["locale"] == "en"
    assert update_route.calls[1].request.url.params["locale"] == "fr"


@pytest.mark.respx
def test_import_from_jsonl_relation_put_includes_locale(
    strapi_config: StrapiConfig, respx_mock: respx.Router, tmp_path: Path
) -> None:
    """JSONL pass 2 must send locale on the relation PUT."""
    author_schema = ContentTypeSchema(
        uid="api::author.author",
        display_name="Author",
        plural_name="authors",
        fields={"name": FieldSchema(type=FieldType.STRING)},
    )
    article_schema = ContentTypeSchema(
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
        },
    )
    export_data = ExportData(
        metadata=ExportMetadata(
            strapi_version="v5",
            source_url="http://localhost:1337",
            content_types=["api::author.author", "api::article.article"],
            total_entities=2,
            schemas={
                "api::author.author": author_schema,
                "api::article.article": article_schema,
            },
        ),
        entities={
            "api::author.author": [
                ExportedEntity(
                    id=1,
                    document_id="auth-src",
                    content_type="api::author.author",
                    data={"name": "Ada"},
                )
            ],
            "api::article.article": [
                ExportedEntity(
                    id=2,
                    document_id="art-src",
                    content_type="api::article.article",
                    data={"title": "Bonjour"},
                    relations={"author": ["auth-src"]},
                    locale="fr",
                )
            ],
        },
    )
    jsonl_path = tmp_path / "export.jsonl"
    with JSONLExportWriter(jsonl_path) as writer:
        writer.write_metadata(export_data.metadata)
        for content_type in export_data.metadata.content_types:
            for entity in export_data.entities[content_type]:
                writer.write_entity(entity)

    _mock_document_missing(respx_mock, "authors", "auth-src")
    _mock_document_missing(respx_mock, "articles", "art-src")
    respx_mock.post("http://localhost:1337/api/authors").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 9, "documentId": "auth-new", "name": "Ada"}}
        )
    )
    respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "documentId": "art-new", "title": "Bonjour"}}
        )
    )
    relation_route = respx_mock.put("http://localhost:1337/api/articles/art-new").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "documentId": "art-new", "title": "Bonjour"}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_from_jsonl(jsonl_path)

    assert result.success is True
    assert result.relations_imported == 1
    assert relation_route.calls.last.request.url.params["locale"] == "fr"


@pytest.mark.respx
def test_import_writes_nested_component_relation(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Nested seo[0].author is written on the component payload (#105)."""
    import json

    seo_schema, _, _ = _nested_component_schemas()
    export_data = _nested_component_export(include_component_schemas=False)
    relation_route, _ = _mock_nested_component_writes(respx_mock)

    with SyncClient(strapi_config) as client:
        importer = StrapiImporter(client)
        importer._schema_cache.cache_component_schema("shared.seo", seo_schema)
        result = importer.import_data(export_data)

    assert result.success is True
    assert result.relations_imported == 1
    body = json.loads(relation_route.calls.last.request.content)
    assert body["data"]["seo"][0]["metaTitle"] == "T"
    assert body["data"]["seo"][0]["author"] == "auth-new"


@pytest.mark.respx
def test_import_v4_destination_uses_numeric_relation_payload(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """A dest without documentIds writes numeric relation ids (#108)."""
    import json

    author_schema = ContentTypeSchema(
        uid="api::author.author",
        display_name="Author",
        plural_name="authors",
        fields={"name": FieldSchema(type=FieldType.STRING)},
    )
    article_schema = ContentTypeSchema(
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
        },
    )
    export_data = ExportData(
        metadata=ExportMetadata(
            strapi_version="v4",
            source_url="http://localhost:1337",
            content_types=["api::author.author", "api::article.article"],
            total_entities=2,
            schemas={
                "api::author.author": author_schema,
                "api::article.article": article_schema,
            },
        ),
        entities={
            "api::author.author": [
                ExportedEntity(
                    id=1,
                    content_type="api::author.author",
                    data={"name": "Ada"},
                )
            ],
            "api::article.article": [
                ExportedEntity(
                    id=2,
                    content_type="api::article.article",
                    data={"title": "Hello"},
                    relations={"author": [1]},
                )
            ],
        },
    )
    respx_mock.post("http://localhost:1337/api/authors").mock(
        return_value=httpx.Response(200, json={"data": {"id": 9, "attributes": {"name": "Ada"}}})
    )
    respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "attributes": {"title": "Hello"}}}
        )
    )
    relation_route = respx_mock.put("http://localhost:1337/api/articles/20").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "attributes": {"title": "Hello"}}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(export_data)

    assert result.success is True
    assert result.relations_imported == 1
    body = json.loads(relation_route.calls.last.request.content)
    assert body["data"]["author"] == 9


@pytest.mark.respx
def test_import_media_write_uses_dest_document_id(
    strapi_config: StrapiConfig, respx_mock: respx.Router, tmp_path: Path
) -> None:
    """Create payload uses dest file documentId, not remapped populate blobs (#106)."""
    import json

    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "5_cover.jpg").write_bytes(b"fake-image")
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "title": FieldSchema(type=FieldType.STRING),
            "cover": FieldSchema(type=FieldType.MEDIA),
        },
    )
    export_data = ExportData(
        metadata=ExportMetadata(
            strapi_version="v5",
            source_url="http://localhost:1337",
            content_types=["api::article.article"],
            total_entities=1,
            schemas={"api::article.article": article_schema},
        ),
        entities={
            "api::article.article": [
                ExportedEntity(
                    id=2,
                    document_id="art-src",
                    content_type="api::article.article",
                    data={
                        "title": "Hello",
                        "cover": {
                            "id": 5,
                            "documentId": "file-src",
                            "mime": "image/jpeg",
                            "url": "/uploads/old.jpg",
                        },
                    },
                )
            ],
        },
        media=[
            ExportedMediaFile(
                id=5,
                document_id="file-src",
                url="/uploads/old.jpg",
                name="cover.jpg",
                mime="image/jpeg",
                size=10,
                hash="abc",
                local_path="5_cover.jpg",
            )
        ],
    )
    _mock_document_missing(respx_mock, "articles", "art-src")
    respx_mock.post("http://localhost:1337/api/upload").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 50,
                    "documentId": "file-dest",
                    "name": "cover.jpg",
                    "alternativeText": "cover.jpg",
                    "hash": "abc",
                    "ext": ".jpg",
                    "mime": "image/jpeg",
                    "size": 0.01,
                    "url": "/uploads/new.jpg",
                    "provider": "local",
                    "createdAt": "2024-01-01T00:00:00.000Z",
                    "updatedAt": "2024-01-01T00:00:00.000Z",
                }
            ],
        )
    )
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "documentId": "art-new", "title": "Hello"}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(
            export_data,
            ImportOptions(overwrite_media=True),
            media_dir=media_dir,
        )

    assert result.warnings == []
    assert result.media_imported == 1
    assert result.success is True
    body = json.loads(create_route.calls.last.request.content)
    assert body["data"]["cover"] == "file-dest"
    assert "mime" not in body["data"]


@pytest.mark.respx
def test_import_nested_relation_put_uses_dest_media_not_source_blob(
    strapi_config: StrapiConfig, respx_mock: respx.Router, tmp_path: Path
) -> None:
    """seo[0].author PUT remaps dest media and must not resend source blobs."""
    import json

    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "7_og.jpg").write_bytes(b"fake-image")
    seo_schema = ContentTypeSchema(
        uid="shared.seo",
        display_name="SEO",
        fields={
            "metaTitle": FieldSchema(type=FieldType.STRING),
            "ogImage": FieldSchema(type=FieldType.MEDIA),
            "author": FieldSchema(
                type=FieldType.RELATION,
                relation=RelationType.MANY_TO_ONE,
                target="api::author.author",
            ),
        },
    )
    author_schema = ContentTypeSchema(
        uid="api::author.author",
        display_name="Author",
        plural_name="authors",
        fields={"name": FieldSchema(type=FieldType.STRING)},
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
    source_og = {
        "id": 7,
        "documentId": "file-src",
        "mime": "image/jpeg",
        "url": "/uploads/og.jpg",
    }
    export_data = ExportData(
        metadata=ExportMetadata(
            strapi_version="v5",
            source_url="http://localhost:1337",
            content_types=["api::author.author", "api::article.article"],
            total_entities=2,
            schemas={
                "api::author.author": author_schema,
                "api::article.article": article_schema,
            },
        ),
        entities={
            "api::author.author": [
                ExportedEntity(
                    id=1,
                    document_id="auth-src",
                    content_type="api::author.author",
                    data={"name": "Ada"},
                )
            ],
            "api::article.article": [
                ExportedEntity(
                    id=2,
                    document_id="art-src",
                    content_type="api::article.article",
                    data={
                        "title": "Hello",
                        "seo": [{"metaTitle": "T", "ogImage": source_og}],
                    },
                    relations={"seo[0].author": ["auth-src"]},
                )
            ],
        },
        media=[
            ExportedMediaFile(
                id=7,
                document_id="file-src",
                url="/uploads/og.jpg",
                name="og.jpg",
                mime="image/jpeg",
                size=10,
                hash="oghash",
                local_path="7_og.jpg",
            )
        ],
    )
    _mock_document_missing(respx_mock, "authors", "auth-src")
    _mock_document_missing(respx_mock, "articles", "art-src")
    respx_mock.post("http://localhost:1337/api/upload").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 70,
                    "documentId": "file-dest",
                    "name": "og.jpg",
                    "alternativeText": "og.jpg",
                    "hash": "oghash",
                    "ext": ".jpg",
                    "mime": "image/jpeg",
                    "size": 0.01,
                    "url": "/uploads/og-new.jpg",
                    "provider": "local",
                    "createdAt": "2024-01-01T00:00:00.000Z",
                    "updatedAt": "2024-01-01T00:00:00.000Z",
                }
            ],
        )
    )
    respx_mock.post("http://localhost:1337/api/authors").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 9, "documentId": "auth-new", "name": "Ada"}}
        )
    )
    respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "documentId": "art-new", "title": "Hello"}}
        )
    )
    relation_route = respx_mock.put("http://localhost:1337/api/articles/art-new").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "documentId": "art-new", "title": "Hello"}}
        )
    )

    with SyncClient(strapi_config) as client:
        importer = StrapiImporter(client)
        importer._schema_cache.cache_component_schema("shared.seo", seo_schema)
        result = importer.import_data(
            export_data,
            ImportOptions(overwrite_media=True),
            media_dir=media_dir,
        )

    assert result.success is True
    assert result.relations_imported == 1
    body = json.loads(relation_route.calls.last.request.content)
    seo0 = body["data"]["seo"][0]
    assert seo0["metaTitle"] == "T"
    assert seo0["author"] == "auth-new"
    assert seo0["ogImage"] == "file-dest"
    assert "mime" not in seo0
    assert "url" not in seo0
    dumped = json.dumps(body)
    assert "file-src" not in dumped
    assert "mime" not in dumped
    assert "/uploads/og.jpg" not in dumped
    # Source entity data must not be mutated.
    assert export_data.entities["api::article.article"][0].data["seo"][0]["ogImage"] == source_og


@pytest.mark.respx
def test_import_unwritten_nested_relation_is_error(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """A nested path that cannot be written fails the import (#105)."""
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
    author_schema = ContentTypeSchema(
        uid="api::author.author",
        display_name="Author",
        plural_name="authors",
        fields={"name": FieldSchema(type=FieldType.STRING)},
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
    export_data = ExportData(
        metadata=ExportMetadata(
            strapi_version="v5",
            source_url="http://localhost:1337",
            content_types=["api::author.author", "api::article.article"],
            total_entities=2,
            schemas={
                "api::author.author": author_schema,
                "api::article.article": article_schema,
            },
        ),
        entities={
            "api::author.author": [
                ExportedEntity(
                    id=1,
                    document_id="auth-src",
                    content_type="api::author.author",
                    data={"name": "Ada"},
                )
            ],
            "api::article.article": [
                ExportedEntity(
                    id=2,
                    document_id="art-src",
                    content_type="api::article.article",
                    data={"title": "Hello"},
                    relations={"seo[0].author": ["auth-src"]},
                )
            ],
        },
    )
    _mock_document_missing(respx_mock, "authors", "auth-src")
    _mock_document_missing(respx_mock, "articles", "art-src")
    respx_mock.post("http://localhost:1337/api/authors").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 9, "documentId": "auth-new", "name": "Ada"}}
        )
    )
    respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "documentId": "art-new", "title": "Hello"}}
        )
    )

    with SyncClient(strapi_config) as client:
        importer = StrapiImporter(client)
        importer._schema_cache.cache_component_schema("shared.seo", seo_schema)
        result = importer.import_data(export_data)

    assert result.success is False
    assert any("seo[0].author" in error for error in result.errors)


@pytest.mark.respx
def test_import_v4_destination_writes_nested_numeric_relation(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """A v4 dest nested seo[0].author PUT keeps scalars and numeric author id."""
    import json

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
    author_schema = ContentTypeSchema(
        uid="api::author.author",
        display_name="Author",
        plural_name="authors",
        fields={"name": FieldSchema(type=FieldType.STRING)},
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
    export_data = ExportData(
        metadata=ExportMetadata(
            strapi_version="v4",
            source_url="http://localhost:1337",
            content_types=["api::author.author", "api::article.article"],
            total_entities=2,
            schemas={
                "api::author.author": author_schema,
                "api::article.article": article_schema,
            },
        ),
        entities={
            "api::author.author": [
                ExportedEntity(
                    id=1,
                    content_type="api::author.author",
                    data={"name": "Ada"},
                )
            ],
            "api::article.article": [
                ExportedEntity(
                    id=2,
                    content_type="api::article.article",
                    data={"title": "Hello", "seo": [{"metaTitle": "T"}]},
                    relations={"seo[0].author": [1]},
                )
            ],
        },
    )
    respx_mock.post("http://localhost:1337/api/authors").mock(
        return_value=httpx.Response(200, json={"data": {"id": 9, "attributes": {"name": "Ada"}}})
    )
    respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "attributes": {"title": "Hello"}}}
        )
    )
    relation_route = respx_mock.put("http://localhost:1337/api/articles/20").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "attributes": {"title": "Hello"}}}
        )
    )

    with SyncClient(strapi_config) as client:
        importer = StrapiImporter(client)
        importer._schema_cache.cache_component_schema("shared.seo", seo_schema)
        result = importer.import_data(export_data)

    assert result.success is True
    assert result.relations_imported == 1
    body = json.loads(relation_route.calls.last.request.content)
    assert body["data"]["seo"][0]["metaTitle"] == "T"
    assert body["data"]["seo"][0]["author"] == 9


@pytest.mark.respx
def test_import_converts_unmapped_media_blobs_to_write_shape(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Create converts populate blobs even when no dest media mapping exists."""
    import json

    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
        plural_name="articles",
        fields={
            "title": FieldSchema(type=FieldType.STRING),
            "cover": FieldSchema(type=FieldType.MEDIA),
        },
    )
    export_data = ExportData(
        metadata=ExportMetadata(
            strapi_version="v5",
            source_url="http://localhost:1337",
            content_types=["api::article.article"],
            total_entities=1,
            schemas={"api::article.article": article_schema},
        ),
        entities={
            "api::article.article": [
                ExportedEntity(
                    id=2,
                    document_id="art-src",
                    content_type="api::article.article",
                    data={
                        "title": "Hello",
                        "cover": {
                            "id": 5,
                            "documentId": "file-src",
                            "mime": "image/jpeg",
                            "url": "/uploads/old.jpg",
                        },
                    },
                )
            ],
        },
    )
    _mock_document_missing(respx_mock, "articles", "art-src")
    create_route = respx_mock.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 20, "documentId": "art-new", "title": "Hello"}}
        )
    )

    with SyncClient(strapi_config) as client:
        result = StrapiImporter(client).import_data(export_data)

    assert result.success is True
    body = json.loads(create_route.calls.last.request.content)
    assert body["data"]["cover"] is None
    dumped = json.dumps(body)
    assert "mime" not in dumped
    assert "file-src" not in dumped
    assert "/uploads/old.jpg" not in dumped


def test_validate_relations_resolves_nested_paths(strapi_config: StrapiConfig) -> None:
    """``seo[0].author`` is validated against the component relation target."""
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
    author_schema = ContentTypeSchema(
        uid="api::author.author",
        display_name="Author",
        plural_name="authors",
        fields={"name": FieldSchema(type=FieldType.STRING)},
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
    export_data = ExportData(
        metadata=ExportMetadata(
            strapi_version="v5",
            source_url="http://localhost:1337",
            content_types=["api::author.author", "api::article.article"],
            total_entities=2,
            schemas={
                "api::author.author": author_schema,
                "api::article.article": article_schema,
            },
        ),
        entities={
            "api::author.author": [
                ExportedEntity(
                    id=1,
                    document_id="auth-src",
                    content_type="api::author.author",
                    data={"name": "Ada"},
                )
            ],
            "api::article.article": [
                ExportedEntity(
                    id=2,
                    document_id="art-src",
                    content_type="api::article.article",
                    data={"title": "Hello", "seo": [{"metaTitle": "T"}]},
                    relations={"seo[0].author": [99]},
                )
            ],
        },
    )
    result = ImportResult(success=False, dry_run=True)
    with SyncClient(strapi_config) as client:
        importer = StrapiImporter(client)
        importer._load_schemas_from_export(export_data)
        importer._schema_cache.cache_component_schema("shared.seo", seo_schema)
        importer._validate_relations(export_data, result)

    assert any("seo[0].author" in warning and "99" in warning for warning in result.warnings)
