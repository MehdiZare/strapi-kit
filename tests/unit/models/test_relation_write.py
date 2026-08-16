"""Tests for Strapi 5 relation write payload helper."""

import pytest

import strapi_kit
import strapi_kit.models as models_pkg
from strapi_kit import RelationWriteOp, ValidationError, relation_write


class TestRelationWriteOp:
    """Tests for RelationWriteOp enum values."""

    def test_enum_values(self) -> None:
        """Enum members match the Strapi 5 REST vocabulary."""
        assert RelationWriteOp.SET == "set"
        assert RelationWriteOp.CONNECT == "connect"
        assert RelationWriteOp.DISCONNECT == "disconnect"
        assert RelationWriteOp.SET.value == "set"
        assert {member.value for member in RelationWriteOp} == {
            "set",
            "connect",
            "disconnect",
        }

    def test_public_exports(self) -> None:
        """Helper and enum are public on the package and models package."""
        assert strapi_kit.RelationWriteOp is RelationWriteOp
        assert strapi_kit.relation_write is relation_write
        assert models_pkg.RelationWriteOp is RelationWriteOp
        assert models_pkg.relation_write is relation_write
        assert "RelationWriteOp" in strapi_kit.__all__
        assert "relation_write" in strapi_kit.__all__
        assert "RelationWriteOp" in models_pkg.__all__
        assert "relation_write" in models_pkg.__all__


class TestRelationWriteSingle:
    """One-side relation writes return a documentId string or None."""

    def test_single_id(self) -> None:
        """A single documentId is returned as a string."""
        assert relation_write(document_ids=["authorDoc"], multiple=False) == "authorDoc"

    def test_single_empty_returns_none(self) -> None:
        """Zero ids clear a one-side relation."""
        assert relation_write(document_ids=[], multiple=False) is None

    def test_single_with_two_ids_raises(self) -> None:
        """Two or more ids are invalid for a one-side field."""
        with pytest.raises(ValidationError, match="at most one documentId") as exc_info:
            relation_write(document_ids=["a", "b"], multiple=False)

        assert exc_info.value.details["count"] == 2
        assert exc_info.value.details["document_ids"] == ["a", "b"]


class TestRelationWriteMultiple:
    """Many-side relation writes return {op: [documentIds]}."""

    def test_multi_set(self) -> None:
        """Default op is set and replaces the full relation list."""
        assert relation_write(document_ids=["docId1", "docId2"], multiple=True) == {
            "set": ["docId1", "docId2"]
        }
        assert relation_write(
            document_ids=["docId1", "docId2"],
            multiple=True,
            op=RelationWriteOp.SET,
        ) == {"set": ["docId1", "docId2"]}

    def test_multi_connect(self) -> None:
        """connect adds documentIds without replacing existing links."""
        assert relation_write(
            document_ids=["docId3"],
            multiple=True,
            op=RelationWriteOp.CONNECT,
        ) == {"connect": ["docId3"]}

    def test_multi_disconnect(self) -> None:
        """disconnect removes the given documentIds."""
        assert relation_write(
            document_ids=["docId1"],
            multiple=True,
            op=RelationWriteOp.DISCONNECT,
        ) == {"disconnect": ["docId1"]}

    def test_multi_empty_set(self) -> None:
        """An empty many-side set list is a valid full replace (clear)."""
        assert relation_write(document_ids=[], multiple=True) == {"set": []}

    def test_multi_accepts_tuple(self) -> None:
        """Any sequence of documentIds is accepted, not only lists."""
        assert relation_write(document_ids=("docId1", "docId2"), multiple=True) == {
            "set": ["docId1", "docId2"]
        }

    def test_string_op_values_coerce(self) -> None:
        """Official REST op strings coerce to RelationWriteOp (StrEnum values)."""
        assert relation_write(
            document_ids=["docId3"],
            multiple=True,
            op="connect",  # type: ignore[arg-type]
        ) == {"connect": ["docId3"]}
        assert relation_write(
            document_ids=["docId1"],
            multiple=True,
            op="disconnect",  # type: ignore[arg-type]
        ) == {"disconnect": ["docId1"]}


