"""Tests for Strapi v5 Blocks ↔ Markdown converters."""

from typing import Any

import pytest

from strapi_kit import FieldType, MarkdownConversion, blocks_to_markdown, markdown_to_blocks
from strapi_kit.models.schema import FieldSchema

EMPTY_PARAGRAPH: list[dict[str, Any]] = [
    {"type": "paragraph", "children": [{"type": "text", "text": ""}]}
]


def _text(
    text: str,
    *,
    bold: bool = False,
    italic: bool = False,
    underline: bool = False,
    strikethrough: bool = False,
    code: bool = False,
) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "text", "text": text}
    if bold:
        node["bold"] = True
    if italic:
        node["italic"] = True
    if underline:
        node["underline"] = True
    if strikethrough:
        node["strikethrough"] = True
    if code:
        node["code"] = True
    return node


def _paragraph(*children: dict[str, Any]) -> dict[str, Any]:
    return {"type": "paragraph", "children": list(children)}


def _heading(level: int, *children: dict[str, Any]) -> dict[str, Any]:
    return {"type": "heading", "level": level, "children": list(children)}


class TestPublicExports:
    """Converters and FieldType are part of the public API."""

    def test_package_exports(self) -> None:
        assert FieldType.BLOCKS == "blocks"
        assert callable(blocks_to_markdown)
        assert callable(markdown_to_blocks)
        assert MarkdownConversion(markdown="", lossy_reasons=()).lossy_reasons == ()

    def test_utils_reexports(self) -> None:
        from strapi_kit.utils import (
            MarkdownConversion as UtilsConversion,
        )
        from strapi_kit.utils import (
            blocks_to_markdown as utils_blocks_to_markdown,
        )
        from strapi_kit.utils import (
            markdown_to_blocks as utils_markdown_to_blocks,
        )

        assert utils_blocks_to_markdown is blocks_to_markdown
        assert utils_markdown_to_blocks is markdown_to_blocks
        assert UtilsConversion is MarkdownConversion


class TestFieldTypeBlocks:
    """FieldType.BLOCKS must round-trip a CTB attribute fixture."""

    CTB_ATTRIBUTE: dict[str, Any] = {"type": "blocks", "required": True}

    def test_enum_value(self) -> None:
        assert FieldType.BLOCKS == "blocks"
        assert FieldType("blocks") is FieldType.BLOCKS

    def test_ctb_attribute_round_trip(self) -> None:
        field = FieldSchema.model_validate(self.CTB_ATTRIBUTE)
        assert field.type is FieldType.BLOCKS
        assert field.required is True

        dumped = field.model_dump(mode="json")
        assert dumped["type"] == "blocks"
        again = FieldSchema.model_validate(dumped)
        assert again.type is FieldType.BLOCKS
        assert again.type.value == "blocks"


