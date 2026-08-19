"""Live e2e: import restores i18n localizations on the Docker fixture (#112)."""

from __future__ import annotations

import pytest

from strapi_kit import StrapiExporter, StrapiImporter, SyncClient
from strapi_kit.exceptions import ImportExportError
from strapi_kit.models import (
    ConflictResolution,
    DocumentStatus,
    ExportData,
    ExportedEntity,
    FilterBuilder,
    ImportOptions,
    StrapiQuery,
)

from .helpers import delete_document

_UID = "api::localized-article.localized-article"
_COLLECTION = "localized-articles"


def _draft_locale(locale: str) -> StrapiQuery:
    return StrapiQuery().with_locale(locale).with_document_status(DocumentStatus.DRAFT)


def _locales_for(client: SyncClient, document_id: str) -> set[str]:
    query = (
        StrapiQuery()
        .filter(FilterBuilder().eq("documentId", document_id))
        .with_locale("*")
        .with_document_status(DocumentStatus.DRAFT)
        .paginate(page=1, page_size=25)
    )
    response = client.get_many(_COLLECTION, query)
    found: set[str] = set()
    for entity in response.data:
        locale = entity.locale or entity.attributes.get("locale")
        if isinstance(locale, str) and locale:
            found.add(locale)
    return found


def _title_for(client: SyncClient, document_id: str, locale: str) -> str:
    response = client.get_one(
        _COLLECTION,
        query=_draft_locale(locale),
        document_id=document_id,
    )
    assert response.data is not None
    title = response.data.attributes.get("title")
    assert isinstance(title, str) and title
    return title


def _filter_export_to_document(export_data: ExportData, document_id: str) -> list[ExportedEntity]:
    """Keep only rows for ``document_id``; leftover collection rows flake asserts."""
    rows = [row for row in export_data.entities[_UID] if row.document_id == document_id]
    export_data.entities[_UID] = rows
    assert rows
    return rows


def _create_en_fr(client: SyncClient) -> str:
    created = client.create(
        _COLLECTION,
        {"title": "Hello", "body": "EN"},
        query=_draft_locale("en"),
    )
    assert created.data is not None
    document_id = created.data.document_id
    assert document_id
    updated = client.update(
        _COLLECTION,
        {"title": "Bonjour", "body": "FR"},
        document_id=document_id,
        query=_draft_locale("fr"),
    )
    assert updated.data is not None
    assert updated.data.document_id == document_id
    return document_id


def _delete_locale(client: SyncClient, document_id: str, locale: str) -> None:
    delete_document(client, _COLLECTION, document_id, locales=(locale,))


def _delete_document(client: SyncClient, document_id: str) -> None:
    delete_document(client, _COLLECTION, document_id, locales=("en", "fr"))


