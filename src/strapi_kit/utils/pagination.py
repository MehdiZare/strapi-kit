"""Pagination echo / maxLimit guard.

Re-exports :func:`strapi_kit.models.response.pagination.assert_pagination_echo`
so callers can import from ``strapi_kit.utils.pagination``.
"""

from strapi_kit.models.response.pagination import assert_pagination_echo

__all__ = ["assert_pagination_echo"]