class TestBlocksToMarkdownSupported:
    """Every official block and inline type."""

    def test_paragraph(self) -> None:
        result = blocks_to_markdown([_paragraph(_text("A simple paragraph"))])
        assert result.markdown == "A simple paragraph"
        assert result.lossy_reasons == ()

    @pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
    def test_heading_levels(self, level: int) -> None:
        result = blocks_to_markdown([_heading(level, _text(f"Heading {level}"))])
        assert result.markdown == f"{'#' * level} Heading {level}"
        assert result.lossy_reasons == ()

    def test_unordered_list(self) -> None:
        blocks = [
            {
                "type": "list",
                "format": "unordered",
                "children": [
                    {"type": "list-item", "children": [_text("bulleted")]},
                    {"type": "list-item", "children": [_text("list")]},
                ],
            }
        ]
        result = blocks_to_markdown(blocks)
        assert result.markdown == "- bulleted\n- list"
        assert result.lossy_reasons == ()

    def test_ordered_list(self) -> None:
        blocks = [
            {
                "type": "list",
                "format": "ordered",
                "children": [
                    {"type": "list-item", "children": [_text("numbered")]},
                    {"type": "list-item", "children": [_text("list")]},
                ],
            }
        ]
        result = blocks_to_markdown(blocks)
        assert result.markdown == "1. numbered\n2. list"
        assert result.lossy_reasons == ()

    def test_nested_list(self) -> None:
        blocks = [
            {
                "type": "list",
                "format": "unordered",
                "children": [
                    {"type": "list-item", "children": [_text("outer")]},
                    {
                        "type": "list",
                        "format": "unordered",
                        "children": [
                            {"type": "list-item", "children": [_text("inner")]},
                        ],
                    },
                ],
            }
        ]
        result = blocks_to_markdown(blocks)
        assert result.markdown == "- outer\n  - inner"
        assert result.lossy_reasons == ()

    def test_quote(self) -> None:
        result = blocks_to_markdown([{"type": "quote", "children": [_text("Quote content")]}])
        assert result.markdown == "> Quote content"
        assert result.lossy_reasons == ()

    def test_code_block(self) -> None:
        result = blocks_to_markdown([{"type": "code", "children": [_text('print("hi")')]}])
        assert result.markdown == '```\nprint("hi")\n```'
        assert result.lossy_reasons == ()

    def test_code_block_longer_fence_when_content_has_backticks(self) -> None:
        result = blocks_to_markdown([{"type": "code", "children": [_text("```inside")]}])
        assert result.markdown.startswith("````\n")
        assert result.markdown.endswith("\n````")

    def test_image(self) -> None:
        blocks = [
            {
                "type": "image",
                "image": {
                    "url": "https://example.com/mascot.png",
                    "alternativeText": "mascot",
                    "name": "mascot.png",
                },
                "children": [_text("")],
            }
        ]
        result = blocks_to_markdown(blocks)
        assert result.markdown == "![mascot](https://example.com/mascot.png)"
        assert result.lossy_reasons == ()

    def test_link(self) -> None:
        blocks = [
            _paragraph(
                _text("See "),
                {
                    "type": "link",
                    "url": "https://example.com",
                    "children": [_text("docs")],
                },
                _text("."),
            )
        ]
        result = blocks_to_markdown(blocks)
        assert result.markdown == "See [docs](https://example.com)."
        assert result.lossy_reasons == ()

    def test_link_url_with_paren_is_wrapped(self) -> None:
        blocks = [
            _paragraph(
                {
                    "type": "link",
                    "url": "https://example.com/a(b)",
                    "children": [_text("docs")],
                }
            )
        ]
        result = blocks_to_markdown(blocks)
        assert result.markdown == "[docs](<https://example.com/a(b)>)"
        assert result.lossy_reasons == ()

    def test_image_url_with_paren_is_wrapped(self) -> None:
        blocks = [
            {
                "type": "image",
                "image": {
                    "url": "https://example.com/a(b).png",
                    "alternativeText": "mascot",
                },
                "children": [_text("")],
            }
        ]
        result = blocks_to_markdown(blocks)
        assert result.markdown == "![mascot](<https://example.com/a(b).png>)"
        assert result.lossy_reasons == ()

    def test_bold(self) -> None:
        result = blocks_to_markdown([_paragraph(_text("this is the bold", bold=True))])
        assert result.markdown == "**this is the bold**"
        assert result.lossy_reasons == ()

    def test_italic(self) -> None:
        result = blocks_to_markdown([_paragraph(_text("italic paragraph", italic=True))])
        assert result.markdown == "_italic paragraph_"
        assert result.lossy_reasons == ()

    def test_strikethrough(self) -> None:
        result = blocks_to_markdown([_paragraph(_text("struck", strikethrough=True))])
        assert result.markdown == "~~struck~~"
        assert result.lossy_reasons == ()

    def test_inline_code(self) -> None:
        result = blocks_to_markdown([_paragraph(_text("some code", code=True))])
        assert result.markdown == "`some code`"
        assert result.lossy_reasons == ()

    def test_combined_marks(self) -> None:
        result = blocks_to_markdown(
            [_paragraph(_text("hi", bold=True, italic=True, strikethrough=True, code=True))]
        )
        assert result.markdown == "**_~~`hi`~~_**"
        assert result.lossy_reasons == ()

    def test_empty_input_is_faithful(self) -> None:
        assert blocks_to_markdown([]).markdown == ""
        assert blocks_to_markdown([]).lossy_reasons == ()
        assert blocks_to_markdown(None).lossy_reasons == ()

    def test_kitchen_sink_supported_nodes(self) -> None:
        blocks: list[dict[str, Any]] = [
            _heading(1, _text("Heading 1")),
            _heading(2, _text("Heading 2")),
            _heading(3, _text("Heading 3")),
            _paragraph(_text("basic paragraph")),
            _paragraph(_text("this is the bold", bold=True)),
            _paragraph(_text("this is an italic paragraph", italic=True)),
            _paragraph(_text("this has strikethrough", strikethrough=True)),
            _paragraph(_text("some code", code=True)),
            _paragraph(
                _text(""),
                {"type": "link", "url": "https://google.com", "children": [_text("a link")]},
                _text(""),
            ),
            {
                "type": "list",
                "format": "unordered",
                "children": [
                    {"type": "list-item", "children": [_text("bulleted")]},
                    {"type": "list-item", "children": [_text("list")]},
                ],
            },
            {
                "type": "list",
                "format": "ordered",
                "children": [
                    {"type": "list-item", "children": [_text("numbered")]},
                    {"type": "list-item", "children": [_text("list")]},
                ],
            },
            {"type": "quote", "children": [_text("Quote content here")]},
            {
                "type": "image",
                "image": {
                    "url": "http://localhost:1337/uploads/mascot.png",
                    "alternativeText": "alt text",
                },
                "children": [_text("")],
            },
            {"type": "code", "children": [_text("const x = 1;")]},
        ]
        result = blocks_to_markdown(blocks)
        assert result.lossy_reasons == ()
        assert "# Heading 1" in result.markdown
        assert "## Heading 2" in result.markdown
        assert "### Heading 3" in result.markdown
        assert "basic paragraph" in result.markdown
        assert "**this is the bold**" in result.markdown
        assert "_this is an italic paragraph_" in result.markdown
        assert "~~this has strikethrough~~" in result.markdown
        assert "`some code`" in result.markdown
        assert "[a link](https://google.com)" in result.markdown
        assert "- bulleted" in result.markdown
        assert "1. numbered" in result.markdown
        assert "> Quote content here" in result.markdown
        assert "![alt text](http://localhost:1337/uploads/mascot.png)" in result.markdown
        assert "```\nconst x = 1;\n```" in result.markdown


