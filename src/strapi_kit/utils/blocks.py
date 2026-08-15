"""Strapi v5 Blocks rich text (JSON) ↔ Markdown converters.

Strapi 5 stores the Blocks editor as a JSON tree (the
``@strapi/blocks-react-renderer`` schema), not a markdown string.
Classic ``richtext`` fields remain markdown/strings and are not handled here.

``blocks_to_markdown`` walks official nodes and is never silently lossy:
every unsupported construct is recorded in ``MarkdownConversion.lossy_reasons``.

``markdown_to_blocks`` is a documented CommonMark subset write path. It
recognizes block-level Markdown plus inline marks, links, images, and
nested lists. It is not a full CommonMark parser (no setext headings,
HTML blocks, reference links, or thematic breaks).
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
_REASON_MAX_DEPTH: Final[str] = "maximum node depth exceeded"
# Generous for real documents (nested lists); stops recursion bombs / cycles.
_MAX_DEPTH: Final[int] = 32

_HEADING_RE: Final[re.Pattern[str]] = re.compile(r"^(#{1,6})[ \t]+(.*)$")
_UL_RE: Final[re.Pattern[str]] = re.compile(r"^[*+-][ \t]+(.*)$")
_OL_RE: Final[re.Pattern[str]] = re.compile(r"^\d+\.[ \t]+(.*)$")
_FENCE_RE: Final[re.Pattern[str]] = re.compile(r"^(`{3,}|~{3,})(.*)$")
_QUOTE_RE: Final[re.Pattern[str]] = re.compile(r"^>[ \t]?(.*)$")
_IMAGE_RE: Final[re.Pattern[str]] = re.compile(r"!\[([^\]]*)\]\((<[^>\n]+>|[^)\s]+)\)")
_LINK_RE: Final[re.Pattern[str]] = re.compile(r"\[([^\]]+)\]\((<[^>\n]+>|[^)\s]+)\)")
_ORDERED_PREFIX_RE: Final[re.Pattern[str]] = re.compile(r"^(\d+)\.")

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
    - trees deeper than 32 nodes — remaining subtree skipped

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
    code, ordered/unordered lists (including indented nested lists), and
    blockquotes.

    Inline Markdown is converted to official nodes/marks: ``**bold**``,
    ``_italic_`` / ``*italic*``, ``~~strike~~``, inline ``code``,
    ``[text](url)`` links, and ``![alt](url)`` images (no upload).

    This is **not** a full CommonMark parser. Setext headings, HTML blocks,
    reference links, and thematic breaks are not recognized.

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
            blocks.extend(_heading_blocks(len(heading.group(1)), heading.group(2).rstrip()))
            index += 1
            continue

        list_line = _match_list_line(line)
        if list_line is not None:
            list_blocks, index = _consume_list(lines, index, ordered=list_line[2])
            blocks.extend(list_blocks)
            continue

        if _QUOTE_RE.match(line):
            quote_blocks, index = _consume_quote(lines, index)
            blocks.extend(quote_blocks)
            continue

        paragraph_blocks, index = _consume_paragraph(lines, index)
        blocks.extend(paragraph_blocks)

    return blocks if blocks else [_empty_paragraph()]


def _empty_paragraph() -> dict[str, Any]:
    return {
        "type": "paragraph",
        "children": [{"type": "text", "text": ""}],
    }


def _text_node(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def _split_around_images(children: Sequence[object]) -> list[tuple[str, Any]]:
    """Split inline children into ``("inlines", ... )`` / ``("image", node)``."""
    segments: list[tuple[str, Any]] = []
    buf: list[object] = []
    for child in children:
        if isinstance(child, Mapping) and child.get("type") == "image":
            if buf:
                segments.append(("inlines", buf))
                buf = []
            segments.append(("image", child))
        else:
            buf.append(child)
    if buf:
        segments.append(("inlines", buf))
    return segments


def _blocks_from_inlines(
    block_type: str, children: Sequence[object], extra: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Emit parent blocks around official root ``image`` siblings."""
    extra = extra or {}
    segments = _split_around_images(children)
    if not segments:
        node: dict[str, Any] = {"type": block_type, "children": [_text_node("")], **extra}
        return [node]
    result: list[dict[str, Any]] = []
    for kind, payload in segments:
        if kind == "image":
            result.append(dict(payload))
            continue
        node = {"type": block_type, "children": list(payload), **extra}
        result.append(node)
    return result


def _heading_blocks(level: int, text: str) -> list[dict[str, Any]]:
    return _blocks_from_inlines("heading", _parse_inlines(text), {"level": level})


def _paragraph_blocks(text: str) -> list[dict[str, Any]]:
    return _blocks_from_inlines("paragraph", _parse_inlines(text))


