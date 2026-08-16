"""Typed Strapi v5 Blocks JSON nodes.

These TypedDicts describe the official ``@strapi/blocks-react-renderer``
tree. ``markdown_to_blocks`` returns this shape so the list can be sent
on a ``blocks`` field without ``.model_dump()``.

``blocks_to_markdown`` still accepts ``Sequence[object]`` because the
read path must record unknown/malformed nodes as lossy instead of
rejecting the tree.
"""

from __future__ import annotations

from typing import Literal, Required, TypedDict


class TextNode(TypedDict, total=False):
    """Text leaf with optional official marks."""

    type: Required[Literal["text"]]
    text: Required[str]
    bold: bool
    italic: bool
    underline: bool
    strikethrough: bool
    code: bool


class LinkNode(TypedDict):
    """Inline link."""

    type: Literal["link"]
    url: str
    children: list[TextNode]


class ImageAsset(TypedDict, total=False):
    """Media payload on an official image block."""

    url: Required[str]
    alternativeText: str
    caption: str
    name: str


class ImageNode(TypedDict):
    """Root image block (not a valid inline child)."""

    type: Literal["image"]
    image: ImageAsset
    children: list[TextNode]


class ParagraphNode(TypedDict):
    """Root paragraph."""

    type: Literal["paragraph"]
    children: list[TextNode | LinkNode]


class HeadingNode(TypedDict):
    """Root heading (levels 1–6)."""

    type: Literal["heading"]
    level: Literal[1, 2, 3, 4, 5, 6]
    children: list[TextNode | LinkNode]


class QuoteNode(TypedDict):
    """Root blockquote."""

    type: Literal["quote"]
    children: list[TextNode | LinkNode]


class CodeNode(TypedDict):
    """Root fenced code block."""

    type: Literal["code"]
    children: list[TextNode]


class ListNode(TypedDict):
    """Root or nested list."""

    type: Literal["list"]
    format: Literal["ordered", "unordered"]
    children: list[ListItemNode]


class ListItemNode(TypedDict):
    """List item; may nest another ``list``."""

    type: Literal["list-item"]
    children: list[TextNode | LinkNode | ListNode]


type InlineNode = TextNode | LinkNode
type BlockNode = ParagraphNode | HeadingNode | ListNode | QuoteNode | CodeNode | ImageNode

__all__ = [
    "BlockNode",
    "CodeNode",
    "HeadingNode",
    "ImageAsset",
    "ImageNode",
    "InlineNode",
    "LinkNode",
    "ListItemNode",
    "ListNode",
    "ParagraphNode",
    "QuoteNode",
    "TextNode",
]
