"""Tests for StrapiQuery builder."""

import pytest

from py_strapi.models.enums import PublicationState, SortDirection
from py_strapi.models.request.filters import FilterBuilder
from py_strapi.models.request.populate import Populate
from py_strapi.models.request.query import StrapiQuery


class TestStrapiQuery:
    """Tests for StrapiQuery builder."""

    def test_empty_query(self) -> None:
        """Test empty query returns empty params."""
        query = StrapiQuery()
        assert query.to_query_params() == {}

    def test_filter_only(self) -> None:
        """Test query with only filters."""
        query = StrapiQuery().filter(FilterBuilder().eq("status", "published"))
        params = query.to_query_params()

        # Filters are flattened to bracket notation for Strapi compatibility
        assert "filters[status][$eq]" in params
        assert params["filters[status][$eq]"] == "published"

    def test_sort_only(self) -> None:
        """Test query with only sorting."""
        query = StrapiQuery().sort_by("publishedAt", SortDirection.DESC)
        params = query.to_query_params()

        assert "sort" in params
        assert params["sort"] == ["publishedAt:desc"]

    def test_multiple_sorts(self) -> None:
        """Test query with multiple sort fields."""
        query = (
            StrapiQuery()
            .sort_by("status", SortDirection.ASC)
            .then_sort_by("publishedAt", SortDirection.DESC)
        )
        params = query.to_query_params()

        assert params["sort"] == ["status:asc", "publishedAt:desc"]

    def test_page_pagination(self) -> None:
        """Test query with page-based pagination."""
        query = StrapiQuery().paginate(page=2, page_size=50)
        params = query.to_query_params()

        assert params["pagination[page]"] == 2
        assert params["pagination[pageSize]"] == 50
        assert params["pagination[withCount]"] is True

    def test_offset_pagination(self) -> None:
        """Test query with offset-based pagination."""
        query = StrapiQuery().paginate(start=100, limit=25)
        params = query.to_query_params()

        assert params["pagination[start]"] == 100
        assert params["pagination[limit]"] == 25
        assert params["pagination[withCount]"] is True

    def test_pagination_without_count(self) -> None:
        """Test pagination with count disabled."""
        query = StrapiQuery().paginate(page=1, page_size=10, with_count=False)
        params = query.to_query_params()

        assert params["pagination[withCount]"] is False

    def test_pagination_mixed_error(self) -> None:
        """Test that mixing pagination strategies raises error."""
        with pytest.raises(ValueError, match="Cannot mix"):
            StrapiQuery().paginate(page=1, start=0)

    def test_populate_all(self) -> None:
        """Test populate all relations."""
        query = StrapiQuery().populate_all()
        params = query.to_query_params()

        assert params["populate"] == "*"

    def test_populate_fields_list(self) -> None:
        """Test populate with field list."""
        query = StrapiQuery().populate_fields(["author", "category", "tags"])
        params = query.to_query_params()

        assert params["populate"] == ["author", "category", "tags"]

    def test_populate_complex(self) -> None:
        """Test populate with complex configuration."""
        query = StrapiQuery().populate(Populate().add_field("author", fields=["name", "email"]))
        params = query.to_query_params()

        assert "populate" in params
        assert "author" in params["populate"]
        assert params["populate"]["author"]["fields"] == ["name", "email"]

    def test_select_fields(self) -> None:
        """Test field selection."""
        query = StrapiQuery().select(["title", "description", "publishedAt"])
        params = query.to_query_params()

        assert params["fields"] == ["title", "description", "publishedAt"]

    def test_with_locale(self) -> None:
        """Test locale parameter."""
        query = StrapiQuery().with_locale("fr")
        params = query.to_query_params()

        assert params["locale"] == "fr"

    def test_with_publication_state(self) -> None:
        """Test publication state parameter."""
        query = StrapiQuery().with_publication_state(PublicationState.LIVE)
        params = query.to_query_params()

        assert params["publicationState"] == "live"

    def test_simple_complete_query(self) -> None:
        """Test simple complete query with multiple parameters."""
        query = (
            StrapiQuery()
            .filter(FilterBuilder().eq("status", "published"))
            .sort_by("publishedAt", SortDirection.DESC)
            .paginate(page=1, page_size=25)
            .populate_fields(["author", "category"])
            .select(["title", "description"])
        )
        params = query.to_query_params()

        # Verify all parameters are present
        assert "filters[status][$eq]" in params
        assert "sort" in params
        assert "pagination[page]" in params
        assert "pagination[pageSize]" in params
        assert "populate" in params
        assert "fields" in params

        # Verify values
        assert params["filters[status][$eq]"] == "published"
        assert params["sort"] == ["publishedAt:desc"]
        assert params["pagination[page]"] == 1
        assert params["pagination[pageSize]"] == 25
        assert params["populate"] == ["author", "category"]
        assert params["fields"] == ["title", "description"]

    def test_complex_query_with_nested_population(self) -> None:
        """Test complex query with nested population and filtering."""
        query = (
            StrapiQuery()
            .filter(
                FilterBuilder()
                .eq("status", "published")
                .gt("views", 100)
                .or_group(
                    FilterBuilder().contains("title", "Python"),
                    FilterBuilder().contains("title", "Django"),
                )
            )
            .sort_by("views", SortDirection.DESC)
            .then_sort_by("publishedAt", SortDirection.DESC)
            .paginate(page=1, page_size=10)
            .populate(
                Populate()
                .add_field("author", fields=["name", "email"])
                .add_field(
                    "comments",
                    filters=FilterBuilder().eq("approved", True),
                    nested=Populate().add_field("author", fields=["name"]),
                )
            )
            .select(["title", "description", "views"])
            .with_locale("en")
        )
        params = query.to_query_params()

        # Verify filters are flattened to bracket notation
        assert "filters[status][$eq]" in params
        assert "filters[views][$gt]" in params
        # OR group creates nested structure
        has_or = any("$or" in key for key in params.keys())
        assert has_or

        # Verify sort
        assert params["sort"] == ["views:desc", "publishedAt:desc"]

        # Verify pagination
        assert params["pagination[page]"] == 1
        assert params["pagination[pageSize]"] == 10

        # Verify populate
        assert "populate" in params
        assert "author" in params["populate"]
        assert "comments" in params["populate"]

        # Verify fields
        assert params["fields"] == ["title", "description", "views"]

        # Verify locale
        assert params["locale"] == "en"

    def test_query_chaining_order_independence(self) -> None:
        """Test that query building order doesn't matter."""
        query1 = (
            StrapiQuery()
            .filter(FilterBuilder().eq("status", "published"))
            .sort_by("publishedAt")
            .paginate(page=1, page_size=10)
        )

        query2 = (
            StrapiQuery()
            .paginate(page=1, page_size=10)
            .filter(FilterBuilder().eq("status", "published"))
            .sort_by("publishedAt")
        )

        # Both should produce same params
        params1 = query1.to_query_params()
        params2 = query2.to_query_params()

        assert params1 == params2

    def test_to_query_dict_alias(self) -> None:
        """Test that to_query_dict is alias for to_query_params."""
        query = StrapiQuery().filter(FilterBuilder().eq("status", "published"))

        params = query.to_query_params()
        dict_result = query.to_query_dict()

        assert params == dict_result

    def test_realistic_blog_query(self) -> None:
        """Test realistic blog article query."""
        query = (
            StrapiQuery()
            .filter(
                FilterBuilder()
                .eq("status", "published")
                .null("deletedAt")
                .gte("publishedAt", "2024-01-01")
            )
            .sort_by("publishedAt", SortDirection.DESC)
            .paginate(page=1, page_size=20)
            .populate(
                Populate()
                .add_field("author", fields=["name", "avatar", "bio"])
                .add_field("category")
                .add_field("tags")
            )
            .select(["title", "slug", "excerpt", "coverImage", "publishedAt"])
            .with_publication_state(PublicationState.LIVE)
        )
        params = query.to_query_params()

        # Verify structure (filters are flattened to bracket notation)
        assert "filters[status][$eq]" in params
        assert "sort" in params
        assert "pagination[page]" in params
        assert "populate" in params
        assert "fields" in params
        assert "publicationState" in params

        # Verify publication state
        assert params["publicationState"] == "live"

    def test_realistic_ecommerce_query(self) -> None:
        """Test realistic e-commerce product query."""
        query = (
            StrapiQuery()
            .filter(
                FilterBuilder()
                .eq("inStock", True)
                .between("price", 10, 100)
                .in_("category", ["electronics", "accessories"])
            )
            .sort_by("price", SortDirection.ASC)
            .then_sort_by("rating", SortDirection.DESC)
            .paginate(start=0, limit=50)
            .populate(
                Populate()
                .add_field("images")
                .add_field("reviews", filters=FilterBuilder().gte("rating", 4))
            )
            .select(["name", "price", "sku", "rating"])
        )
        params = query.to_query_params()

        # Verify filters are flattened to bracket notation
        assert params["filters[inStock][$eq]"] is True
        assert params["filters[price][$between]"] == [10, 100]
        assert params["filters[category][$in]"] == ["electronics", "accessories"]

        # Verify sort
        assert params["sort"] == ["price:asc", "rating:desc"]

        # Verify offset pagination
        assert params["pagination[start]"] == 0
        assert params["pagination[limit]"] == 50
