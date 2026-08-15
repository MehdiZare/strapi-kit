"""Tests for pagination echo / maxLimit guard helper."""

import pytest

from strapi_kit import ValidationError, assert_pagination_echo
from strapi_kit.models import ResponseMeta
from strapi_kit.models.response.meta import PaginationMeta


class TestAssertPaginationEcho:
    """Tests for assert_pagination_echo."""

    def test_matching_echo_returns_total(self) -> None:
        """Matching page/pageSize echo returns total."""
        meta = {
            "pagination": {
                "page": 1,
                "pageSize": 25,
                "pageCount": 4,
                "total": 100,
            }
        }

        assert assert_pagination_echo(meta, requested_page=1, requested_page_size=25) == 100

    def test_matching_echo_from_response_meta(self) -> None:
        """ResponseMeta with matching echo returns total."""
        meta = ResponseMeta(
            pagination=PaginationMeta(page=2, page_size=50, page_count=3, total=120)
        )

        assert assert_pagination_echo(meta, requested_page=2, requested_page_size=50) == 120

    def test_digit_string_total_page_and_page_size(self) -> None:
        """Digit strings for total/page/pageSize parse as ints."""
        meta = {
            "pagination": {
                "page": "2",
                "pageSize": "50",
                "total": "12",
            }
        }

        assert assert_pagination_echo(meta, requested_page=2, requested_page_size=50) == 12

    def test_absent_page_keys_with_present_total(self) -> None:
        """Absent page/pageSize keys are tolerated when total is present."""
        meta = {"pagination": {"total": 7}}

        assert assert_pagination_echo(meta, requested_page=1, requested_page_size=25) == 7

    def test_mismatched_page_raises(self) -> None:
        """Present page echo must equal requested_page."""
        meta = {"pagination": {"page": 3, "pageSize": 25, "total": 10}}

        with pytest.raises(ValidationError, match="page echo") as exc_info:
            assert_pagination_echo(meta, requested_page=1, requested_page_size=25)

        assert exc_info.value.details["requested_page"] == 1
        assert exc_info.value.details["echo_page"] == 3

    def test_mismatched_page_size_raises(self) -> None:
        """Present pageSize echo must equal requested_page_size (maxLimit guard)."""
        meta = {"pagination": {"page": 1, "pageSize": 100, "total": 250}}

        with pytest.raises(ValidationError, match="pageSize echo") as exc_info:
            assert_pagination_echo(meta, requested_page=1, requested_page_size=250)

        assert exc_info.value.details["requested_page_size"] == 250
        assert exc_info.value.details["echo_page_size"] == 100

    def test_missing_total_raises(self) -> None:
        """total is required."""
        meta = {"pagination": {"page": 1, "pageSize": 25}}

        with pytest.raises(ValidationError, match="total is required"):
            assert_pagination_echo(meta, requested_page=1, requested_page_size=25)

    def test_bool_total_rejected(self) -> None:
        """bool is not an int, even though bool subclasses int."""
        meta = {"pagination": {"total": True}}

        with pytest.raises(ValidationError, match="total is unreadable"):
            assert_pagination_echo(meta, requested_page=1, requested_page_size=25)

    def test_abc_total_rejected(self) -> None:
        """Non-digit string total is unreadable."""
        meta = {"pagination": {"total": "abc"}}

        with pytest.raises(ValidationError, match="total is unreadable"):
            assert_pagination_echo(meta, requested_page=1, requested_page_size=25)

    def test_bool_page_rejected(self) -> None:
        """Present bool page is unreadable, not treated as 1."""
        meta = {"pagination": {"page": True, "total": 5}}

        with pytest.raises(ValidationError, match="page is unreadable"):
            assert_pagination_echo(meta, requested_page=1, requested_page_size=25)

    def test_abc_page_size_rejected(self) -> None:
        """Present non-digit pageSize is unreadable."""
        meta = {"pagination": {"pageSize": "abc", "total": 5}}

        with pytest.raises(ValidationError, match="pageSize is unreadable"):
            assert_pagination_echo(meta, requested_page=1, requested_page_size=25)

    def test_zero_total_is_valid(self) -> None:
        """total of 0 is a non-negative int."""
        meta = {"pagination": {"page": 1, "pageSize": 25, "total": 0}}

        assert assert_pagination_echo(meta, requested_page=1, requested_page_size=25) == 0

    def test_negative_int_total_rejected(self) -> None:
        """Integer -1 is readable but not a non-negative total."""
        meta = {"pagination": {"total": -1}}

        with pytest.raises(ValidationError, match="non-negative"):
            assert_pagination_echo(meta, requested_page=1, requested_page_size=25)

    def test_negative_string_total_rejected(self) -> None:
        """String '-1' is a readable negative, not unreadable."""
        meta = {"pagination": {"total": "-1"}}

        with pytest.raises(ValidationError, match="non-negative") as exc_info:
            assert_pagination_echo(meta, requested_page=1, requested_page_size=25)

        assert "unreadable" not in str(exc_info.value)

    def test_snake_case_page_size_matching(self) -> None:
        """Raw mappings may use page_size instead of pageSize."""
        meta = {"page": 1, "page_size": 25, "total": 8}

        assert assert_pagination_echo(meta, requested_page=1, requested_page_size=25) == 8

    def test_snake_case_page_size_mismatch(self) -> None:
        """Present snake_case page_size must equal requested_page_size."""
        meta = {"pagination": {"page": 1, "page_size": 100, "total": 250}}

        with pytest.raises(ValidationError, match="pageSize echo") as exc_info:
            assert_pagination_echo(meta, requested_page=1, requested_page_size=250)

        assert exc_info.value.details["echo_page_size"] == 100

    def test_pagination_meta_direct(self) -> None:
        """PaginationMeta is accepted as meta input."""
        pagination = PaginationMeta(page=1, page_size=10, total=3)

        assert assert_pagination_echo(pagination, requested_page=1, requested_page_size=10) == 3

    def test_public_exports(self) -> None:
        """Helper is exported from package, models, and utils."""
        from strapi_kit.models import assert_pagination_echo as from_models
        from strapi_kit.models.response import assert_pagination_echo as from_response
        from strapi_kit.utils import assert_pagination_echo as from_utils
        from strapi_kit.utils.pagination import assert_pagination_echo as from_module

        assert from_models is assert_pagination_echo
        assert from_response is assert_pagination_echo
        assert from_utils is assert_pagination_echo
        assert from_module is assert_pagination_echo