def _list_item_block(text: str) -> dict[str, Any]:
    return {"type": "list-item", "children": _parse_inlines(text)}


def _unwrap_destination(raw: str) -> str:
    if raw.startswith("<") and raw.endswith(">") and len(raw) >= 2:
        return raw[1:-1]
    return raw


def _parse_inlines(text: str) -> list[dict[str, Any]]:
    """Parse inline marks, links, and images from a Markdown fragment."""
    if text == "":
        return [_text_node("")]
    nodes: list[dict[str, Any]] = []
    index = 0
    length = len(text)
    while index < length:
        image = _IMAGE_RE.match(text, index)
        if image:
            nodes.append(
                {
                    "type": "image",
                    "image": {
                        "url": _unwrap_destination(image.group(2)),
                        "alternativeText": image.group(1),
                    },
                    "children": [_text_node("")],
                }
            )
            index = image.end()
            continue
        link = _LINK_RE.match(text, index)
        if link:
            nodes.append(
                {
                    "type": "link",
                    "url": _unwrap_destination(link.group(2)),
                    "children": _parse_styled_text(link.group(1)),
                }
            )
            index = link.end()
            continue
        next_special = _next_inline_special(text, index)
        chunk_end = next_special if next_special is not None else length
        if chunk_end > index:
            nodes.extend(_parse_styled_text(text[index:chunk_end]))
        if next_special is None:
            break
        index = chunk_end
    return nodes or [_text_node("")]


def _next_inline_special(text: str, start: int) -> int | None:
    image = _IMAGE_RE.search(text, start)
    link = _LINK_RE.search(text, start)
    candidates = [match.start() for match in (image, link) if match is not None]
    return min(candidates) if candidates else None


def _parse_styled_text(text: str) -> list[dict[str, Any]]:
    """Parse bold / italic / strike / code marks; leftover text stays literal."""
    if text == "":
        return [_text_node("")]
    nodes: list[dict[str, Any]] = []
    buffer: list[str] = []
    index = 0
    length = len(text)

    def flush() -> None:
        if buffer:
            nodes.append(_text_node("".join(buffer)))
            buffer.clear()

    while index < length:
        styled = _consume_styled(text, index)
        if styled is not None:
            flush()
            inner_nodes, new_index = styled
            nodes.extend(inner_nodes)
            index = new_index
            continue
        buffer.append(text[index])
        index += 1
    flush()
    return nodes or [_text_node("")]


def _consume_styled(text: str, index: int) -> tuple[list[dict[str, Any]], int] | None:
    if text.startswith("`", index):
        end = text.find("`", index + 1)
        if end != -1:
            node = _text_node(text[index + 1 : end])
            node["code"] = True
            return [node], end + 1
    for delim, mark in (("**", "bold"), ("__", "bold"), ("~~", "strikethrough")):
        parsed = _consume_delimited(text, index, delim, mark)
        if parsed is not None:
            return parsed
    for delim, mark in (("*", "italic"), ("_", "italic")):
        parsed = _consume_delimited(text, index, delim, mark, word_boundary=(delim == "_"))
        if parsed is not None:
            return parsed
    return None


def _consume_delimited(
    text: str,
    index: int,
    delim: str,
    mark: str,
    *,
    word_boundary: bool = False,
) -> tuple[list[dict[str, Any]], int] | None:
    if not text.startswith(delim, index):
        return None
    if word_boundary and index > 0 and text[index - 1].isalnum():
        return None
    end = text.find(delim, index + len(delim))
    if end == -1:
        return None
    inner = text[index + len(delim) : end]
    if inner == "":
        return None
    if word_boundary and end + len(delim) < len(text) and text[end + len(delim)].isalnum():
        return None
    nodes = _parse_styled_text(inner)
    for node in nodes:
        if node.get("type") == "text":
            node[mark] = True
    return nodes, end + len(delim)


def _escape_block_prefixes(text: str) -> str:
    """Escape ATX / list / quote prefixes at the start of generated lines."""
    if not text:
        return text
    return "\n".join(_escape_line_block_prefix(line) for line in text.split("\n"))


def _escape_line_block_prefix(line: str) -> str:
    if not line:
        return line
    if line.startswith("#") or line.startswith(">"):
        return f"\\{line}"
    if line[0] in "-+*" and (len(line) == 1 or line[1].isspace()):
        return f"\\{line}"
    ordered = _ORDERED_PREFIX_RE.match(line)
    if ordered:
        return f"{ordered.group(1)}\\.{line[ordered.end() :]}"
    return line


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


