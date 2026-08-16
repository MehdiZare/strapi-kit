"""Helpers for Strapi 5 REST relation write payloads.

Strapi 5 relation writes take **documentId** strings, not numeric ``id``.
Many-side fields use ``set`` / ``connect`` / ``disconnect`` objects. One-side
fields take a documentId string or ``None``. v4 ``{ connect: [{ id: 1 }] }``
shapes are not produced.

Examples:
    >>> from strapi_kit.models.enums import RelationWriteOp
    >>> relation_write(document_ids=["abc"], multiple=False)
    'abc'
    >>> relation_write(document_ids=[], multiple=False) is None
    True
    >>> relation_write(document_ids=["a", "b"], multiple=True)
    {'set': ['a', 'b']}
    >>> relation_write(
    ...     document_ids=["c"],
    ...     multiple=True,
    ...     op=RelationWriteOp.CONNECT,
    ... )
    {'connect': ['c']}
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal, overload

from strapi_kit.exceptions import ValidationError
from strapi_kit.models.enums import RelationWriteOp

RelationIdInput = str | Mapping[str, object]
RelationWritePayload = str | None | dict[str, list[str]]


def _normalize_document_id(value: object, index: int) -> str:
    """Normalize a relation target to a Strapi 5 documentId string.

    Args:
        value: A documentId string or ``{"documentId": "..."}`` object.
        index: Position in ``document_ids`` (included in error details).

    Returns:
        Non-empty documentId string.

    Raises:
        ValidationError: If the value is empty or not a documentId.
    """
    if isinstance(value, str):
        document_id = value.strip()
        if not document_id:
            raise ValidationError(
                "Relation write documentId must be a non-empty string",
                details={"index": index, "value": value},
            )
        return document_id

    if isinstance(value, Mapping):
        raw = value.get("documentId", value.get("document_id"))
        if isinstance(raw, str):
            document_id = raw.strip()
            if document_id:
                return document_id
        raise ValidationError(
            'Relation write objects must include a non-empty "documentId"',
            details={"index": index, "value": dict(value)},
        )

    raise ValidationError(
        "Relation write ids must be documentId strings or "
        '{"documentId": "..."} objects, not numeric id',
        details={"index": index, "value": value},
    )


def _normalize_document_ids(document_ids: Sequence[RelationIdInput]) -> list[str]:
    """Validate and normalize a sequence of relation targets.

    Args:
        document_ids: documentId strings and/or ``{"documentId": "..."}`` objects.

    Returns:
        New list of documentId strings.

    Raises:
        ValidationError: If ``document_ids`` is a bare string/mapping or an
            item cannot be normalized.
    """
    # str/bytes are Sequences; iterating them would split a documentId.
    if isinstance(document_ids, (str, bytes)) or not isinstance(document_ids, Sequence):
        raise ValidationError(
            "document_ids must be a sequence of documentId values, not a single string",
            details={"document_ids": document_ids},
        )
    return [_normalize_document_id(value, index) for index, value in enumerate(document_ids)]


def _coerce_relation_write_op(op: object) -> RelationWriteOp:
    """Resolve ``op`` to a :class:`RelationWriteOp`.

    Accepts the enum or its official string values (``set`` / ``connect`` /
    ``disconnect``). Invalid values raise :class:`ValidationError` instead of
    ``AttributeError`` from ``op.value``.

    Args:
        op: A ``RelationWriteOp`` member or its ``.value`` string.

    Returns:
        The matching ``RelationWriteOp``.

    Raises:
        ValidationError: If ``op`` is not a known relation write operation.
    """
    if isinstance(op, RelationWriteOp):
        return op
    if isinstance(op, str):
        try:
            return RelationWriteOp(op)
        except ValueError as e:
            raise ValidationError(
                "op must be a RelationWriteOp (set, connect, or disconnect)",
                details={"op": op},
            ) from e
    raise ValidationError(
        "op must be a RelationWriteOp (set, connect, or disconnect)",
        details={"op": op},
    )


@overload
def relation_write(
    *,
    document_ids: Sequence[RelationIdInput],
    multiple: Literal[False],
    op: RelationWriteOp = RelationWriteOp.SET,
) -> str | None: ...


@overload
def relation_write(
    *,
    document_ids: Sequence[RelationIdInput],
    multiple: Literal[True],
    op: RelationWriteOp = RelationWriteOp.SET,
) -> dict[str, list[str]]: ...


@overload
def relation_write(
    *,
    document_ids: Sequence[RelationIdInput],
    multiple: bool,
    op: RelationWriteOp = RelationWriteOp.SET,
) -> RelationWritePayload: ...


def relation_write(
    *,
    document_ids: Sequence[RelationIdInput],
    multiple: bool,
    op: RelationWriteOp = RelationWriteOp.SET,
) -> RelationWritePayload:
    """Build a Strapi 5 REST relation write value.

    v5 relation writes take **documentId** strings, not numeric ``id``.
    One-side fields (``multiple=False``) accept 0 or 1 id and return that
    documentId or ``None``. Many-side fields (``multiple=True``) return
    ``{op: [documentIds]}``.

    ``{"documentId": "..."}`` (and ``{"document_id": "..."}``) objects are
    normalized to the short string form Strapi 5 REST accepts.

    Args:
        document_ids: Target documentIds (strings or ``{"documentId": "..."}``).
        multiple: ``False`` for one-side relations; ``True`` for many-side.
        op: Many-side operator. Defaults to :attr:`RelationWriteOp.SET`.
            Ignored when ``multiple`` is ``False``.

    Returns:
        A documentId string, ``None`` (clears a one-side relation), or
        ``{op.value: [documentIds]}`` for many-side writes.

    Raises:
        ValidationError: If a one-side write receives 2+ ids, ``op`` is not a
            :class:`RelationWriteOp`, ``document_ids`` is a bare string, or an
            item is not a documentId.

    Examples:
        >>> relation_write(document_ids=["authorDoc"], multiple=False)
        'authorDoc'
        >>> relation_write(document_ids=[], multiple=False) is None
        True
        >>> relation_write(document_ids=["a", "b"], multiple=True)
        {'set': ['a', 'b']}
    """
    resolved_op = _coerce_relation_write_op(op)
    ids = _normalize_document_ids(document_ids)

    if not multiple:
        if len(ids) > 1:
            raise ValidationError(
                "One-side relation writes accept at most one documentId",
                details={"count": len(ids), "document_ids": ids},
            )
        return ids[0] if ids else None

    return {resolved_op.value: ids}
