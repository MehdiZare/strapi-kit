"""Strapi v5 Blocks rich text (JSON) ↔ Markdown converters.

Strapi 5 stores the Blocks editor as a JSON tree (the
``@strapi/blocks-react-renderer`` schema), not a markdown string.
Classic ``richtext`` fields remain markdown/strings and are not handled here.

``blocks_to_markdown`` walks official nodes and is never silently lossy:
every unsupported construct is recorded in ``MarkdownConversion.lossy_reasons``.

``markdown_to_blocks`` is a best-effort write path for creates/updates. It
recognizes block-level Markdown only. Inline Markdown such as ``**bold**`` or
``[text](url)`` is stored as literal text, not marks or link nodes.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

# Official root/inline types from @strapi/blocks-react-renderer.
_BLOCK_TYPES: Final[frozenset[str]] = frozenset(
    {"paragraph", "heading", "list", "quote", "code", "image"}
)
_MARK_KEYS: Final[frozenset[str]] = frozenset(
    {"bold", "italic", "underline", "strikethrough", "code"}
)
_TEXT_NODE_KEYS: Final[frozenset[str]] = frozenset({"type", "text", *_MARK_KEYS, "children"})

_REASON_UNDERLINE: Final[str] = "underline mark has no markdown equivalent"
_REASON_IMAGE_NO_URL: Final[str] = "image dropped because it has no URL"
_REASON_LINK_NO_URL: Final[str] = "link has no URL; kept link text"
_REASON_UNKNOWN_BLOCK: Final[str] = "unknown block type flattened to text"
_REASON_UNKNOWN_INLINE: Final[str] = "unknown inline type flattened to text"
_REASON_MALFORMED: Final[str] = "malformed non-object node skipped"
_REASON_HEADING_LEVEL: Final[str] = "heading level is outside 1-6"
_REASON_UNKNOWN_MARK: Final[str] = "unknown mark dropped"

_HEADING_RE: Final[re.Pattern[str]] = re.compile(r"^(#{1,6})[ \t]+(.*)$")
_UL_RE: Final[re.Pattern[str]] = re.compile(r"^[*+-][ \t]+(.*)$")
_OL_RE: Final[re.Pattern[str]] = re.compile(r"^\d+\.[ \t]+(.*)$")
_FENCE_RE: Final[re.Pattern[str]] = re.compile(r"^(`{3,}|~{3,})(.*)$")
_QUOTE_RE: Final[re.Pattern[str]] = re.compile(r"^>[ \t]?(.*)$")

__all__ = [
    "MarkdownConversion",
    "blocks_to_markdown",
    "markdown_to_blocks",
]


@dataclass(frozen=True)
class MarkdownConversion:
    """Result of converting Strapi Blocks JSON to Markdown.

    Attributes:
        markdown: Converted Markdown document.
        lossy_reasons: Unique lossy-conversion reasons in first-seen order.
            Empty if and only if the conversion is faithful.
    """

    markdown: str
    lossy_reasons: tuple[str, ...]


class _ReasonCollector:
    """Collect unique lossy-conversion reasons in first-seen order."""

    def __init__(self) -> None:
        self._reasons: list[str] = []
        self._seen: set[str] = set()

    def add(self, reason: str) -> None:
        if reason not in self._seen:
            self._seen.add(reason)
            self._reasons.append(reason)

    def as_tuple(self) -> tuple[str, ...]:
        return tuple(self._reasons)


def blocks_to_markdown(blocks: Sequence[object] | None) -> MarkdownConversion:
    """Convert a Strapi v5 Blocks tree to Markdown.

    Supported nodes: ``paragraph``, ``heading`` (levels 1–6), ``list``
    (``ordered`` / ``unordered``) with ``list-item``, ``quote``, ``code``,
    ``image``, ``link``, and ``text``. Marks: bold, italic, strikethrough, code.

    Plain-text leaves are escaped **before** marks are applied so source
    ``**literal**`` cannot invent emphasis.

    Lossy cases (never silent):

    - ``underline`` — text is kept; a reason is recorded
    - image/link without a URL — image dropped / link text kept
    - unknown block/inline types — flattened to plain text or dropped
    - malformed (non-object) nodes — skipped

    Args:
        blocks: Blocks field value (a list of root nodes). ``None`` or an empty
            list yields empty markdown with no reasons.

    Returns:
        Markdown plus deduplicated ``lossy_reasons`` (empty iff faithful).
    """
    reasons = _ReasonCollector()
    if blocks is None:
        return MarkdownConversion(markdown="", lossy_reasons=())
    if isinstance(blocks, (str, bytes)) or not isinstance(blocks, Sequence):
        reasons.add(_REASON_MALFORMED)
        return MarkdownConversion(markdown="", lossy_reasons=reasons.as_tuple())

    parts: list[str] = []
    for node in blocks:
        converted = _convert_block(node, reasons)
        if converted is not None:
            parts.append(converted)

    return MarkdownConversion(markdown="\n\n".join(parts), lossy_reasons=reasons.as_tuple())


def markdown_to_blocks(markdown: str) -> list[dict[str, Any]]:
    """Convert Markdown to a Strapi v5 Blocks tree (best-effort write path).

    Recognized block constructs: ATX headings (levels 1–6), paragraphs, fenced
    code, ordered/unordered lists, and blockquotes.

    This is **not** a full CommonMark parser. Inline Markdown (emphasis, links,
    images, inline code) is stored as literal text nodes. Images are not
    uploaded; a line such as ``![alt](url)`` becomes a paragraph of that text.

    Empty or whitespace-only input is pinned to a single empty paragraph::

        [{"type": "paragraph", "children": [{"type": "text", "text": ""}]}]

    Args:
        markdown: Markdown source.

    Returns:
        A list of Blocks root nodes suitable for a ``blocks`` field.
    """
    if not markdown or not markdown.strip():
        return [_empty_paragraph()]

    normalized = markdown.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    blocks: list[dict[str, Any]] = []
    index = 0
    total = len(lines)

    while index < total:
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        fence = _FENCE_RE.match(line)
        if fence:
            block, index = _consume_fence(lines, index, fence)
            blocks.append(block)
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            blocks.append(_heading_block(len(heading.group(1)), heading.group(2).rstrip()))
            index += 1
            continue

        if _UL_RE.match(line):
            block, index = _consume_list(lines, index, ordered=False)
            blocks.append(block)
            continue

        if _OL_RE.match(line):
            block, index = _consume_list(lines, index, ordered=True)
            blocks.append(block)
            continue

        if _QUOTE_RE.match(line):
            block, index = _consume_quote(lines, index)
            blocks.append(block)
            continue

        block, index = _consume_paragraph(lines, index)
        blocks.append(block)

    return blocks if blocks else [_empty_paragraph()]


def _empty_paragraph() -> dict[str, Any]:
    return {
        "type": "paragraph",
        "children": [{"type": "text", "text": ""}],
    }


def _text_node(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def _heading_block(level: int, text: str) -> dict[str, Any]:
    return {"type": "heading", "level": level, "children": [_text_node(text)]}


def _paragraph_block(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "children": [_text_node(text)]}


def _list_item_block(text: str) -> dict[str, Any]:
    return {"type": "list-item", "children": [_text_node(text)]}


def _escape_markdown(text: str) -> str:
    """Escape markdown metacharacters so leaf text cannot invent formatting."""
    if not text:
        return text
    out: list[str] = []
    for char in text:
        if char in {"\\", "`", "*", "_", "[", "]", "~"}:
            out.append("\\")
        out.append(char)
    return "".join(out)


def _iter_children(node: Mapping[str, object]) -> Sequence[object]:
    children = node.get("children")
    if isinstance(children, Sequence) and not isinstance(children, (str, bytes)):
        return children
    return ()


def _as_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _heading_level(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _first_nonempty_str(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return ""


def _fence_for(text: str) -> str:
    longest = 0
    for match in re.finditer(r"`+", text):
        longest = max(longest, len(match.group()))
    return "`" * max(3, longest + 1)


def _extract_plain_text(node: object, reasons: _ReasonCollector) -> str:
    if isinstance(node, str):
        return node
    if not isinstance(node, Mapping):
        reasons.add(_REASON_MALFORMED)
        return ""
    raw = node.get("text")
    text = raw if isinstance(raw, str) else ""
    if raw is not None and not isinstance(raw, str):
        reasons.add(_REASON_MALFORMED)
        text = str(raw)
    if text:
        return text
    return "".join(_extract_plain_text(child, reasons) for child in _iter_children(node))


def _extract_code_text(node: Mapping[str, object], reasons: _ReasonCollector) -> str:
    children = _iter_children(node)
    if children:
        parts: list[str] = []
        for child in children:
            if isinstance(child, Mapping):
                raw = child.get("text")
                if isinstance(raw, str):
                    parts.append(raw)
                else:
                    parts.append(_extract_plain_text(child, reasons))
            elif isinstance(child, str):
                parts.append(child)
            else:
                reasons.add(_REASON_MALFORMED)
        return "".join(parts)
    plain = node.get("plainText")
    return plain if isinstance(plain, str) else ""


def _apply_marks(text: str, node: Mapping[str, object], reasons: _ReasonCollector) -> str:
    if node.get("underline") is True:
        reasons.add(_REASON_UNDERLINE)
    for key, value in node.items():
        if key not in _TEXT_NODE_KEYS and value is True:
            reasons.add(_REASON_UNKNOWN_MARK)
    if not text:
        return text
    # Innermost: code, then strikethrough, italic, bold.
    if node.get("code") is True:
        text = f"`{text}`"
    if node.get("strikethrough") is True:
        text = f"~~{text}~~"
    if node.get("italic") is True:
        text = f"_{text}_"
    if node.get("bold") is True:
        text = f"**{text}**"
    return text


def _convert_inline(node: object, reasons: _ReasonCollector) -> str:
    if not isinstance(node, Mapping):
        reasons.add(_REASON_MALFORMED)
        return ""

    ntype = node.get("type")
    if ntype == "text":
        raw = node.get("text", "")
        if raw is None:
            text = ""
        elif isinstance(raw, str):
            text = raw
        else:
            reasons.add(_REASON_MALFORMED)
            text = str(raw)
        return _apply_marks(_escape_markdown(text), node, reasons)

    if ntype == "link":
        inner = _convert_inlines(_iter_children(node), reasons)
        url = _as_str(node.get("url"))
        if not url:
            reasons.add(_REASON_LINK_NO_URL)
            return inner
        if ")" in url or " " in url:
            return f"[{inner}](<{url}>)"
        return f"[{inner}]({url})"

    if ntype == "list-item":
        return _convert_inlines(_iter_children(node), reasons)

    if isinstance(ntype, str) and ntype in _BLOCK_TYPES:
        converted = _convert_block(node, reasons)
        return converted if converted is not None else ""

    reasons.add(_REASON_UNKNOWN_INLINE)
    return _escape_markdown(_extract_plain_text(node, reasons))


def _convert_inlines(children: Sequence[object], reasons: _ReasonCollector) -> str:
    return "".join(_convert_inline(child, reasons) for child in children)


def _convert_image(node: Mapping[str, object], reasons: _ReasonCollector) -> str | None:
    image = node.get("image")
    url: str | None = None
    alt = ""
    if isinstance(image, Mapping):
        url = _as_str(image.get("url"))
        alt = _first_nonempty_str(
            image.get("alternativeText"),
            image.get("caption"),
            image.get("name"),
        )
    if not url:
        url = _as_str(node.get("url"))
    if not url:
        reasons.add(_REASON_IMAGE_NO_URL)
        return None
    return f"![{_escape_markdown(alt)}]({url})"


def _convert_list(node: Mapping[str, object], reasons: _ReasonCollector, indent: int) -> str:
    fmt = node.get("format")
    ordered = fmt == "ordered"
    lines: list[str] = []
    index = 1
    for child in _iter_children(node):
        if not isinstance(child, Mapping):
            reasons.add(_REASON_MALFORMED)
            continue
        ctype = child.get("type")
        if ctype == "list-item":
            marker = f"{index}. " if ordered else "- "
            index += 1
            body = _convert_inlines(_iter_children(child), reasons)
            lines.append(f"{' ' * indent}{marker}{body}")
        elif ctype == "list":
            nested = _convert_list(child, reasons, indent + 2)
            if nested:
                lines.append(nested)
        else:
            reasons.add(_REASON_UNKNOWN_INLINE)
            plain = _escape_markdown(_extract_plain_text(child, reasons))
            if plain:
                marker = f"{index}. " if ordered else "- "
                index += 1
                lines.append(f"{' ' * indent}{marker}{plain}")
    return "\n".join(lines)


def _convert_block(node: object, reasons: _ReasonCollector) -> str | None:
    if not isinstance(node, Mapping):
        reasons.add(_REASON_MALFORMED)
        return None

    ntype = node.get("type")
    if ntype == "paragraph":
        return _convert_inlines(_iter_children(node), reasons)
    if ntype == "heading":
        level = _heading_level(node.get("level"))
        if level is None or not 1 <= level <= 6:
            if node.get("level") is not None:
                reasons.add(_REASON_HEADING_LEVEL)
            if level is None:
                level = 1
            else:
                level = min(max(level, 1), 6)
        body = _convert_inlines(_iter_children(node), reasons)
        return f"{'#' * level} {body}".rstrip()
    if ntype == "list":
        return _convert_list(node, reasons, indent=0)
    if ntype == "list-item":
        return f"- {_convert_inlines(_iter_children(node), reasons)}"
    if ntype == "quote":
        body = _convert_inlines(_iter_children(node), reasons)
        if not body:
            return ">"
        return "\n".join(f"> {line}" if line else ">" for line in body.split("\n"))
    if ntype == "code":
        text = _extract_code_text(node, reasons)
        fence = _fence_for(text)
        return f"{fence}\n{text}\n{fence}"
    if ntype == "image":
        return _convert_image(node, reasons)
    if ntype in {"link", "text"}:
        return _convert_inline(node, reasons)

    if ntype is None or not isinstance(ntype, str):
        reasons.add(_REASON_MALFORMED)
    else:
        reasons.add(_REASON_UNKNOWN_BLOCK)
    plain = _escape_markdown(_extract_plain_text(node, reasons))
    return plain if plain else None


def _starts_block(line: str) -> bool:
    return bool(
        _HEADING_RE.match(line)
        or _UL_RE.match(line)
        or _OL_RE.match(line)
        or _FENCE_RE.match(line)
        or _QUOTE_RE.match(line)
    )


def _consume_fence(
    lines: list[str], start: int, opening: re.Match[str]
) -> tuple[dict[str, Any], int]:
    marker = opening.group(1)
    fence_char = marker[0]
    min_len = len(marker)
    index = start + 1
    body: list[str] = []
    while index < len(lines):
        candidate = lines[index]
        closing = _FENCE_RE.match(candidate)
        if (
            closing
            and closing.group(1)[0] == fence_char
            and len(closing.group(1)) >= min_len
            and not closing.group(2).strip()
        ):
            index += 1
            break
        body.append(candidate)
        index += 1
    return {"type": "code", "children": [_text_node("\n".join(body))]}, index


def _consume_list(lines: list[str], start: int, *, ordered: bool) -> tuple[dict[str, Any], int]:
    pattern = _OL_RE if ordered else _UL_RE
    items: list[dict[str, Any]] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            break
        match = pattern.match(line)
        if not match:
            break
        items.append(_list_item_block(match.group(1)))
        index += 1
    return {
        "type": "list",
        "format": "ordered" if ordered else "unordered",
        "children": items,
    }, index


def _consume_quote(lines: list[str], start: int) -> tuple[dict[str, Any], int]:
    parts: list[str] = []
    index = start
    while index < len(lines):
        match = _QUOTE_RE.match(lines[index])
        if not match:
            break
        parts.append(match.group(1))
        index += 1
    return {"type": "quote", "children": [_text_node("\n".join(parts))]}, index


def _consume_paragraph(lines: list[str], start: int) -> tuple[dict[str, Any], int]:
    parts: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if not line.strip() or _starts_block(line):
            break
        parts.append(line.strip())
        index += 1
    return _paragraph_block(" ".join(parts)), index
