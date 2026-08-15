"""E2E tests for Strapi 5 Draft & Publish.

Covers live REST ``status=`` via ``StrapiQuery.with_document_status`` on
list and on publish-on-write (``PUT ?status=published``).

``SyncClient.publish`` / ``unpublish`` hit ``/api/.../actions/*``. Stock
Strapi 5 public REST does not register those routes (see #65); the
helper test skips on 404/405 instead of failing this file.

This module does not write or filter the article ``status`` enum
attribute used by other e2e modules (``FilterBuilder().eq("status",
...)``). That field collides with reserved D&P ``status`` (see #68).
"""

from __future__ import annotations

import uuid

import pytest

from strapi_kit import SyncClient
from strapi_kit.exceptions import MethodNotAllowedError, NotFoundError, StrapiError
from strapi_kit.models import (
    DocumentStatus,
    FilterBuilder,
    NormalizedCollectionResponse,
    StrapiQuery,
)


def _unique_article() -> tuple[str, dict[str, str]]:
    """Return ``(title, create payload)`` without the ``status`` attribute."""
    unique = uuid.uuid4().hex[:12]
    title = f"E2E Draft Publish {unique}"
    payload = {
        "title": title,
        "content": "Draft & Publish e2e coverage.",
        "slug": f"e2e-draft-publish-{unique}",
    }
    return title, payload


def _list_by_title(
    client: SyncClient,
    title: str,
    document_status: DocumentStatus | None = None,
) -> NormalizedCollectionResponse:
    """List articles matching ``title``, optionally with v5 ``status=``."""
    query = StrapiQuery().filter(FilterBuilder().eq("title", title))
    if document_status is not None:
        query = query.with_document_status(document_status)
    return client.get_many("articles", query=query)


def _has_document(response: NormalizedCollectionResponse, document_id: str) -> bool:
    """Return True if ``document_id`` appears in a collection response."""
    return any(entity.document_id == document_id for entity in response.data)


def _delete_article(client: SyncClient, document_id: str) -> None:
    """Best-effort delete of published and draft versions."""
    try:
        client.remove(f"articles/{document_id}")
    except StrapiError:
        pass
    try:
        client.delete(f"articles/{document_id}", params={"status": "draft"})
    except StrapiError:
        pass


@pytest.mark.e2e
class TestDraftAndPublish:
    """Live Strapi 5 Draft & Publish: ``status=`` plus publish/unpublish."""

    def test_draft_is_hidden_until_status_published_write(self, sync_client: SyncClient) -> None:
        """Create a draft via ``status=draft``; publish via ``status=published``."""
        title, payload = _unique_article()
        document_id: str | None = None

        try:
            created = sync_client.create(
                "articles",
                payload,
                query=StrapiQuery().with_document_status(DocumentStatus.DRAFT),
            )
            assert created.data is not None
            document_id = created.data.document_id
            assert document_id is not None
            assert created.data.published_at is None

            drafts = _list_by_title(sync_client, title, DocumentStatus.DRAFT)
            assert _has_document(drafts, document_id)

            default_list = _list_by_title(sync_client, title)
            assert not _has_document(default_list, document_id)

            published_list = _list_by_title(sync_client, title, DocumentStatus.PUBLISHED)
            assert not _has_document(published_list, document_id)

            # Stock REST publish-on-write: PUT /api/articles/:id?status=published
            published = sync_client.update(
                f"articles/{document_id}",
                {"title": title},
                query=StrapiQuery().with_document_status(DocumentStatus.PUBLISHED),
            )
            assert published.data is not None
            assert published.data.document_id == document_id
            assert published.data.published_at is not None

            default_after_publish = _list_by_title(sync_client, title)
            assert _has_document(default_after_publish, document_id)

            published_after = _list_by_title(sync_client, title, DocumentStatus.PUBLISHED)
            assert _has_document(published_after, document_id)
        finally:
            if document_id is not None:
                _delete_article(sync_client, document_id)

    def test_publish_unpublish_document_actions(self, sync_client: SyncClient) -> None:
        """Live-check ``publish`` / ``unpublish`` helpers (depends on #65)."""
        title, payload = _unique_article()
        document_id: str | None = None

        try:
            created = sync_client.create(
                "articles",
                payload,
                query=StrapiQuery().with_document_status(DocumentStatus.DRAFT),
            )
            assert created.data is not None
            document_id = created.data.document_id
            assert document_id is not None

            try:
                published = sync_client.publish("articles", document_id)
            except (NotFoundError, MethodNotAllowedError) as exc:
                pytest.skip(
                    "stock Strapi 5 REST does not register "
                    f"/api/.../actions/publish ({exc}); see #65"
                )

            assert published.data is not None
            assert published.data.document_id == document_id
            assert published.data.published_at is not None
            assert _has_document(_list_by_title(sync_client, title), document_id)

            try:
                unpublished = sync_client.unpublish("articles", document_id)
            except (NotFoundError, MethodNotAllowedError) as exc:
                pytest.skip(
                    "stock Strapi 5 REST does not register "
                    f"/api/.../actions/unpublish ({exc}); see #65"
                )
            if unpublished.data is not None:
                assert unpublished.data.published_at is None

            assert not _has_document(_list_by_title(sync_client, title), document_id)
            assert _has_document(
                _list_by_title(sync_client, title, DocumentStatus.DRAFT),
                document_id,
            )
        finally:
            if document_id is not None:
                _delete_article(sync_client, document_id)
