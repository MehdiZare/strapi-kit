"""E2E tests for query builder functionality.

Tests filters, sorting, pagination, and population against a real Strapi instance.
"""

from __future__ import annotations

import pytest

from py_strapi import SyncClient
from py_strapi.models import FilterBuilder, SortDirection, StrapiQuery

from .seed_data import DataSeeder, SeededData


@pytest.fixture(scope="module")
def seeded_data(e2e_strapi_config) -> SeededData:
    """Seed test data for query tests.

    This fixture is module-scoped so data is seeded once
    and reused across all tests in this module.
    """
    with SyncClient(e2e_strapi_config) as client:
        seeder = DataSeeder(client)
        seeded = seeder.seed_all()
        yield seeded
        seeder.cleanup(seeded)


@pytest.mark.e2e
class TestFilterOperations:
    """Tests for filter operations."""

    def test_filter_eq(self, sync_client: SyncClient, seeded_data: SeededData) -> None:
        """Test equality filter."""
        query = StrapiQuery().filter(FilterBuilder().eq("status", "published"))

        response = sync_client.get_many("articles", query=query)

        assert response.data is not None
        assert len(response.data) > 0
        for article in response.data:
            assert article.attributes["status"] == "published"

    def test_filter_ne(self, sync_client: SyncClient, seeded_data: SeededData) -> None:
        """Test not-equal filter."""
        query = StrapiQuery().filter(FilterBuilder().ne("status", "archived"))

        response = sync_client.get_many("articles", query=query)

        assert response.data is not None
        for article in response.data:
            assert article.attributes["status"] != "archived"

    def test_filter_gt(self, sync_client: SyncClient, seeded_data: SeededData) -> None:
        """Test greater-than filter."""
        query = StrapiQuery().filter(FilterBuilder().gt("views", 1000))

        response = sync_client.get_many("articles", query=query)

        assert response.data is not None
        for article in response.data:
            assert article.attributes["views"] > 1000

    def test_filter_lt(self, sync_client: SyncClient, seeded_data: SeededData) -> None:
        """Test less-than filter."""
        query = StrapiQuery().filter(FilterBuilder().lt("views", 2000))

        response = sync_client.get_many("articles", query=query)

        assert response.data is not None
        for article in response.data:
            assert article.attributes["views"] < 2000

    def test_filter_contains(self, sync_client: SyncClient, seeded_data: SeededData) -> None:
        """Test contains filter (case-sensitive)."""
        query = StrapiQuery().filter(FilterBuilder().contains("title", "Python"))

        response = sync_client.get_many("articles", query=query)

        assert response.data is not None
        for article in response.data:
            assert "Python" in article.attributes["title"]

    def test_filter_containsi(self, sync_client: SyncClient, seeded_data: SeededData) -> None:
        """Test case-insensitive contains filter."""
        query = StrapiQuery().filter(FilterBuilder().containsi("title", "python"))

        response = sync_client.get_many("articles", query=query)

        assert response.data is not None
        for article in response.data:
            assert "python" in article.attributes["title"].lower()

    def test_filter_in(self, sync_client: SyncClient, seeded_data: SeededData) -> None:
        """Test 'in' filter with multiple values."""
        query = StrapiQuery().filter(FilterBuilder().in_("status", ["published", "draft"]))

        response = sync_client.get_many("articles", query=query)

        assert response.data is not None
        for article in response.data:
            assert article.attributes["status"] in ["published", "draft"]

    def test_filter_or_group(self, sync_client: SyncClient, seeded_data: SeededData) -> None:
        """Test OR group filter."""
        query = StrapiQuery().filter(
            FilterBuilder().or_group(
                FilterBuilder().gt("views", 3000),
                FilterBuilder().eq("status", "draft"),
            )
        )

        response = sync_client.get_many("articles", query=query)

        assert response.data is not None
        for article in response.data:
            # Either views > 3000 OR status is draft
            assert article.attributes["views"] > 3000 or article.attributes["status"] == "draft"

    def test_filter_combined(self, sync_client: SyncClient, seeded_data: SeededData) -> None:
        """Test combining multiple filters (AND)."""
        query = StrapiQuery().filter(FilterBuilder().eq("status", "published").gt("views", 500))

        response = sync_client.get_many("articles", query=query)

        assert response.data is not None
        for article in response.data:
            assert article.attributes["status"] == "published"
            assert article.attributes["views"] > 500


@pytest.mark.e2e
class TestSortOperations:
    """Tests for sorting operations."""

    def test_sort_ascending(self, sync_client: SyncClient, seeded_data: SeededData) -> None:
        """Test ascending sort."""
        query = StrapiQuery().sort_by("views", SortDirection.ASC)

        response = sync_client.get_many("articles", query=query)

        assert response.data is not None
        assert len(response.data) >= 2
        views = [a.attributes["views"] for a in response.data]
        assert views == sorted(views)

    def test_sort_descending(self, sync_client: SyncClient, seeded_data: SeededData) -> None:
        """Test descending sort."""
        query = StrapiQuery().sort_by("views", SortDirection.DESC)

        response = sync_client.get_many("articles", query=query)

        assert response.data is not None
        assert len(response.data) >= 2
        views = [a.attributes["views"] for a in response.data]
        assert views == sorted(views, reverse=True)

    def test_sort_by_title(self, sync_client: SyncClient, seeded_data: SeededData) -> None:
        """Test sorting by string field."""
        query = StrapiQuery().sort_by("title", SortDirection.ASC)

        response = sync_client.get_many("articles", query=query)

        assert response.data is not None
        assert len(response.data) >= 2
        titles = [a.attributes["title"] for a in response.data]
        assert titles == sorted(titles)