def _link_destination(url: str) -> str:
    """Format a markdown link/image destination.

    Destinations containing ``)`` or spaces are wrapped in ``<>`` so they do
    not terminate the surrounding ``(...)``.
    """
    if ")" in url or " " in url:
        return f"<{url}>"
    return url


def _too_deep(depth: int, reasons: _ReasonCollector) -> bool:
    """Record a reason and return True when ``depth`` is at/over the guard."""
    if depth >= _MAX_DEPTH:
        reasons.add(_REASON_MAX_DEPTH)
        return True
    return False


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


def _extract_plain_text(node: object, reasons: _ReasonCollector, depth: int) -> str:
    if isinstance(node, str):
        return node
    if _too_deep(depth, reasons):
        return ""
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
    return "".join(_extract_plain_text(child, reasons, depth + 1) for child in _iter_children(node))


def _extract_code_text(node: Mapping[str, object], reasons: _ReasonCollector, depth: int) -> str:
    children = _iter_children(node)
    if children:
        parts: list[str] = []
        for child in children:
            if isinstance(child, Mapping):
                raw = child.get("text")
                if isinstance(raw, str):
                    parts.append(raw)
                else:
                    parts.append(_extract_plain_text(child, reasons, depth + 1))
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


def _convert_inline(node: object, reasons: _ReasonCollector, depth: int) -> str:
    if _too_deep(depth, reasons):
        return ""
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
        inner = _convert_inlines(_iter_children(node), reasons, depth + 1)
        url = _as_str(node.get("url"))
        if not url:
            reasons.add(_REASON_LINK_NO_URL)
            return inner
        return f"[{inner}]({_link_destination(url)})"

    if ntype == "list-item":
        return _convert_inlines(_iter_children(node), reasons, depth + 1)

    if isinstance(ntype, str) and ntype in _BLOCK_TYPES:
        converted = _convert_block(node, reasons, depth)
        return converted if converted is not None else ""

    reasons.add(_REASON_UNKNOWN_INLINE)
    return _escape_markdown(_extract_plain_text(node, reasons, depth))


def _convert_inlines(children: Sequence[object], reasons: _ReasonCollector, depth: int) -> str:
    return "".join(_convert_inline(child, reasons, depth) for child in children)


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
    return f"![{_escape_markdown(alt)}]({_link_destination(url)})"


def _convert_list(
    node: Mapping[str, object], reasons: _ReasonCollector, indent: int, depth: int
) -> str:
    if _too_deep(depth, reasons):
        return ""
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
            body = _convert_inlines(_iter_children(child), reasons, depth + 1)
            lines.append(f"{' ' * indent}{marker}{body}")
        elif ctype == "list":
            nested = _convert_list(child, reasons, indent + 2, depth + 1)
            if nested:
                lines.append(nested)
        else:
            reasons.add(_REASON_UNKNOWN_INLINE)
            plain = _escape_markdown(_extract_plain_text(child, reasons, depth + 1))
            if plain:
                marker = f"{index}. " if ordered else "- "
                index += 1
                lines.append(f"{' ' * indent}{marker}{plain}")
    return "\n".join(lines)


def _convert_block(node: object, reasons: _ReasonCollector, depth: int = 0) -> str | None:
    if _too_deep(depth, reasons):
        return None
    if not isinstance(node, Mapping):
        reasons.add(_REASON_MALFORMED)
        return None

    ntype = node.get("type")
    if ntype == "paragraph":
        return _escape_block_prefixes(_convert_inlines(_iter_children(node), reasons, depth + 1))
    if ntype == "heading":
        level = _heading_level(node.get("level"))
        if level is None or not 1 <= level <= 6:
            if node.get("level") is not None:
                reasons.add(_REASON_HEADING_LEVEL)
            if level is None:
                level = 1
            else:
                level = min(max(level, 1), 6)
        body = _convert_inlines(_iter_children(node), reasons, depth + 1)
        return f"{'#' * level} {body}".rstrip()
    if ntype == "list":
        return _convert_list(node, reasons, indent=0, depth=depth)
    if ntype == "list-item":
        return f"- {_convert_inlines(_iter_children(node), reasons, depth + 1)}"
    if ntype == "quote":
        body = _convert_inlines(_iter_children(node), reasons, depth + 1)
        if not body:
            return ">"
        return "\n".join(f"> {line}" if line else ">" for line in body.split("\n"))
    if ntype == "code":
        text = _extract_code_text(node, reasons, depth)
        fence = _fence_for(text)
        return f"{fence}\n{text}\n{fence}"
    if ntype == "image":
        return _convert_image(node, reasons)
    if ntype in {"link", "text"}:
        return _convert_inline(node, reasons, depth)

    if ntype is None or not isinstance(ntype, str):
        reasons.add(_REASON_MALFORMED)
    else:
        reasons.add(_REASON_UNKNOWN_BLOCK)
    plain = _escape_markdown(_extract_plain_text(node, reasons, depth))
    return plain if plain else None


