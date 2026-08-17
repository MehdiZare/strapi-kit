"""Live e2e: import restores i18n localizations on the Docker fixture (#112)."""

from __future__ import annotations

import pytest

from strapi_kit import StrapiExporter, StrapiImporter, SyncClient
from strapi_kit.models import (
    ConflictResolution,
    DocumentStatus,
    FilterBuilder,
    ImportOptions,
    StrapiQuery,
)

_UID = "api::localized-article.localized-article"
_COLLECTION = "localized-articles"


def _draft_locale(locale: str) -> StrapiQuery:
    return StrapiQuery().with_locale(locale).with_document_status(DocumentStatus.DRAFT)


def _locales_for(client: SyncClient, document_id: str) -> set[str]:
    query = (
        StrapiQuery()
        .filter(FilterBuilder().eq("documentId", document_id))
        .with_locale("all")
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
    path = client.document_path(_COLLECTION, document_id)
    client.delete(path, params={"locale": locale, "status": "draft"})


def _delete_document(client: SyncClient, document_id: str) -> None:
    try:
        client.remove(_COLLECTION, document_id=document_id)
    except Exception:  # noqa: BLE001 - cleanup
        pass


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
            rows = export_data.entities[_UID]
            assert {row.locale for row in rows} >= {"en", "fr"}
            assert {row.document_id for row in rows} == {source_doc}

            _delete_document(sync_client, source_doc)
            result = StrapiImporter(sync_client).import_data(export_data)
            assert result.success is True
            dest_doc = result.doc_id_to_new_document_id[_UID][source_doc]
            assert dest_doc
            assert _locales_for(sync_client, dest_doc) >= {"en", "fr"}
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
            _delete_locale(sync_client, source_doc, "fr")
            assert "fr" not in _locales_for(sync_client, source_doc)

            result = StrapiImporter(sync_client).import_data(
                export_data, ImportOptions(conflict_resolution=ConflictResolution.SKIP)
            )
            assert result.success is True
            assert result.entities_skipped >= 1
            assert result.entities_imported >= 1
            assert result.doc_id_to_new_document_id[_UID][source_doc] == source_doc
            assert _locales_for(sync_client, source_doc) >= {"en", "fr"}
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
            _delete_locale(sync_client, dest_doc, "en")
            assert _locales_for(sync_client, dest_doc) == {"fr"}

            result = StrapiImporter(sync_client).import_data(
                export_data, ImportOptions(conflict_resolution=ConflictResolution.SKIP)
            )
            assert result.success is True
            assert result.entities_imported >= 1
            assert result.doc_id_to_new_document_id[_UID][dest_doc] == dest_doc
            assert _locales_for(sync_client, dest_doc) >= {"en", "fr"}
        finally:
            _delete_document(sync_client, dest_doc)
