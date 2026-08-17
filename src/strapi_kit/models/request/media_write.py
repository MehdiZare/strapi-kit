"""Helpers for Strapi media field write payloads.

Media writes take a destination file ``documentId`` string or numeric ``id``.
Populate objects (``mime``, ``url``, source ``documentId``) are not a write
shape and reconnect the origin file on v5.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, overload

from strapi_kit.exceptions import ValidationError

MediaWriteId = int | str
MediaWritePayload = MediaWriteId | None | list[MediaWriteId]


def _normalize_media_id(value: object, index: int) -> MediaWriteId:
    """Normalize one media target to a dest ``documentId`` or numeric id."""
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, str):
            document_id = value.strip()
            if document_id:
                return document_id
        raise ValidationError(
            "Media write ids must be dest documentId strings or numeric ids",
            details={"index": index, "value": value},
        )
    if value < 1:
        raise ValidationError(
            "Media write numeric id must be a positive int",
            details={"index": index, "value": value},
        )
    return value


@overload
def media_write(
    *,
    file_ids: Sequence[MediaWriteId],
    multiple: Literal[False],
) -> MediaWriteId | None: ...


@overload
def media_write(
    *,
    file_ids: Sequence[MediaWriteId],
    multiple: Literal[True],
) -> list[MediaWriteId]: ...


@overload
def media_write(
    *,
    file_ids: Sequence[MediaWriteId],
    multiple: bool,
) -> MediaWritePayload: ...


def media_write(
    *,
    file_ids: Sequence[MediaWriteId],
    multiple: bool,
) -> MediaWritePayload:
    """Build a media field write value.

    One-side fields (``multiple=False``) accept 0 or 1 id and return that
    dest ``documentId`` / numeric id, or ``None`` to clear. Many-side fields
    return a list (empty list clears).

    Args:
        file_ids: Destination file documentIds and/or numeric ids.
        multiple: ``False`` for a single media field; ``True`` for a list.

    Returns:
        A dest id, ``None``, or a list of dest ids.

    Raises:
        ValidationError: If a one-side write receives 2+ ids, ``file_ids`` is
            a bare string, or an item is not a dest id.
    """
    if isinstance(file_ids, (str, bytes)) or not isinstance(file_ids, Sequence):
        raise ValidationError(
            "file_ids must be a sequence of dest media ids, not a single string",
            details={"file_ids": file_ids},
        )
    ids = [_normalize_media_id(value, index) for index, value in enumerate(file_ids)]
    if not multiple:
        if len(ids) > 1:
            raise ValidationError(
                "One-side media writes accept at most one dest id",
                details={"count": len(ids), "file_ids": ids},
            )
        return ids[0] if ids else None
    return ids
