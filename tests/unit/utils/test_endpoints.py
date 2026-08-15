"""Tests for REST collection path helpers (pluralName only)."""

import pytest

from strapi_kit import collection_endpoint, document_endpoint
from strapi_kit.client.base import BaseClient
from strapi_kit.exceptions import ValidationError
from strapi_kit.models.content_type import ContentTypeInfo, ContentTypeListItem
from strapi_kit.models.content_type import ContentTypeSchema as CTBContentTypeSchema
from strapi_kit.models.schema import ContentTypeSchema
from strapi_kit.utils import (
    collection_endpoint as utils_collection_endpoint,
)
from strapi_kit.utils import (
    document_endpoint as utils_document_endpoint,
)

# UID that naive pluralization would turn into "posts" — must never be used.
_MISLEADING_UID = "api::post.post"
_PLURAL_NAME = "blog-posts"

_LIST_ITEM_DATA = {
    "uid": _MISLEADING_UID,
    "kind": "collectionType",
    "info": {
        "displayName": "Post",
        "singularName": "post",
        "pluralName": _PLURAL_NAME,
    },
}


def _list_item(**info_overrides: object) -> ContentTypeListItem:
    info = {
        "displayName": "Post",
        "singularName": "post",
        "pluralName": _PLURAL_NAME,
        **info_overrides,
    }
    return ContentTypeListItem.model_validate(
        {"uid": _MISLEADING_UID, "kind": "collectionType", "info": info}
    )


class TestCollectionEndpoint:
    """Tests for collection_endpoint."""

    def test_uses_plural_name_not_uid_list_item(self) -> None:
        """pluralName=blog-posts with UID api::post.post uses blog-posts."""
        item = _list_item()
        assert item.uid == _MISLEADING_UID
        assert collection_endpoint(item) == "blog-posts"

    def test_uses_plural_name_not_uid_ctb_schema(self) -> None:
        """ContentTypeSchema (CTB) uses info.pluralName, not the UID."""
        schema = CTBContentTypeSchema.model_validate(_LIST_ITEM_DATA)
        assert schema.uid == _MISLEADING_UID
        assert collection_endpoint(schema) == "blog-posts"

    def test_uses_plural_name_not_uid_cached_schema(self) -> None:
        """Cached ContentTypeSchema uses top-level plural_name, not the UID."""
        schema = ContentTypeSchema(
            uid=_MISLEADING_UID,
            display_name="Post",
            singular_name="post",
            plural_name=_PLURAL_NAME,
        )
        assert collection_endpoint(schema) == "blog-posts"

    def test_uses_plural_name_from_dict_info(self) -> None:
        """Dict with info.pluralName uses that value, not the UID."""
        payload = {
            "uid": _MISLEADING_UID,
            "apiID": "posts",
            "info": {"displayName": "Post", "pluralName": "blog-posts"},
        }
        assert collection_endpoint(payload) == "blog-posts"

    def test_uses_top_level_plural_name_on_dict(self) -> None:
        """Flat v5-style dict uses top-level pluralName."""
        payload = {
            "uid": _MISLEADING_UID,
            "displayName": "Post",
            "pluralName": "blog-posts",
        }
        assert collection_endpoint(payload) == "blog-posts"

    def test_uses_snake_case_plural_name_on_mapping(self) -> None:
        """Dicts accept info.plural_name and top-level plural_name."""
        nested = {"uid": _MISLEADING_UID, "info": {"plural_name": "blog-posts"}}
        flat = {"uid": _MISLEADING_UID, "plural_name": "blog-posts"}
        assert collection_endpoint(nested) == "blog-posts"
        assert collection_endpoint(flat) == "blog-posts"

    def test_uses_model_valued_info_on_mapping(self) -> None:
        """A mapping whose info is a ContentTypeInfo still reads pluralName."""
        info = ContentTypeInfo.model_validate({"displayName": "Post", "pluralName": "blog-posts"})
        payload = {"uid": _MISLEADING_UID, "info": info}
        assert collection_endpoint(payload) == "blog-posts"

    def test_non_string_plural_name_raises(self) -> None:
        """Non-string pluralName raises; UID is not used as a path."""
        with pytest.raises(ValidationError, match="pluralName") as exc_info:
            collection_endpoint({"uid": _MISLEADING_UID, "pluralName": 123})
        assert exc_info.value.details.get("pluralName") == 123
        assert "posts" not in str(exc_info.value)

    def test_missing_plural_name_raises_uid_not_consulted(self) -> None:
        """Missing pluralName raises; UID is not used as a fallback."""
        item = _list_item(pluralName=None)
        assert item.uid == _MISLEADING_UID
        with pytest.raises(ValidationError, match="pluralName") as exc_info:
            collection_endpoint(item)
        assert "posts" not in str(exc_info.value)
        assert exc_info.value.details.get("uid") == _MISLEADING_UID

    def test_blank_plural_name_raises_uid_not_consulted(self) -> None:
        """Blank pluralName raises; UID is not used as a fallback."""
        item = _list_item(pluralName="   ")
        with pytest.raises(ValidationError, match="pluralName") as exc_info:
            collection_endpoint(item)
        assert "posts" not in str(exc_info.value)

    def test_missing_plural_name_on_dict_raises(self) -> None:
        """Dict with only a UID (and apiID) raises without guessing."""
        payload = {"uid": _MISLEADING_UID, "apiID": "posts", "info": {"displayName": "Post"}}
        with pytest.raises(ValidationError, match="pluralName"):
            collection_endpoint(payload)

    def test_empty_string_plural_name_raises(self) -> None:
        """Empty-string pluralName is treated as blank."""
        with pytest.raises(ValidationError, match="pluralName"):
            collection_endpoint({"uid": _MISLEADING_UID, "pluralName": ""})

    def test_uid_string_is_not_a_path(self) -> None:
        """A raw UID string is not a collection path and is not pluralized."""
        with pytest.raises(ValidationError, match="pluralName"):
            collection_endpoint(_MISLEADING_UID)