@pytest.mark.e2e
class TestI18nImportLocalizations:
    """Stock REST + Docker fixture checks for #104 / #110 localization restore."""

    def test_import_empty_dest_restores_en_and_fr(self, sync_client: SyncClient) -> None:
        """Export en+fr, delete dest, import → one documentId, two locales."""
        source_doc = _create_en_fr(sync_client)
        dest_doc: str | None = None
        try:
            exporter = StrapiExporter(sync_client)
            export_data = exporter.export_content_types([_UID], include_media=False)
            rows = _filter_export_to_document(export_data, source_doc)
            assert {row.locale for row in rows} >= {"en", "fr"}
            assert {row.document_id for row in rows} == {source_doc}

            _delete_document(sync_client, source_doc)
            assert _locales_for(sync_client, source_doc) == set()
            result = StrapiImporter(sync_client).import_data(export_data)
            assert result.success is True
            assert result.entities_imported == 2
            assert result.entities_skipped == 0
            dest_doc = result.doc_id_to_new_document_id[_UID][source_doc]
            assert dest_doc
            assert dest_doc != source_doc
            assert _locales_for(sync_client, dest_doc) == {"en", "fr"}
        finally:
            if dest_doc:
                _delete_document(sync_client, dest_doc)
            _delete_document(sync_client, source_doc)

    def test_skip_rewrites_only_the_deleted_locale(self, sync_client: SyncClient) -> None:
        """SKIP after deleting fr writes only the missing locale."""
        source_doc = _create_en_fr(sync_client)
        try:
            export_data = StrapiExporter(sync_client).export_content_types(
                [_UID], include_media=False
            )
            rows = _filter_export_to_document(export_data, source_doc)
            assert {row.locale for row in rows} >= {"en", "fr"}

            mutated_title = "Hello mutated"
            updated = sync_client.update(
                _COLLECTION,
                {"title": mutated_title},
                document_id=source_doc,
                query=_draft_locale("en"),
            )
            assert updated.data is not None
            assert updated.data.attributes.get("title") == mutated_title

            _delete_locale(sync_client, source_doc, "fr")
            assert "fr" not in _locales_for(sync_client, source_doc)

            result = StrapiImporter(sync_client).import_data(
                export_data, ImportOptions(conflict_resolution=ConflictResolution.SKIP)
            )
            assert result.success is True
            assert result.entities_skipped == 1
            assert result.entities_imported == 1
            assert result.doc_id_to_new_document_id[_UID][source_doc] == source_doc
            assert _locales_for(sync_client, source_doc) == {"en", "fr"}
            assert _title_for(sync_client, source_doc, "en") == mutated_title
        finally:
            _delete_document(sync_client, source_doc)

    def test_dest_with_only_fr_localizes_en_without_second_document(
        self, sync_client: SyncClient
    ) -> None:
        """Same-instance dest that only has fr gets en as a localization."""
        created = sync_client.create(
            _COLLECTION,
            {"title": "Bonjour", "body": "FR"},
            query=_draft_locale("fr"),
        )
        assert created.data is not None
        dest_doc = created.data.document_id
        assert dest_doc
        try:
            sync_client.update(
                _COLLECTION,
                {"title": "Hello", "body": "EN"},
                document_id=dest_doc,
                query=_draft_locale("en"),
            )
            export_data = StrapiExporter(sync_client).export_content_types(
                [_UID], include_media=False
            )
            rows = _filter_export_to_document(export_data, dest_doc)
            assert {row.locale for row in rows} >= {"en", "fr"}
            _delete_locale(sync_client, dest_doc, "en")
            assert _locales_for(sync_client, dest_doc) == {"fr"}

            result = StrapiImporter(sync_client).import_data(
                export_data, ImportOptions(conflict_resolution=ConflictResolution.SKIP)
            )
            assert result.success is True
            assert result.entities_imported == 1
            assert result.entities_skipped == 1
            assert result.doc_id_to_new_document_id[_UID][dest_doc] == dest_doc
            assert _locales_for(sync_client, dest_doc) == {"en", "fr"}
        finally:
            _delete_document(sync_client, dest_doc)

    def test_fail_writes_missing_locale_then_raises(self, sync_client: SyncClient) -> None:
        """FAIL writes missing fr, does not overwrite en, then raises (#117)."""
        source_doc = _create_en_fr(sync_client)
        try:
            export_data = StrapiExporter(sync_client).export_content_types(
                [_UID], include_media=False
            )
            rows = _filter_export_to_document(export_data, source_doc)
            assert {row.locale for row in rows} >= {"en", "fr"}
            _delete_locale(sync_client, source_doc, "fr")
            assert _locales_for(sync_client, source_doc) == {"en"}
            mutated_title = "Hello mutated"
            sync_client.update(
                _COLLECTION,
                {"title": mutated_title, "body": "EN"},
                document_id=source_doc,
                query=_draft_locale("en"),
            )

            with pytest.raises(ImportExportError, match="already exists"):
                StrapiImporter(sync_client).import_data(
                    export_data,
                    ImportOptions(conflict_resolution=ConflictResolution.FAIL),
                )

            assert _locales_for(sync_client, source_doc) == {"en", "fr"}
            assert _title_for(sync_client, source_doc, "en") == mutated_title
            assert _title_for(sync_client, source_doc, "fr") == "Bonjour"
        finally:
            _delete_document(sync_client, source_doc)
