"""Tests for relation resolver."""


from py_strapi.export.relation_resolver import RelationResolver


def test_extract_relations_single() -> None:
    """Test extracting a single relation."""
    data = {
        "title": "Article 1",
        "author": {"data": {"id": 5, "name": "Author Name"}},
    }

    relations = RelationResolver.extract_relations(data)

    assert "author" in relations
    assert relations["author"] == [5]


def test_extract_relations_multiple() -> None:
    """Test extracting multiple relations."""
    data = {
        "title": "Article 1",
        "categories": {
            "data": [
                {"id": 1, "name": "Category 1"},
                {"id": 2, "name": "Category 2"},
            ]
        },
    }

    relations = RelationResolver.extract_relations(data)

    assert "categories" in relations
    assert relations["categories"] == [1, 2]


def test_extract_relations_null() -> None:
    """Test extracting null relation."""
    data = {
        "title": "Article 1",
        "author": {"data": None},
    }

    relations = RelationResolver.extract_relations(data)

    assert "author" in relations
    assert relations["author"] == []


def test_extract_relations_mixed() -> None:
    """Test extracting mixed relations."""
    data = {
        "title": "Article 1",
        "author": {"data": {"id": 5}},
        "categories": {"data": [{"id": 1}, {"id": 2}]},
        "featured_image": {"data": {"id": 10}},
    }

    relations = RelationResolver.extract_relations(data)

    assert len(relations) == 3
    assert relations["author"] == [5]
    assert relations["categories"] == [1, 2]
    assert relations["featured_image"] == [10]


def test_extract_relations_no_relations() -> None:
    """Test extracting from data with no relations."""
    data = {
        "title": "Article 1",
        "content": "Some content",
        "published": True,
    }

    relations = RelationResolver.extract_relations(data)

    assert relations == {}


def test_strip_relations() -> None:
    """Test stripping relations from data."""
    data = {
        "title": "Article 1",
        "content": "Content",
        "author": {"data": {"id": 5}},
        "categories": {"data": [{"id": 1}, {"id": 2}]},
    }

    clean_data = RelationResolver.strip_relations(data)

    assert "title" in clean_data
    assert "content" in clean_data
    assert "author" not in clean_data
    assert "categories" not in clean_data


def test_strip_relations_no_relations() -> None:
    """Test stripping when there are no relations."""
    data = {
        "title": "Article 1",
        "content": "Content",
    }

    clean_data = RelationResolver.strip_relations(data)

    assert clean_data == data


def test_resolve_relations() -> None:
    """Test resolving relations with ID mapping."""
    relations = {
        "author": [5],
        "categories": [1, 2],
    }

    id_mapping = {
        "api::author.author": {5: 50},
        "api::category.category": {1: 10, 2: 20},
    }

    # Resolve author
    resolved_author = RelationResolver.resolve_relations(
        {"author": relations["author"]},
        id_mapping,
        "api::author.author",
    )
    assert resolved_author == {"author": [50]}

    # Resolve categories
    resolved_categories = RelationResolver.resolve_relations(
        {"categories": relations["categories"]},
        id_mapping,
        "api::category.category",
    )
    assert resolved_categories == {"categories": [10, 20]}


def test_resolve_relations_missing_mapping() -> None:
    """Test resolving with missing ID mapping."""
    relations = {"author": [5, 6]}
    id_mapping = {
        "api::author.author": {5: 50}  # 6 is missing
    }

    resolved = RelationResolver.resolve_relations(
        relations,
        id_mapping,
        "api::author.author",
    )

    # Should only include the mapped ID
    assert resolved == {"author": [50]}


def test_resolve_relations_no_mapping() -> None:
    """Test resolving with no mapping available."""
    relations = {"author": [5]}
    id_mapping = {}  # No mapping for this content type

    resolved = RelationResolver.resolve_relations(
        relations,
        id_mapping,
        "api::author.author",
    )

    assert resolved == {}


def test_build_relation_payload_single() -> None:
    """Test building payload for single relation."""
    relations = {"author": [10]}

    payload = RelationResolver.build_relation_payload(relations)

    # Single relation should use single ID, not array
    assert payload == {"author": 10}


def test_build_relation_payload_multiple() -> None:
    """Test building payload for multiple relations."""
    relations = {"categories": [10, 11, 12]}

    payload = RelationResolver.build_relation_payload(relations)

    # Multiple relations should use array
    assert payload == {"categories": [10, 11, 12]}


def test_build_relation_payload_mixed() -> None:
    """Test building payload with mixed relations."""
    relations = {
        "author": [10],
        "categories": [11, 12],
        "featured_image": [20],
    }

    payload = RelationResolver.build_relation_payload(relations)

    assert payload == {
        "author": 10,
        "categories": [11, 12],
        "featured_image": 20,
    }


def test_build_relation_payload_empty() -> None:
    """Test building payload with no relations."""
    relations = {}

    payload = RelationResolver.build_relation_payload(relations)

    assert payload == {}