def _starts_block(line: str) -> bool:
    return bool(
        _HEADING_RE.match(line)
        or _match_list_line(line) is not None
        or _FENCE_RE.match(line)
        or _QUOTE_RE.match(line)
    )


def _match_list_line(line: str) -> tuple[int, str, bool] | None:
    """Return ``(indent, item_text, ordered)`` when ``line`` is a list item."""
    if not line.strip():
        return None
    indent = len(line) - len(line.lstrip(" "))
    rest = line[indent:]
    unordered = _UL_RE.match(rest)
    if unordered:
        return indent, unordered.group(1), False
    ordered = _OL_RE.match(rest)
    if ordered:
        return indent, ordered.group(1), True
    return None


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


def _consume_list(
    lines: list[str], start: int, *, ordered: bool
) -> tuple[list[dict[str, Any]], int]:
    entries: list[tuple[int, str, bool]] = []
    index = start
    while index < len(lines):
        parsed = _match_list_line(lines[index])
        if parsed is None:
            break
        indent, text, is_ordered = parsed
        if entries and indent == entries[0][0] and is_ordered != entries[0][2]:
            break
        if not entries and is_ordered != ordered:
            break
        entries.append((indent, text, is_ordered))
        index += 1
    return _lift_images_from_list(_build_list_tree(entries, ordered)), index


def _build_list_tree(entries: list[tuple[int, str, bool]], ordered: bool) -> dict[str, Any]:
    """Nest indented list items under the previous item as child lists."""
    root: dict[str, Any] = {
        "type": "list",
        "format": "ordered" if ordered else "unordered",
        "children": [],
    }
    if not entries:
        return root

    stack: list[tuple[int, dict[str, Any]]] = [(entries[0][0], root)]
    for indent, text, is_ordered in entries:
        item: dict[str, Any] = _list_item_block(text)
        while len(stack) > 1 and indent < stack[-1][0]:
            stack.pop()
        current_indent, current_list = stack[-1]
        if indent > current_indent:
            nested: dict[str, Any] = {
                "type": "list",
                "format": "ordered" if is_ordered else "unordered",
                "children": [item],
            }
            if current_list["children"]:
                previous = current_list["children"][-1]
                previous["children"].append(nested)
            else:
                current_list["children"].append(item)
                continue
            stack.append((indent, nested))
        else:
            current_list["children"].append(item)
    return root


def _lift_images_from_list(list_node: dict[str, Any]) -> list[dict[str, Any]]:
    """Hoist official image nodes out of list items to root siblings."""
    result: list[dict[str, Any]] = []
    current_items: list[dict[str, Any]] = []
    fmt = list_node.get("format", "unordered")

    def flush() -> None:
        if current_items:
            result.append({"type": "list", "format": fmt, "children": current_items[:]})
            current_items.clear()

    for item in list_node.get("children", []):
        if not isinstance(item, Mapping) or item.get("type") != "list-item":
            if isinstance(item, dict):
                current_items.append(item)
            continue
        inline_children: list[object] = []
        nested_lists: list[dict[str, Any]] = []
        for child in item.get("children", ()):
            if isinstance(child, Mapping) and child.get("type") == "list":
                nested_lists.extend(_lift_images_from_list(dict(child)))
            else:
                inline_children.append(child)

        segments = _split_around_images(inline_children)
        if not segments:
            current_items.append({"type": "list-item", "children": [_text_node("")]})
        for kind, payload in segments:
            if kind == "image":
                flush()
                result.append(dict(payload))
            else:
                current_items.append({"type": "list-item", "children": list(payload)})

        for nested in nested_lists:
            if nested.get("type") == "image":
                flush()
                result.append(nested)
            elif current_items:
                current_items[-1]["children"].append(nested)
            else:
                result.append(nested)

    flush()
    return result


def _consume_quote(lines: list[str], start: int) -> tuple[list[dict[str, Any]], int]:
    parts: list[str] = []
    index = start
    while index < len(lines):
        match = _QUOTE_RE.match(lines[index])
        if not match:
            break
        parts.append(match.group(1))
        index += 1
    return _blocks_from_inlines("quote", _parse_inlines("\n".join(parts))), index


def _consume_paragraph(lines: list[str], start: int) -> tuple[list[dict[str, Any]], int]:
    parts: list[str] = []
    index = start
    while index < len(lines):
        line = lines[index]
        if not line.strip() or _starts_block(line):
            break
        parts.append(line.strip())
        index += 1
    return _paragraph_blocks(" ".join(parts)), index