class TestBlocksToMarkdownLossy:
    """Every lossy case is recorded; reasons are never silent."""

    def test_underline_keeps_text(self) -> None:
        result = blocks_to_markdown([_paragraph(_text("this is underlined", underline=True))])
        assert result.markdown == "this is underlined"
        assert result.lossy_reasons == ("underline mark has no markdown equivalent",)

    def test_image_without_url_is_dropped(self) -> None:
        blocks = [
            {
                "type": "image",
                "image": {"alternativeText": "missing"},
                "children": [_text("")],
            }
        ]
        result = blocks_to_markdown(blocks)
        assert result.markdown == ""
        assert result.lossy_reasons == ("image dropped because it has no URL",)

    def test_link_without_url_keeps_text(self) -> None:
        blocks = [
            _paragraph(
                {
                    "type": "link",
                    "children": [_text("orphaned")],
                }
            )
        ]
        result = blocks_to_markdown(blocks)
        assert result.markdown == "orphaned"
        assert result.lossy_reasons == ("link has no URL; kept link text",)

    def test_link_with_empty_url_keeps_text(self) -> None:
        blocks = [_paragraph({"type": "link", "url": "", "children": [_text("x")]})]
        result = blocks_to_markdown(blocks)
        assert result.markdown == "x"
        assert "link has no URL" in result.lossy_reasons[0]

    def test_unknown_block_flattened_to_text(self) -> None:
        blocks = [{"type": "callout", "children": [_text("hey")]}]
        result = blocks_to_markdown(blocks)
        assert result.markdown == "hey"
        assert result.lossy_reasons == ("unknown block type flattened to text",)

    def test_unknown_inline_flattened_to_text(self) -> None:
        blocks = [_paragraph({"type": "mention", "text": "@you"})]
        result = blocks_to_markdown(blocks)
        assert result.markdown == "@you"
        assert result.lossy_reasons == ("unknown inline type flattened to text",)

    def test_malformed_non_object_nodes_skipped(self) -> None:
        blocks: list[object] = [
            "not-an-object",
            42,
            None,
            _paragraph(_text("ok")),
        ]
        result = blocks_to_markdown(blocks)
        assert result.markdown == "ok"
        assert result.lossy_reasons == ("malformed non-object node skipped",)

    def test_reason_dedup(self) -> None:
        blocks = [
            _paragraph(_text("a", underline=True), _text("b", underline=True)),
            _paragraph(_text("c", underline=True)),
        ]
        result = blocks_to_markdown(blocks)
        assert result.markdown == "ab\n\nc"
        assert result.lossy_reasons == ("underline mark has no markdown equivalent",)

    def test_malformed_reason_dedup(self) -> None:
        result = blocks_to_markdown([1, 2, 3])
        assert result.markdown == ""
        assert result.lossy_reasons == ("malformed non-object node skipped",)

    def test_empty_reasons_iff_faithful(self) -> None:
        faithful = blocks_to_markdown([_paragraph(_text("plain"))])
        lossy = blocks_to_markdown([_paragraph(_text("u", underline=True))])
        assert faithful.lossy_reasons == ()
        assert lossy.lossy_reasons != ()

    def test_string_input_is_malformed_not_char_walk(self) -> None:
        result = blocks_to_markdown("**not blocks**")  # type: ignore[arg-type]
        assert result.markdown == ""
        assert result.lossy_reasons == ("malformed non-object node skipped",)

    def test_invalid_heading_level_is_clamped(self) -> None:
        result = blocks_to_markdown([_heading(0, _text("Zero")), _heading(9, _text("Nine"))])
        assert "# Zero" in result.markdown
        assert "###### Nine" in result.markdown
        assert result.lossy_reasons == ("heading level is outside 1-6",)

    def test_unknown_mark_is_recorded(self) -> None:
        node = _text("glow")
        node["highlight"] = True
        result = blocks_to_markdown([_paragraph(node)])
        assert result.markdown == "glow"
        assert result.lossy_reasons == ("unknown mark dropped",)

    def test_cyclic_children_do_not_raise(self) -> None:
        para: dict[str, Any] = _paragraph(_text("x"))
        para["children"].append(para)
        result = blocks_to_markdown([para])
        assert "maximum node depth exceeded" in result.lossy_reasons

    def test_deeply_nested_lists_do_not_raise(self) -> None:
        node: dict[str, Any] = {
            "type": "list",
            "format": "unordered",
            "children": [{"type": "list-item", "children": [_text("leaf")]}],
        }
        for _ in range(64):
            node = {"type": "list", "format": "unordered", "children": [node]}
        result = blocks_to_markdown([node])
        assert "maximum node depth exceeded" in result.lossy_reasons

    def test_unknown_block_cycle_does_not_raise(self) -> None:
        node: dict[str, Any] = {"type": "callout", "children": []}
        node["children"].append(node)
        result = blocks_to_markdown([node])
        assert "maximum node depth exceeded" in result.lossy_reasons
        assert "unknown block type flattened to text" in result.lossy_reasons

    def test_reasonable_nesting_is_faithful(self) -> None:
        node: dict[str, Any] = {
            "type": "list",
            "format": "unordered",
            "children": [{"type": "list-item", "children": [_text("leaf")]}],
        }
        for _ in range(8):
            node = {"type": "list", "format": "unordered", "children": [node]}
        result = blocks_to_markdown([node])
        assert result.lossy_reasons == ()
        assert "leaf" in result.markdown


