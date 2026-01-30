"""Tests for media handler."""

from py_strapi.export.media_handler import MediaHandler


def test_extract_media_references_single() -> None:
    """Test extracting a single media reference."""
    data = {
        "title": "Article",
        "cover": {
            "data": {
                "id": 5,
                "mime": "image/jpeg",
                "url": "/uploads/image.jpg",
            }
        },
    }

    media_ids = MediaHandler.extract_media_references(data)

    assert media_ids == [5]


def test_extract_media_references_multiple() -> None:
    """Test extracting multiple media references."""
    data = {
        "title": "Article",
        "gallery": {
            "data": [
                {"id": 10, "mime": "image/jpeg", "url": "/uploads/img1.jpg"},
                {"id": 11, "mime": "image/png", "url": "/uploads/img2.png"},
                {"id": 12, "mime": "image/gif", "url": "/uploads/img3.gif"},
            ]
        },
    }

    media_ids = MediaHandler.extract_media_references(data)

    assert media_ids == [10, 11, 12]


def test_extract_media_references_mixed() -> None:
    """Test extracting mixed media references."""
    data = {
        "title": "Article",
        "cover": {"data": {"id": 5, "mime": "image/jpeg"}},
        "gallery": {
            "data": [
                {"id": 10, "mime": "image/jpeg"},
                {"id": 11, "mime": "image/png"},
            ]
        },
        "attachment": {"data": {"id": 20, "mime": "application/pdf"}},
    }

    media_ids = MediaHandler.extract_media_references(data)

    assert media_ids == [5, 10, 11, 20]


def test_extract_media_references_null() -> None:
    """Test extracting when media is null."""
    data = {
        "title": "Article",
        "cover": {"data": None},
    }

    media_ids = MediaHandler.extract_media_references(data)

    assert media_ids == []


def test_extract_media_references_no_media() -> None:
    """Test extracting when there are no media references."""
    data = {
        "title": "Article",
        "content": "Some text content",
        "published": True,
    }

    media_ids = MediaHandler.extract_media_references(data)

    assert media_ids == []


def test_extract_media_references_ignores_relations() -> None:
    """Test that media extraction ignores relation fields."""
    data = {
        "title": "Article",
        "author": {"data": {"id": 99}},  # Relation (no mime)
        "cover": {"data": {"id": 5, "mime": "image/jpeg"}},  # Media (has mime)
    }

    media_ids = MediaHandler.extract_media_references(data)

    # Should only extract media (with mime), not relations
    assert media_ids == [5]


def test_update_media_references_single() -> None:
    """Test updating a single media reference."""
    data = {
        "title": "Article",
        "cover": {
            "data": {
                "id": 5,
                "mime": "image/jpeg",
                "url": "/uploads/image.jpg",
            }
        },
    }

    mapping = {5: 50}
    updated = MediaHandler.update_media_references(data, mapping)

    assert updated["cover"]["data"]["id"] == 50
    assert updated["cover"]["data"]["mime"] == "image/jpeg"


def test_update_media_references_multiple() -> None:
    """Test updating multiple media references."""
    data = {
        "title": "Article",
        "gallery": {
            "data": [
                {"id": 10, "mime": "image/jpeg"},
                {"id": 11, "mime": "image/png"},
            ]
        },
    }

    mapping = {10: 100, 11: 110}
    updated = MediaHandler.update_media_references(data, mapping)

    assert updated["gallery"]["data"][0]["id"] == 100
    assert updated["gallery"]["data"][1]["id"] == 110


def test_update_media_references_mixed() -> None:
    """Test updating mixed media references."""
    data = {
        "title": "Article",
        "cover": {"data": {"id": 5, "mime": "image/jpeg"}},
        "gallery": {
            "data": [
                {"id": 10, "mime": "image/jpeg"},
                {"id": 11, "mime": "image/png"},
            ]
        },
    }

    mapping = {5: 50, 10: 100, 11: 110}
    updated = MediaHandler.update_media_references(data, mapping)

    assert updated["cover"]["data"]["id"] == 50
    assert updated["gallery"]["data"][0]["id"] == 100
    assert updated["gallery"]["data"][1]["id"] == 110


def test_update_media_references_partial_mapping() -> None:
    """Test updating when mapping is incomplete."""
    data = {
        "gallery": {
            "data": [
                {"id": 10, "mime": "image/jpeg"},
                {"id": 11, "mime": "image/png"},
            ]
        },
    }

    mapping = {10: 100}  # Only one ID mapped
    updated = MediaHandler.update_media_references(data, mapping)

    # First should be updated, second should remain unchanged
    assert updated["gallery"]["data"][0]["id"] == 100
    assert updated["gallery"]["data"][1]["id"] == 11


def test_update_media_references_no_mapping() -> None:
    """Test updating when there's no mapping."""
    data = {
        "cover": {"data": {"id": 5, "mime": "image/jpeg"}},
    }

    mapping = {}  # Empty mapping
    updated = MediaHandler.update_media_references(data, mapping)

    # Should remain unchanged
    assert updated["cover"]["data"]["id"] == 5


def test_update_media_references_preserves_non_media_fields() -> None:
    """Test that non-media fields are preserved."""
    data = {
        "title": "Article",
        "content": "Some content",
        "published": True,
        "cover": {"data": {"id": 5, "mime": "image/jpeg"}},
    }

    mapping = {5: 50}
    updated = MediaHandler.update_media_references(data, mapping)

    assert updated["title"] == "Article"
    assert updated["content"] == "Some content"
    assert updated["published"] is True
    assert updated["cover"]["data"]["id"] == 50


def test_update_media_references_null_media() -> None:
    """Test updating when media is null."""
    data = {
        "title": "Article",
        "cover": {"data": None},
    }

    mapping = {5: 50}
    updated = MediaHandler.update_media_references(data, mapping)

    # Null media should remain null
    assert updated["cover"]["data"] is None


def test_update_media_references_ignores_relations() -> None:
    """Test that relation fields are not updated."""
    data = {
        "title": "Article",
        "author": {"data": {"id": 99}},  # Relation (no mime)
        "cover": {"data": {"id": 5, "mime": "image/jpeg"}},  # Media
    }

    mapping = {5: 50, 99: 999}
    updated = MediaHandler.update_media_references(data, mapping)

    # Media should be updated
    assert updated["cover"]["data"]["id"] == 50

    # Relation should remain unchanged (no mime field means it's not media)
    assert updated["author"]["data"]["id"] == 99
