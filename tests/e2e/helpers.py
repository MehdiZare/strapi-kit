"""Shared helpers for Docker-backed e2e tests."""

from __future__ import annotations

from collections.abc import Sequence

from strapi_kit import SyncClient
from strapi_kit.exceptions import NotFoundError, StrapiError


def delete_document(
    client: SyncClient,
    collection: str,
    document_id: str,
    *,
    locales: Sequence[str] | None = None,
) -> None:
    """Best-effort delete of a document (draft and/or per-locale).

    Strapi 5.34 500s ``DELETE ?status=draft`` for draft-only i18n rows
    (``Cannot delete a draft document``). Per-locale DELETE without
    ``status`` returns 204. Non-i18n types still try published remove
    then ``status=draft``.
    """
    if locales:
        path = client.document_path(collection, document_id)
        for locale in locales:
            try:
                client.delete(path, params={"locale": locale})
            except (NotFoundError, StrapiError):
                pass
        return
    try:
        client.remove(f"{collection}/{document_id}")
    except StrapiError:
        pass
    try:
        client.delete(f"{collection}/{document_id}", params={"status": "draft"})
    except StrapiError:
        pass
