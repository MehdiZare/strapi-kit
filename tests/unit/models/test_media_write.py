"""Tests for media_write helper."""

import pytest

from strapi_kit import media_write
from strapi_kit.exceptions import ValidationError


def test_media_write_one_side_document_id() -> None:
    """One-side write is a dest documentId string."""
    assert media_write(file_ids=["file-dest"], multiple=False) == "file-dest"


def test_media_write_one_side_numeric() -> None:
    """One-side write accepts a dest numeric id (v4)."""
    assert media_write(file_ids=[50], multiple=False) == 50


def test_media_write_one_side_empty() -> None:
    """Empty one-side media clears the field."""
    assert media_write(file_ids=[], multiple=False) is None


def test_media_write_many_side() -> None:
    """Many-side write is a list of dest ids."""
    assert media_write(file_ids=["a", 2], multiple=True) == ["a", 2]


def test_media_write_many_side_empty() -> None:
    """Empty many-side media is an empty list."""
    assert media_write(file_ids=[], multiple=True) == []


def test_media_write_rejects_two_ids_on_one_side() -> None:
    """One-side media cannot take two dest ids."""
    with pytest.raises(ValidationError, match="at most one"):
        media_write(file_ids=["a", "b"], multiple=False)


def test_media_write_rejects_bare_string() -> None:
    """A bare string is not a sequence of dest ids."""
    with pytest.raises(ValidationError, match="sequence"):
        media_write(file_ids="abc", multiple=False)  # type: ignore[arg-type]
