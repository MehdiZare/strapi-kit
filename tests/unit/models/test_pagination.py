"""Tests for pagination functionality."""

import pytest
from pydantic import ValidationError

from py_strapi.models.request.pagination import OffsetPagination, PagePagination


class TestPagePagination:
    """Tests for PagePagination model."""

    def test_default_values(self) -> None:
        """Test page pagination with default values."""
        pagination = PagePagination()
        assert pagination.page == 1
        assert pagination.page_size == 25
        assert pagination.with_count is True

    def test_custom_values(self) -> None:
        """Test page pagination with custom values."""
        pagination = PagePagination(page=2, page_size=50, with_count=False)
        assert pagination.page == 2
        assert pagination.page_size == 50
        assert pagination.with_count is False

    def test_to_query_dict(self) -> None:
        """Test conversion to query parameters dictionary."""
        pagination = PagePagination(page=3, page_size=10, with_count=True)
        result = pagination.to_query_dict()

        assert result == {
            "pagination[page]": 3,
            "pagination[pageSize]": 10,
            "pagination[withCount]": True,
        }

    def test_to_query_dict_no_count(self) -> None:
        """Test query dict with count disabled."""
        pagination = PagePagination(page=1, page_size=100, with_count=False)
        result = pagination.to_query_dict()

        assert result["pagination[withCount]"] is False

    def test_page_validation_minimum(self) -> None:
        """Test page number must be >= 1."""
        with pytest.raises(ValidationError) as exc_info:
            PagePagination(page=0)

        assert "page" in str(exc_info.value).lower()

    def test_page_validation_negative(self) -> None:
        """Test page number cannot be negative."""
        with pytest.raises(ValidationError) as exc_info:
            PagePagination(page=-1)

        assert "page" in str(exc_info.value).lower()

    def test_page_size_validation_minimum(self) -> None:
        """Test page size must be >= 1."""
        with pytest.raises(ValidationError) as exc_info:
            PagePagination(page_size=0)

        assert "page_size" in str(exc_info.value).lower()

    def test_page_size_validation_maximum(self) -> None:
        """Test page size must be <= 100."""
        with pytest.raises(ValidationError) as exc_info:
            PagePagination(page_size=101)

        assert "page_size" in str(exc_info.value).lower()

    def test_page_size_at_boundaries(self) -> None:
        """Test page size at valid boundaries."""
        # Minimum valid
        pagination = PagePagination(page_size=1)
        assert pagination.page_size == 1

        # Maximum valid
        pagination = PagePagination(page_size=100)
        assert pagination.page_size == 100


class TestOffsetPagination:
    """Tests for OffsetPagination model."""

    def test_default_values(self) -> None:
        """Test offset pagination with default values."""
        pagination = OffsetPagination()
        assert pagination.start == 0
        assert pagination.limit == 25
        assert pagination.with_count is True

    def test_custom_values(self) -> None:
        """Test offset pagination with custom values."""
        pagination = OffsetPagination(start=50, limit=10, with_count=False)
        assert pagination.start == 50
        assert pagination.limit == 10
        assert pagination.with_count is False

    def test_to_query_dict(self) -> None:
        """Test conversion to query parameters dictionary."""
        pagination = OffsetPagination(start=100, limit=50, with_count=True)
        result = pagination.to_query_dict()

        assert result == {
            "pagination[start]": 100,
            "pagination[limit]": 50,
            "pagination[withCount]": True,
        }

    def test_to_query_dict_no_count(self) -> None:
        """Test query dict with count disabled."""
        pagination = OffsetPagination(start=0, limit=100, with_count=False)
        result = pagination.to_query_dict()

        assert result["pagination[withCount]"] is False

    def test_start_validation_negative(self) -> None:
        """Test start offset cannot be negative."""
        with pytest.raises(ValidationError) as exc_info:
            OffsetPagination(start=-1)

        assert "start" in str(exc_info.value).lower()

    def test_start_validation_zero(self) -> None:
        """Test start offset can be zero."""
        pagination = OffsetPagination(start=0)
        assert pagination.start == 0

    def test_limit_validation_minimum(self) -> None:
        """Test limit must be >= 1."""
        with pytest.raises(ValidationError) as exc_info:
            OffsetPagination(limit=0)

        assert "limit" in str(exc_info.value).lower()

    def test_limit_validation_maximum(self) -> None:
        """Test limit must be <= 100."""
        with pytest.raises(ValidationError) as exc_info:
            OffsetPagination(limit=101)

        assert "limit" in str(exc_info.value).lower()

    def test_limit_at_boundaries(self) -> None:
        """Test limit at valid boundaries."""
        # Minimum valid
        pagination = OffsetPagination(limit=1)
        assert pagination.limit == 1

        # Maximum valid
        pagination = OffsetPagination(limit=100)
        assert pagination.limit == 100

    def test_large_offset(self) -> None:
        """Test offset pagination with large start value."""
        pagination = OffsetPagination(start=10000, limit=25)
        result = pagination.to_query_dict()

        assert result["pagination[start]"] == 10000
        assert result["pagination[limit]"] == 25


class TestPaginationTypeAlias:
    """Tests for Pagination type alias."""

    def test_page_pagination_type(self) -> None:
        """Test PagePagination is valid Pagination type."""
        from py_strapi.models.request.pagination import Pagination

        pagination: Pagination = PagePagination(page=1, page_size=25)
        assert isinstance(pagination, PagePagination)

    def test_offset_pagination_type(self) -> None:
        """Test OffsetPagination is valid Pagination type."""
        from py_strapi.models.request.pagination import Pagination

        pagination: Pagination = OffsetPagination(start=0, limit=25)
        assert isinstance(pagination, OffsetPagination)
