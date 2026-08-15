"""Pagination echo helpers for collection reads.

Stock Strapi silently caps ``pagination[pageSize]`` at the server ``maxLimit``
(default 100). Callers that trust ``len(data)`` or a missing/wrong
``meta.pagination.total`` can skip rows and report a complete import.

This helper is **opt-in**. ``get_many()`` does not call it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from strapi_kit.exceptions import ValidationError
from strapi_kit.models.response.meta import PaginationMeta, ResponseMeta

# Public alias: ResponseMeta, PaginationMeta, or a raw meta/pagination mapping.
PaginationEchoMeta = ResponseMeta | PaginationMeta | Mapping[str, Any]


def assert_pagination_echo(
    meta: PaginationEchoMeta | None,
    *,
    requested_page: int,
    requested_page_size: int,
) -> int:
    """Verify Strapi pagination echo against the requested page window.

    Stock Strapi echoes ``meta.pagination.{page, pageSize, total, pageCount}``.
    Some proxies stringify numbers (``"50"``) or drop ``page`` / ``pageSize``
    while leaving ``total``. A present but unreadable echo is not treated as
    "no echo".

    ``page_size > 100`` is unsafe against stock ``maxLimit`` (default 100)
    unless the Strapi server raises that limit. This helper does not change
    ``PagePagination``'s existing ``le=100`` cap.

    Args:
        meta: ``ResponseMeta``, ``PaginationMeta``, or a raw mapping. A mapping
            may be the ``meta`` object (``{"pagination": {...}}``) or the
            pagination object itself. ``None`` is treated as missing total.
        requested_page: Page number sent in the request (1-indexed).
        requested_page_size: Page size sent in the request.

    Returns:
        The echoed ``total`` as a non-negative int.

    Raises:
        ValidationError: If ``total`` is missing or unreadable, if a present
            ``page`` / ``pageSize`` is unreadable, or if a present echo does
            not match the requested page window.

    Examples:
        >>> from strapi_kit.models.response import assert_pagination_echo
        >>> total = assert_pagination_echo(
        ...     {"pagination": {"page": 1, "pageSize": 25, "total": 100}},
        ...     requested_page=1,
        ...     requested_page_size=25,
        ... )
        >>> total
        100
    """
    pagination = _extract_pagination_mapping(meta)

    if "total" not in pagination:
        raise ValidationError(
            "Pagination total is required",
            details={"reason": "total is missing"},
        )

    total = _parse_int(pagination["total"], "total", non_negative=True)

    if "page" in pagination:
        echoed_page = _parse_int(pagination["page"], "page")
        if echoed_page != requested_page:
            raise ValidationError(
                "Pagination page echo does not match the requested page",
                details={
                    "requested_page": requested_page,
                    "echo_page": echoed_page,
                },
            )

    echoed_page_size = _optional_page_size(pagination)
    if echoed_page_size is not None and echoed_page_size != requested_page_size:
        raise ValidationError(
            "Pagination pageSize echo does not match the requested page_size",
            details={
                "requested_page_size": requested_page_size,
                "echo_page_size": echoed_page_size,
            },
        )

    return total


def _extract_pagination_mapping(
    meta: PaginationEchoMeta | None,
) -> Mapping[str, Any]:
    """Normalize meta input to a raw pagination mapping.

    Args:
        meta: Response meta, pagination meta, raw mapping, or None.

    Returns:
        Mapping of pagination fields (may use camelCase or snake_case keys).

    Raises:
        ValidationError: If meta or pagination cannot be interpreted.
    """
    if meta is None:
        raise ValidationError(
            "Pagination total is required",
            details={"reason": "meta is missing"},
        )

    if isinstance(meta, ResponseMeta):
        if meta.pagination is None:
            raise ValidationError(
                "Pagination total is required",
                details={"reason": "pagination is missing"},
            )
        dumped: dict[str, Any] = meta.pagination.model_dump(by_alias=True, exclude_none=True)
        return dumped

    if isinstance(meta, PaginationMeta):
        pagination_dump: dict[str, Any] = meta.model_dump(by_alias=True, exclude_none=True)
        return pagination_dump

    if not isinstance(meta, Mapping):
        raise ValidationError(
            "Pagination meta must be a ResponseMeta, PaginationMeta, or mapping",
            details={"meta_type": type(meta).__name__},
        )

    if "pagination" not in meta:
        return meta

    pagination = meta["pagination"]
    if pagination is None:
        raise ValidationError(
            "Pagination total is required",
            details={"reason": "pagination is missing"},
        )
    if isinstance(pagination, PaginationMeta):
        nested_dump: dict[str, Any] = pagination.model_dump(by_alias=True, exclude_none=True)
        return nested_dump
    if not isinstance(pagination, Mapping):
        raise ValidationError(
            "Pagination metadata is unreadable",
            details={"pagination": pagination},
        )
    return pagination


def _optional_page_size(pagination: Mapping[str, Any]) -> int | None:
    """Parse pageSize when the key is present.

    Absent ``pageSize`` / ``page_size`` keys are tolerated (proxies strip them).
    A present key must parse as an int.

    Args:
        pagination: Pagination field mapping.

    Returns:
        Parsed page size, or None if the key is absent.

    Raises:
        ValidationError: If a present page size value is unreadable.
    """
    if "pageSize" in pagination:
        return _parse_int(pagination["pageSize"], "pageSize")
    if "page_size" in pagination:
        return _parse_int(pagination["page_size"], "pageSize")
    return None


def _parse_int(value: object, field: str, *, non_negative: bool = False) -> int:
    """Parse a pagination echo value as an int.

    Digit strings (``"12"``) are accepted. A leading minus (``"-1"``) is a
    negative int, not unreadable. ``bool`` is not an int.

    Args:
        value: Raw echo value.
        field: Field name for error messages (``total``, ``page``, ``pageSize``).
        non_negative: If True, reject values less than 0.

    Returns:
        Parsed integer.

    Raises:
        ValidationError: If the value is unreadable or out of range.
    """
    parsed: int | None = None
    if isinstance(value, bool):
        parsed = None
    elif isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        # Optional ASCII minus: "-1" is a negative int, not "unreadable".
        # isdigit() is False for signed strings, which hid the non-negative path.
        digits = value[1:] if value.startswith("-") else value
        if digits.isdigit():
            try:
                parsed = int(value)
            except ValueError:
                parsed = None

    if parsed is None:
        raise ValidationError(
            f"Pagination {field} is unreadable",
            details={field: value},
        )

    if non_negative and parsed < 0:
        raise ValidationError(
            f"Pagination {field} must be a non-negative integer",
            details={field: value},
        )

    return parsed
