"""REST collection path helpers.

Strapi REST collections are addressed by ``schema.pluralName`` (for example
``articles``, ``blog-posts``, ``people``). The content-type UID is an identity
key, not a URL path — never append ``s``, never use ``apiID``, and never split
the UID to invent a collection id.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

from strapi_kit.exceptions import ValidationError

_MISSING_PLURAL_NAME = (
    "Content type pluralName is missing or blank; "
    "REST collections are addressed by schema.pluralName, not the UID"
)


def collection_endpoint(content_type: object) -> str:
    """Return the REST collection id from ``pluralName`` / ``info.plural_name``.

    Accepts ``ContentTypeListItem``, ``ContentTypeSchema`` (Content-Type Builder
    or cached schema), or a mapping with ``info.pluralName`` / ``pluralName``.
    The UID is never used to construct the path.

    Args:
        content_type: Content type model or schema dict that includes
            ``pluralName``.

    Returns:
        REST collection id (e.g. ``blog-posts``).

    Raises:
        ValidationError: If ``pluralName`` is missing or blank. The UID is not
            consulted as a fallback.

    Examples:
        >>> from strapi_kit.models.content_type import ContentTypeListItem
        >>> item = ContentTypeListItem.model_validate({
        ...     "uid": "api::post.post",
        ...     "info": {"displayName": "Post", "pluralName": "blog-posts"},
        ... })
        >>> collection_endpoint(item)
        'blog-posts'
    """
    plural = _extract_plural_name(content_type)
    if plural is None or not plural.strip():
        raise ValidationError(
            _MISSING_PLURAL_NAME,
            details=_uid_details(content_type),
        )
    return plural.strip()


def document_endpoint(content_type: object, document_id: str | int) -> str:
    """Return ``{pluralName}/{percent-encoded document id}``.

    Joins :func:`collection_endpoint` with a document id encoded via
    ``urllib.parse.quote(..., safe="")`` so reserved characters (``/``, ``?``,
    space, ``%``, …) are safe in ``get_one`` / ``update`` / ``remove`` paths.

    Args:
        content_type: Content type model or schema dict that includes
            ``pluralName``.
        document_id: Document id (v5 ``documentId``) or numeric id (v4).

    Returns:
        Collection-relative REST path (e.g. ``blog-posts/abc%2F123``).

    Raises:
        ValidationError: If ``pluralName`` is missing or blank.

    Examples:
        >>> document_endpoint({"info": {"pluralName": "blog-posts"}}, "a/b")
        'blog-posts/a%2Fb'
    """
    collection = collection_endpoint(content_type)
    return f"{collection}/{quote(str(document_id), safe='')}"


def _extract_plural_name(content_type: object) -> str | None:
    """Read ``pluralName`` from a model or mapping. Never inspects the UID."""
    if isinstance(content_type, Mapping):
        return _plural_from_mapping(content_type)

    info = getattr(content_type, "info", None)
    if info is not None and _info_declares_plural(info):
        return _plural_from_info(info)

    for attr in ("plural_name", "pluralName"):
        if hasattr(content_type, attr):
            return _as_optional_str(getattr(content_type, attr))
    return None


def _plural_from_mapping(data: Mapping[str, Any]) -> str | None:
    """Extract ``pluralName`` from a dict (nested info first, then top-level)."""
    info = data.get("info")
    if isinstance(info, Mapping) and _mapping_has_plural(info):
        return _as_optional_str(_mapping_plural(info))
    if _mapping_has_plural(data):
        return _as_optional_str(_mapping_plural(data))
    return None


def _plural_from_info(info: object) -> str | None:
    """Extract ``pluralName`` from an ``info`` object or mapping."""
    if isinstance(info, Mapping):
        return _as_optional_str(_mapping_plural(info))
    for attr in ("plural_name", "pluralName"):
        if hasattr(info, attr):
            return _as_optional_str(getattr(info, attr))
    return None


def _info_declares_plural(info: object) -> bool:
    """Return True if ``info`` has a plural-name field (even when it is None)."""
    if isinstance(info, Mapping):
        return _mapping_has_plural(info)
    return hasattr(info, "plural_name") or hasattr(info, "pluralName")


def _mapping_has_plural(data: Mapping[str, Any]) -> bool:
    return "pluralName" in data or "plural_name" in data


def _mapping_plural(data: Mapping[str, Any]) -> Any:
    if "pluralName" in data:
        return data["pluralName"]
    return data.get("plural_name")


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise ValidationError(
        "Content type pluralName must be a string",
        details={"pluralName": value},
    )


def _uid_details(content_type: object) -> dict[str, Any]:
    """Include UID in error details for debugging only — never as a path."""
    uid: object
    if isinstance(content_type, Mapping):
        uid = content_type.get("uid")
    else:
        uid = getattr(content_type, "uid", None)
    if isinstance(uid, str) and uid:
        return {"uid": uid}
    return {}