class TestMetacharacterEscape:
    """Leaf text is escaped before marks so source cannot invent formatting."""

    def test_literal_asterisks_do_not_become_emphasis(self) -> None:
        result = blocks_to_markdown([_paragraph(_text("**literal**"))])
        assert result.markdown == r"\*\*literal\*\*"
        assert result.lossy_reasons == ()

    def test_escaped_before_bold_mark(self) -> None:
        result = blocks_to_markdown([_paragraph(_text("**literal**", bold=True))])
        assert result.markdown == r"**\*\*literal\*\***"
        assert result.lossy_reasons == ()

    def test_underscores_and_backticks(self) -> None:
        result = blocks_to_markdown([_paragraph(_text("foo_bar `code`"))])
        assert result.markdown == r"foo\_bar \`code\`"
        assert result.lossy_reasons == ()

    def test_brackets_cannot_invent_links(self) -> None:
        result = blocks_to_markdown([_paragraph(_text("[docs](https://example.com)"))])
        assert result.markdown == r"\[docs\](https://example.com)"
        assert result.lossy_reasons == ()

    def test_paragraph_hash_is_not_a_heading(self) -> None:
        result = blocks_to_markdown([_paragraph(_text("# not a heading"))])
        assert result.markdown == r"\# not a heading"
        assert result.lossy_reasons == ()

    def test_paragraph_list_and_quote_prefixes_are_escaped(self) -> None:
        dash = blocks_to_markdown([_paragraph(_text("- item"))])
        quote = blocks_to_markdown([_paragraph(_text("> quote"))])
        numbered = blocks_to_markdown([_paragraph(_text("1. item"))])
        assert dash.markdown == r"\- item"
        assert quote.markdown == r"\> quote"
        assert numbered.markdown == r"1\. item"
        assert dash.lossy_reasons == ()
        assert quote.lossy_reasons == ()
        assert numbered.lossy_reasons == ()

    def test_hyphen_in_running_prose_is_not_escaped(self) -> None:
        result = blocks_to_markdown([_paragraph(_text("foo-bar and - dash"))])
        assert result.markdown == "foo-bar and - dash"
        assert result.lossy_reasons == ()


