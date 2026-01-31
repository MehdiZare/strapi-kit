"""Tests for populate functionality."""

import pytest

from py_strapi.models.enums import SortDirection
from py_strapi.models.request.filters import FilterBuilder
from py_strapi.models.request.populate import Populate, PopulateField
from py_strapi.models.request.sort import Sort


class TestPopulateField:
    """Tests for PopulateField model."""

    def test_simple_field(self) -> None:
        """Test simple populate field."""
        field = PopulateField(field="author")
        result = field.to_dict()

        assert result == {"author": {"populate": "*"}}

    def test_field_with_selection(self) -> None:
        """Test populate field with field selection."""
        field = PopulateField(field="author", fields=["name", "email"])
        result = field.to_dict()

        assert result == {"author": {"fields": ["name", "email"], "populate": "*"}}

    def test_field_with_filters(self) -> None:
        """Test populate field with filters."""
        field = PopulateField(field="comments", filters=FilterBuilder().eq("approved", True))
        result = field.to_dict()

        assert "comments" in result
        assert "filters" in result["comments"]
        assert result["comments"]["filters"] == {"approved": {"$eq": True}}

    def test_field_with_sort(self) -> None:
        """Test populate field with sort."""
        field = PopulateField(
            field="posts", sort=Sort().by_field("publishedAt", SortDirection.DESC)
        )
        result = field.to_dict()

        assert "posts" in result
        assert "sort" in result["posts"]
        assert result["posts"]["sort"] == ["publishedAt:desc"]


class TestPopulate:
    """Tests for Populate fluent API."""

    def test_empty_populate(self) -> None:
        """Test empty populate returns empty dict."""
        populate = Populate()
        assert populate.to_query_dict() == {}

    def test_populate_all(self) -> None:
        """Test populate all relations."""
        populate = Populate().all()
        assert populate.to_query_dict() == {"populate": "*"}

    def test_populate_simple_list(self) -> None:
        """Test populate with simple field list."""
        populate = Populate().fields_list(["author", "category", "tags"])
        result = populate.to_query_dict()

        assert result == {"populate": ["author", "category", "tags"]}

    def test_populate_single_field(self) -> None:
        """Test populate single field."""
        populate = Populate().fields_list(["author"])
        result = populate.to_query_dict()

        assert result == {"populate": ["author"]}

    def test_add_field_simple(self) -> None:
        """Test add_field with simple configuration."""
        populate = Populate().add_field("author")
        result = populate.to_query_dict()

        # Simple field should use array format
        assert result == {"populate": ["author"]}

    def test_add_field_with_selection(self) -> None:
        """Test add_field with field selection."""
        populate = Populate().add_field("author", fields=["name", "email"])
        result = populate.to_query_dict()

        # With configuration, uses object format
        assert "populate" in result
        assert "author" in result["populate"]
        assert result["populate"]["author"]["fields"] == ["name", "email"]

    def test_add_field_with_filters(self) -> None:
        """Test add_field with filters."""
        populate = Populate().add_field("comments", filters=FilterBuilder().eq("approved", True))
        result = populate.to_query_dict()

        assert "populate" in result
        assert "comments" in result["populate"]
        assert "filters" in result["populate"]["comments"]

    def test_add_field_with_sort(self) -> None:
        """Test add_field with sort."""
        populate = Populate().add_field(
            "posts", sort=Sort().by_field("publishedAt", SortDirection.DESC)
        )
        result = populate.to_query_dict()

        assert "populate" in result
        assert "posts" in result["populate"]
        assert result["populate"]["posts"]["sort"] == ["publishedAt:desc"]

    def test_multiple_simple_fields(self) -> None:
        """Test multiple simple fields."""
        populate = Populate().add_field("author").add_field("category")
        result = populate.to_query_dict()

        # All simple, should use array format
        assert result == {"populate": ["author", "category"]}

    def test_mixed_simple_and_complex_fields(self) -> None:
        """Test mix of simple and complex field configurations."""
        populate = (
            Populate()
            .add_field("category")  # Simple
            .add_field("author", fields=["name"])  # Complex
        )
        result = populate.to_query_dict()

        # Has complex config, must use object format
        assert "populate" in result
        assert isinstance(result["populate"], dict)
        assert "category" in result["populate"]
        assert "author" in result["populate"]

    def test_nested_population(self) -> None:
        """Test nested population."""
        populate = Populate().add_field("author", nested=Populate().add_field("profile"))
        result = populate.to_query_dict()

        assert "populate" in result
        assert "author" in result["populate"]
        # Nested populate should be present
        assert "populate" in result["populate"]["author"]

    def test_deeply_nested_population(self) -> None:
        """Test deeply nested population."""
        populate = Populate().add_field(
            "author",
            nested=Populate().add_field("profile", nested=Populate().add_field("avatar")),
        )
        result = populate.to_query_dict()

        assert "populate" in result
        assert "author" in result["populate"]
        author_pop = result["populate"]["author"]["populate"]
        assert "profile" in author_pop
        assert "populate" in author_pop["profile"]

    def test_complex_population_scenario(self) -> None:
        """Test complex real-world population scenario."""
        populate = (
            Populate()
            .add_field("author", fields=["name", "email", "bio"])
            .add_field(
                "comments",
                filters=FilterBuilder().eq("approved", True),
                sort=Sort().by_field("createdAt", SortDirection.DESC),
                nested=Populate().add_field("author", fields=["name"]),
            )
            .add_field("category")
        )
        result = populate.to_query_dict()

        assert "populate" in result
        assert isinstance(result["populate"], dict)
        assert "author" in result["populate"]
        assert "comments" in result["populate"]
        assert "category" in result["populate"]

        # Check author config
        assert result["populate"]["author"]["fields"] == ["name", "email", "bio"]

        # Check comments config
        comments_config = result["populate"]["comments"]
        assert "filters" in comments_config
        assert "sort" in comments_config
        assert "populate" in comments_config

    def test_recursion_depth_limit(self) -> None:
        """Test that excessive nesting raises RecursionError."""
        # Build deeply nested populate structure that exceeds max depth
        # With max_depth=10, depth can be 0-10 (11 levels), so 12 levels should fail
        nested = Populate().add_field("level12")
        for i in range(11, 0, -1):
            nested = Populate().add_field(f"level{i}", nested=nested)

        # Default max depth is 10, so 12 levels should fail
        with pytest.raises(RecursionError) as exc_info:
            nested.to_query_dict()

        assert "maximum depth" in str(exc_info.value).lower()

    def test_custom_max_depth(self) -> None:
        """Test custom max depth parameter."""
        # Build 5 levels of nesting
        nested = Populate().add_field("level5")
        for i in range(4, 0, -1):
            nested = Populate().add_field(f"level{i}", nested=nested)

        # With max_depth=3, 5 levels should fail (depth goes 0,1,2,3,4)
        with pytest.raises(RecursionError):
            nested.to_query_dict(_max_depth=3)

        # With max_depth=5, should succeed (depth goes 0,1,2,3,4 which is <= 5)
        result = nested.to_query_dict(_max_depth=5)
        assert "populate" in result