class TestDocumentEndpoint:
    """Tests for document_endpoint percent-encoding."""

    def test_joins_collection_and_id(self) -> None:
        """Plain document ids are appended without extra encoding."""
        item = _list_item()
        assert document_endpoint(item, "abc123") == "blog-posts/abc123"

    def test_joins_integer_document_id(self) -> None:
        """Numeric v4 ids are stringified and appended."""
        item = _list_item()
        assert document_endpoint(item, 12) == "blog-posts/12"

    def test_encodes_slash_question_space_percent(self) -> None:
        """Reserved characters in the document id are percent-encoded."""
        item = _list_item()
        assert document_endpoint(item, "a/b?c d%") == "blog-posts/a%2Fb%3Fc%20d%25"

    def test_shares_encoder_with_document_path(self) -> None:
        """document_endpoint and BaseClient.document_path use one encoder."""
        item = _list_item()
        assert document_endpoint(item, "a/b?c") == BaseClient.document_path("blog-posts", "a/b?c")

    def test_whitespace_only_collection_raises(self) -> None:
        """Whitespace-only collection is blank, not a path segment."""
        from strapi_kit.utils.endpoints import join_document_path

        for collection in ("", "   ", "///", " / "):
            with pytest.raises(ValidationError, match="collection is required"):
                join_document_path(collection, "abc")
        with pytest.raises(ValidationError, match="document_id is required"):
            join_document_path("articles", "   ")

    def test_encodes_each_reserved_character(self) -> None:
        """Encode /, ?, space, and % individually."""
        item = _list_item()
        assert document_endpoint(item, "a/b") == "blog-posts/a%2Fb"
        assert document_endpoint(item, "a?b") == "blog-posts/a%3Fb"
        assert document_endpoint(item, "a b") == "blog-posts/a%20b"
        assert document_endpoint(item, "a%b") == "blog-posts/a%25b"

    def test_uses_plural_name_not_uid(self) -> None:
        """Document path uses pluralName, never a guessed UID plural."""
        item = _list_item()
        path = document_endpoint(item, "xyz")
        assert path.startswith("blog-posts/")
        assert not path.startswith("posts/")

    def test_missing_plural_name_raises(self) -> None:
        """document_endpoint raises when pluralName is missing."""
        with pytest.raises(ValidationError, match="pluralName"):
            document_endpoint({"uid": _MISLEADING_UID}, "abc")

    def test_blank_document_id_raises(self) -> None:
        """Empty or whitespace document_id is not joined as a trailing slash."""
        item = _list_item()
        for document_id in ("", "   "):
            with pytest.raises(ValidationError, match="document_id") as exc_info:
                document_endpoint(item, document_id)
            assert "posts" not in str(exc_info.value)
            assert exc_info.value.details.get("uid") == _MISLEADING_UID


class TestPublicExports:
    """Helpers are exported from the package and utils."""

    def test_package_and_utils_export_same_functions(self) -> None:
        """Package root and utils expose the same callables."""
        assert collection_endpoint is utils_collection_endpoint
        assert document_endpoint is utils_document_endpoint
