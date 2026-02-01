"""Tests for sort functionality."""

from strapi_kit.models.enums import SortDirection
from strapi_kit.models.request.sort import Sort, SortField


class TestSortField:
    """Tests for SortField model."""

    def test_sort_field_asc(self) -> None:
        """Test sort field with ascending direction."""
        field = SortField(field="publishedAt", direction=SortDirection.ASC)
        assert field.to_string() == "publishedAt:asc"

    def test_sort_field_desc(self) -> None:
        """Test sort field with descending direction."""
        field = SortField(field="publishedAt", direction=SortDirection.DESC)
        assert field.to_string() == "publishedAt:desc"

    def test_sort_field_default_direction(self) -> None:
        """Test sort field with default direction (ASC)."""
        field = SortField(field="title")
        assert field.to_string() == "title:asc"
        assert field.direction == SortDirection.ASC

    def test_sort_field_nested(self) -> None:
        """Test sort field with nested relation."""
        field = SortField(field="author.name", direction=SortDirection.ASC)
        assert field.to_string() == "author.name:asc"


class TestSort:
    """Tests for Sort fluent API."""

    def test_empty_sort(self) -> None:
        """Test empty sort returns empty dict."""
        sort = Sort()
        assert sort.to_query_list() == []
        assert sort.to_query_dict() == {}

    def test_single_field_asc(self) -> None:
        """Test sort by single field ascending."""
        sort = Sort().by_field("publishedAt", SortDirection.ASC)
        assert sort.to_query_list() == ["publishedAt:asc"]
        assert sort.to_query_dict() == {"sort": ["publishedAt:asc"]}

    def test_single_field_desc(self) -> None:
        """Test sort by single field descending."""
        sort = Sort().by_field("publishedAt", SortDirection.DESC)
        assert sort.to_query_list() == ["publishedAt:desc"]
        assert sort.to_query_dict() == {"sort": ["publishedAt:desc"]}

    def test_single_field_default_direction(self) -> None:
        """Test sort by single field with default direction."""
        sort = Sort().by_field("title")
        assert sort.to_query_list() == ["title:asc"]

    def test_multiple_fields(self) -> None:
        """Test sort by multiple fields."""
        sort = (
            Sort()
            .by_field("status", SortDirection.ASC)
            .by_field("publishedAt", SortDirection.DESC)
            .by_field("title", SortDirection.ASC)
        )

        expected = ["status:asc", "publishedAt:desc", "title:asc"]
        assert sort.to_query_list() == expected
        assert sort.to_query_dict() == {"sort": expected}

    def test_then_by_method(self) -> None:
        """Test then_by method for readability."""
        sort = (
            Sort()
            .by_field("status", SortDirection.ASC)
            .then_by("publishedAt", SortDirection.DESC)
            .then_by("title")
        )

        expected = ["status:asc", "publishedAt:desc", "title:asc"]
        assert sort.to_query_list() == expected

    def test_nested_relation_field(self) -> None:
        """Test sort by nested relation field."""
        sort = Sort().by_field("author.name", SortDirection.ASC)
        assert sort.to_query_list() == ["author.name:asc"]

    def test_multiple_nested_fields(self) -> None:
        """Test sort by multiple nested fields."""
        sort = (
            Sort()
            .by_field("author.name", SortDirection.ASC)
            .then_by("category.name", SortDirection.ASC)
            .then_by("publishedAt", SortDirection.DESC)
        )

        expected = ["author.name:asc", "category.name:asc", "publishedAt:desc"]
        assert sort.to_query_list() == expected
