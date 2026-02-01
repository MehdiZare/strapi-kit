"""Tests for export and import functionality."""

from datetime import datetime
from pathlib import Path

import httpx
import pytest
import respx

from strapi_kit import StrapiConfig, StrapiExporter, StrapiImporter
from strapi_kit.client.sync_client import SyncClient
from strapi_kit.exceptions import FormatError
from strapi_kit.models import (
    ExportData,
    ExportedEntity,
    ExportedMediaFile,
    ExportMetadata,
    ImportOptions,
)
from strapi_kit.utils.uid import uid_to_endpoint


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
    metadata = ExportMetadata(
        strapi_version="v5",
        source_url="http://localhost:1337",
        content_types=["api::article.article"],
        total_entities=2,
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


# Export Tests


@respx.mock
def test_export_content_types(strapi_config: StrapiConfig) -> None:
    """Test exporting content types."""
    # Mock paginated response
    respx.get("http://localhost:1337/api/articles").mock(
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


@respx.mock
def test_export_with_progress_callback(strapi_config: StrapiConfig) -> None:
    """Test export with progress callback."""
    respx.get("http://localhost:1337/api/articles").mock(
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


@respx.mock
def test_export_multiple_content_types(strapi_config: StrapiConfig) -> None:
    """Test exporting multiple content types."""
    respx.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 1, "documentId": "doc1", "title": "Article 1"}],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )

    respx.get("http://localhost:1337/api/authors").mock(
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


@respx.mock
def test_import_data_dry_run(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
) -> None:
    """Test import with dry run mode."""
    with SyncClient(strapi_config) as client:
        importer = StrapiImporter(client)
        options = ImportOptions(dry_run=True)

        result = importer.import_data(sample_export_data, options)

        assert result.dry_run
        assert result.entities_imported == 2
        assert result.entities_failed == 0
        # No actual API calls should be made in dry run


@respx.mock
def test_import_data_creates_entities(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
) -> None:
    """Test import actually creates entities."""
    # Mock create responses
    respx.post("http://localhost:1337/api/articles").mock(
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


@respx.mock
def test_import_with_validation_error(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
) -> None:
    """Test import handles validation errors."""
    # First succeeds, second fails
    respx.post("http://localhost:1337/api/articles").mock(
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


@respx.mock
def test_import_with_progress_callback(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
) -> None:
    """Test import with progress callback."""
    respx.post("http://localhost:1337/api/articles").mock(
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


def test_import_validation_warns_on_version_mismatch(
    strapi_config: StrapiConfig,
    sample_export_data: ExportData,
) -> None:
    """Test import validation warns about version mismatches."""
    # Modify export data to have different version
    sample_export_data.metadata.strapi_version = "v4"

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


# Model Tests


def test_export_metadata_model() -> None:
    """Test ExportMetadata model."""
    metadata = ExportMetadata(
        strapi_version="v5",
        source_url="http://localhost:1337",
        content_types=["api::article.article"],
        total_entities=10,
    )

    assert metadata.version == "1.0.0"  # Default
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


@respx.mock
def test_export_includes_schemas(strapi_config: StrapiConfig) -> None:
    """Test that export always includes schemas for relation resolution."""
    # Mock entity response
    respx.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"id": 1, "documentId": "doc1", "title": "Article 1"}],
                "meta": {"pagination": {"page": 1, "pageSize": 100, "pageCount": 1, "total": 1}},
            },
        )
    )

    # Mock schema response
    respx.get(
        "http://localhost:1337/api/content-type-builder/content-types/api::article.article"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "kind": "collectionType",
                    "info": {"displayName": "Article"},
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


@respx.mock
def test_import_resolves_relations_with_schema(strapi_config: StrapiConfig) -> None:
    """Test that import resolves relations correctly using schemas."""
    from strapi_kit.models.schema import ContentTypeSchema, FieldSchema, FieldType, RelationType

    # Create export data with schemas
    article_schema = ContentTypeSchema(
        uid="api::article.article",
        display_name="Article",
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

    # Mock author creation
    respx.post("http://localhost:1337/api/authors").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": 100, "documentId": "new-author-doc1", "name": "John Doe"}},
        )
    )

    # Mock article creation
    respx.post("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": 200, "documentId": "new-article-doc1", "title": "Article 1"}},
        )
    )

    # Mock relation update
    respx.put("http://localhost:1337/api/articles/200").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": 200, "documentId": "new-article-doc1", "title": "Article 1"}},
        )
    )

    with SyncClient(strapi_config) as client:
        importer = StrapiImporter(client)
        options = ImportOptions(skip_relations=False)
        result = importer.import_data(export_data, options)

        # Verify import succeeded
        assert result.success is True
        assert result.entities_imported == 2

        # Verify ID mapping was created
        assert "api::author.author" in result.id_mapping
        assert 5 in result.id_mapping["api::author.author"]
        assert result.id_mapping["api::author.author"][5] == 100

        assert "api::article.article" in result.id_mapping
        assert 1 in result.id_mapping["api::article.article"]
        assert result.id_mapping["api::article.article"][1] == 200
