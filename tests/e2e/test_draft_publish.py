"""E2E tests for Strapi 5 Draft & Publish.

Covers live ``status=`` via ``StrapiQuery.with_document_status`` and
``publish`` / ``unpublish`` document actions.

This is not the article attribute named ``status`` used by
``FilterBuilder().eq("status", "published")`` in other e2e modules.
"""

from __future__ import annotations

import uuid

import pytest

from strapi_kit import SyncClient
from strapi_kit.models import (
    DocumentStatus,
    FilterBuilder,
    NormalizedCollectionResponse,
    StrapiQuery,
)


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
    return any(entity.document_id == document_id for entity in (response.data or []))


@pytest.mark.e2e
class TestDraftAndPublish:
    """Live Strapi 5 Draft & Publish: status= plus publish/unpublish."""

    def test_draft_is_hidden_until_publish(self, sync_client: SyncClient) -> None:
        """Create a draft, publish it into the default list, then unpublish."""
        unique = uuid.uuid4().hex[:12]
        title = f"E2E Draft Publish {unique}"
        document_id: str | None = None

        try:
            created = sync_client.create(
                "articles",
                {
                    "title": title,
                    "content": "Draft & Publish e2e coverage.",
                    "slug": f"e2e-draft-publish-{unique}",
                    # Article attribute, not v5 document status=.
                    "status": "draft",
                },
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

            published = sync_client.publish("articles", document_id)
            assert published.data is not None
            assert published.data.document_id == document_id
            assert published.data.published_at is not None

            default_after_publish = _list_by_title(sync_client, title)
            assert _has_document(default_after_publish, document_id)

            sync_client.unpublish("articles", document_id)

            default_after_unpublish = _list_by_title(sync_client, title)
            assert not _has_document(default_after_unpublish, document_id)

            drafts_after_unpublish = _list_by_title(sync_client, title, DocumentStatus.DRAFT)
            assert _has_document(drafts_after_unpublish, document_id)
        finally:
            if document_id is not None:
                sync_client.remove(f"articles/{document_id}")