class TestRelationWriteNormalize:
    """Optional {"documentId": "..."} objects normalize to short strings."""

    def test_normalize_document_id_objects(self) -> None:
        """Object form is accepted and emitted as documentId strings."""
        assert (
            relation_write(document_ids=[{"documentId": "authorDoc"}], multiple=False)
            == "authorDoc"
        )
        assert relation_write(
            document_ids=[{"documentId": "cat1"}, {"document_id": "cat2"}],
            multiple=True,
        ) == {"set": ["cat1", "cat2"]}

    def test_mixed_strings_and_objects(self) -> None:
        """Strings and objects can be mixed in one call."""
        assert relation_write(
            document_ids=["cat1", {"documentId": "cat2"}],
            multiple=True,
            op=RelationWriteOp.CONNECT,
        ) == {"connect": ["cat1", "cat2"]}

    def test_strips_document_id_whitespace(self) -> None:
        """Leading/trailing whitespace is stripped from documentIds."""
        assert relation_write(document_ids=["  authorDoc  "], multiple=False) == "authorDoc"


class TestRelationWriteValidation:
    """Invalid inputs raise ValidationError."""

    def test_bare_string_raises(self) -> None:
        """A bare string must not be iterated as character ids."""
        with pytest.raises(ValidationError, match="sequence of documentId"):
            relation_write(document_ids="abc123", multiple=True)  # type: ignore[arg-type]

    def test_empty_string_id_raises(self) -> None:
        """Empty documentId strings are rejected."""
        with pytest.raises(ValidationError, match="non-empty string"):
            relation_write(document_ids=["  "], multiple=False)

    def test_object_without_document_id_raises(self) -> None:
        """v4 {id: n} objects are not accepted."""
        with pytest.raises(ValidationError, match="documentId"):
            relation_write(document_ids=[{"id": 1}], multiple=True)

    def test_numeric_id_raises(self) -> None:
        """Numeric ids are v4-shaped and rejected."""
        with pytest.raises(ValidationError, match="not numeric id"):
            relation_write(document_ids=[1], multiple=True)  # type: ignore[list-item]

    def test_none_id_raises(self) -> None:
        """None is not a documentId (use [] to clear a one-side field)."""
        with pytest.raises(ValidationError, match="not numeric id"):
            relation_write(document_ids=[None], multiple=False)  # type: ignore[list-item]

    def test_object_empty_document_id_raises(self) -> None:
        """Object form still requires a non-empty documentId."""
        with pytest.raises(ValidationError, match="documentId"):
            relation_write(document_ids=[{"documentId": "  "}], multiple=True)

    def test_invalid_op_raises(self) -> None:
        """Unknown ops must not emit an unofficial payload key."""
        with pytest.raises(ValidationError, match="RelationWriteOp") as exc_info:
            relation_write(
                document_ids=["a"],
                multiple=True,
                op="merge",  # type: ignore[arg-type]
            )

        assert exc_info.value.details["op"] == "merge"

    def test_invalid_op_rejected_on_one_side(self) -> None:
        """Invalid op is rejected even when unused for a one-side write."""
        with pytest.raises(ValidationError, match="RelationWriteOp"):
            relation_write(
                document_ids=["authorDoc"],
                multiple=False,
                op="merge",  # type: ignore[arg-type]
            )

    def test_non_string_op_raises(self) -> None:
        """Non-enum, non-string ops cannot become unofficial payload keys."""
        with pytest.raises(ValidationError, match="RelationWriteOp") as exc_info:
            relation_write(
                document_ids=["a"],
                multiple=True,
                op=1,  # type: ignore[arg-type]
            )

        assert exc_info.value.details["op"] == 1