@pytest.mark.e2e
class TestPaginationOperations:
    """Tests for pagination operations."""

    def test_page_based_pagination(self, sync_client: SyncClient, seeded_data: SeededData) -> None:
        """Test page-based pagination."""
        query = StrapiQuery().paginate(page=1, page_size=2)

        response = sync_client.get_many("articles", query=query)

        assert response.data is not None
        assert len(response.data) <= 2
        assert response.meta is not None
        assert response.meta.pagination is not None
        assert response.meta.pagination.page == 1
        assert response.meta.pagination.page_size == 2

    def test_pagination_metadata(self, sync_client: SyncClient, seeded_data: SeededData) -> None:
        """Test that pagination metadata is accurate."""
        query = StrapiQuery().paginate(page=1, page_size=3)

        response = sync_client.get_many("articles", query=query)

        assert response.meta is not None
        assert response.meta.pagination is not None
        pagination = response.meta.pagination

        # Total should be >= the number of seeded articles
        assert pagination.total >= len(seeded_data.articles)
        # Page count should be calculated correctly
        expected_pages = (pagination.total + pagination.page_size - 1) // pagination.page_size
        assert pagination.page_count == expected_pages

    def test_pagination_page_two(self, sync_client: SyncClient, seeded_data: SeededData) -> None:
        """Test accessing page two."""
        # First, get total count
        first_query = StrapiQuery().paginate(page=1, page_size=2)
        first_response = sync_client.get_many("articles", query=first_query)

        assert first_response.meta is not None
        assert first_response.meta.pagination is not None

        if first_response.meta.pagination.page_count > 1:
            # Get page 2
            second_query = StrapiQuery().paginate(page=2, page_size=2)
            second_response = sync_client.get_many("articles", query=second_query)

            assert second_response.data is not None
            assert second_response.meta is not None
            assert second_response.meta.pagination is not None
            assert second_response.meta.pagination.page == 2

            # Ensure different items
            first_ids = {a.id for a in first_response.data}
            second_ids = {a.id for a in second_response.data}
            assert first_ids.isdisjoint(second_ids)


@pytest.mark.e2e
class TestPopulationOperations:
    """Tests for population (relation loading) operations."""

    def test_populate_single_relation(
        self, sync_client: SyncClient, seeded_data: SeededData
    ) -> None:
        """Test populating a single relation."""
        query = StrapiQuery().populate_fields(["author"])

        response = sync_client.get_many("articles", query=query)

        assert response.data is not None
        # Find an article with an author
        articles_with_author = [a for a in response.data if a.attributes.get("author") is not None]
        assert len(articles_with_author) > 0

        # Check author is populated
        author = articles_with_author[0].attributes["author"]
        assert author is not None
        # Author should have data (populated), not just an ID
        if isinstance(author, dict):
            assert "name" in author or "data" in author

    def test_populate_multiple_relations(
        self, sync_client: SyncClient, seeded_data: SeededData
    ) -> None:
        """Test populating multiple relations."""
        query = StrapiQuery().populate_fields(["author", "category"])

        response = sync_client.get_many("articles", query=query)

        assert response.data is not None
        # Find an article with both relations
        for article in response.data:
            author = article.attributes.get("author")
            category = article.attributes.get("category")
            if author is not None and category is not None:
                # Both should be populated objects
                break

    def test_populate_with_filter(self, sync_client: SyncClient, seeded_data: SeededData) -> None:
        """Test population combined with filtering."""
        query = (
            StrapiQuery()
            .filter(FilterBuilder().eq("status", "published"))
            .populate_fields(["author"])
        )

        response = sync_client.get_many("articles", query=query)

        assert response.data is not None
        for article in response.data:
            assert article.attributes["status"] == "published"


@pytest.mark.e2e
class TestFieldSelectionOperations:
    """Tests for field selection operations."""

    def test_select_specific_fields(self, sync_client: SyncClient, seeded_data: SeededData) -> None:
        """Test selecting only specific fields."""
        query = StrapiQuery().select(["title", "status"])

        response = sync_client.get_many("articles", query=query)

        assert response.data is not None
        assert len(response.data) > 0

        # Check that selected fields are present
        for article in response.data:
            assert "title" in article.attributes or article.attributes.get("title") is not None


@pytest.mark.e2e
class TestCombinedQueries:
    """Tests for combining multiple query features."""

    def test_filter_sort_paginate(self, sync_client: SyncClient, seeded_data: SeededData) -> None:
        """Test combining filter, sort, and pagination."""
        query = (
            StrapiQuery()
            .filter(FilterBuilder().eq("status", "published"))
            .sort_by("views", SortDirection.DESC)
            .paginate(page=1, page_size=3)
        )

        response = sync_client.get_many("articles", query=query)

        assert response.data is not None
        # All should be published
        for article in response.data:
            assert article.attributes["status"] == "published"

        # Should be sorted by views descending
        if len(response.data) >= 2:
            views = [a.attributes["views"] for a in response.data]
            assert views == sorted(views, reverse=True)

        # Pagination metadata should be present
        assert response.meta is not None
        assert response.meta.pagination is not None

    def test_full_query(self, sync_client: SyncClient, seeded_data: SeededData) -> None:
        """Test a comprehensive query with all features."""
        query = (
            StrapiQuery()
            .filter(FilterBuilder().ne("status", "archived"))
            .sort_by("title", SortDirection.ASC)
            .paginate(page=1, page_size=5)
            .populate_fields(["author", "category"])
        )

        response = sync_client.get_many("articles", query=query)

        assert response.data is not None
        assert response.meta is not None

        # Verify filter applied
        for article in response.data:
            assert article.attributes["status"] != "archived"

        # Verify sort applied
        if len(response.data) >= 2:
            titles = [a.attributes["title"] for a in response.data]
            assert titles == sorted(titles)