class TestMarkdownToBlocks:
    """Best-effort write path for heading/list/code/quote/paragraph."""

    def test_heading(self) -> None:
        assert markdown_to_blocks("# Title") == [
            {"type": "heading", "level": 1, "children": [_text("Title")]}
        ]

    def test_heading_levels(self) -> None:
        src = "# H1\n## H2\n### H3\n#### H4\n##### H5\n###### H6"
        blocks = markdown_to_blocks(src)
        assert [block["level"] for block in blocks] == [1, 2, 3, 4, 5, 6]
        assert all(block["type"] == "heading" for block in blocks)

    def test_unordered_list(self) -> None:
        assert markdown_to_blocks("- one\n- two") == [
            {
                "type": "list",
                "format": "unordered",
                "children": [
                    {"type": "list-item", "children": [_text("one")]},
                    {"type": "list-item", "children": [_text("two")]},
                ],
            }
        ]

    def test_ordered_list(self) -> None:
        assert markdown_to_blocks("1. one\n2. two") == [
            {
                "type": "list",
                "format": "ordered",
                "children": [
                    {"type": "list-item", "children": [_text("one")]},
                    {"type": "list-item", "children": [_text("two")]},
                ],
            }
        ]

    def test_fenced_code(self) -> None:
        assert markdown_to_blocks("```\nprint('hi')\n```") == [
            {"type": "code", "children": [_text("print('hi')")]}
        ]

    def test_fenced_code_ignores_language(self) -> None:
        assert markdown_to_blocks("```python\nx = 1\n```") == [
            {"type": "code", "children": [_text("x = 1")]}
        ]

    def test_quote(self) -> None:
        assert markdown_to_blocks("> quoted") == [{"type": "quote", "children": [_text("quoted")]}]

    def test_multiline_quote(self) -> None:
        assert markdown_to_blocks("> line 1\n> line 2") == [
            {"type": "quote", "children": [_text("line 1\nline 2")]}
        ]

    def test_paragraph(self) -> None:
        assert markdown_to_blocks("Hello world") == [_paragraph(_text("Hello world"))]

    def test_wrapped_paragraph_lines_join(self) -> None:
        assert markdown_to_blocks("Hello\nworld") == [_paragraph(_text("Hello world"))]

    def test_two_paragraphs(self) -> None:
        assert markdown_to_blocks("first\n\nsecond") == [
            _paragraph(_text("first")),
            _paragraph(_text("second")),
        ]

    def test_inline_marks_become_text_marks(self) -> None:
        blocks = markdown_to_blocks("**bold** _italic_ ~~strike~~ `code`")
        children = blocks[0]["children"]
        assert children[0] == _text("bold", bold=True)
        assert children[2] == _text("italic", italic=True)
        assert children[4] == _text("strike", strikethrough=True)
        assert children[6] == _text("code", code=True)

    def test_link_becomes_link_node(self) -> None:
        blocks = markdown_to_blocks("[docs](https://example.com)")
        assert blocks == [
            _paragraph({"type": "link", "url": "https://example.com", "children": [_text("docs")]})
        ]

    def test_image_becomes_image_node(self) -> None:
        blocks = markdown_to_blocks("![alt](https://example.com/a.png)")
        assert blocks == [
            {
                "type": "image",
                "image": {"url": "https://example.com/a.png", "alternativeText": "alt"},
            }
        ]

    def test_nested_indented_list(self) -> None:
        blocks = markdown_to_blocks("- parent\n  - child")
        assert blocks[0]["type"] == "list"
        parent = blocks[0]["children"][0]
        assert parent["type"] == "list-item"
        nested = parent["children"][1]
        assert nested["type"] == "list"
        assert nested["children"][0]["children"][0]["text"] == "child"

    @pytest.mark.parametrize("src", ["", "   ", "\n", "\n\n", " \n \t "])
    def test_empty_input_pins_empty_paragraph(self, src: str) -> None:
        assert markdown_to_blocks(src) == EMPTY_PARAGRAPH
