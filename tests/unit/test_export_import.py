"""Tests for export and import functionality."""

from datetime import datetime
from pathlib import Path

import httpx
import pytest
import respx

from py_strapi import StrapiConfig, StrapiExporter, StrapiImporter
from py_strapi.client.sync_client import SyncClient
from py_strapi.models import (
    ExportData,
    ExportedEntity,
    ExportMetadata,
    ImportOptions,
)


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
        export_data = exporter.export_content_types(["api::article.article"])

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
        export_data = exporter.export_content_types(["api::article.article", "api::author.author"])

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
    """Test UID to endpoint conversion."""
    assert StrapiExporter._uid_to_endpoint("api::article.article") == "articles"
    assert StrapiExporter._uid_to_endpoint("api::author.author") == "authors"
    assert (
        StrapiExporter._uid_to_endpoint("api::category.category") == "categorys"
    )  # Simple pluralization


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

    with SyncClient(strapi_config) as client:
        # Client will report v5 (or auto)
        client._api_version = "v5"

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


def test_import_result_helpers() -> None:
    """Test ImportResult helper methods."""
    from py_strapi.models import ImportResult

    result = ImportResult(success=True, dry_run=False)
    result.entities_imported = 10
    result.entities_skipped = 2
    result.entities_failed = 1

    assert result.get_total_processed() == 13

    result.add_error("Test error")
    result.add_warning("Test warning")

    assert len(result.errors) == 1
    assert len(result.warnings) == 1
