"""Pagination configuration for Strapi API queries.

Strapi supports two pagination strategies:
1. Page-based: Use page number and page size
2. Offset-based: Use start offset and limit

IMPORTANT: Cannot mix pagination strategies in the same query.

Examples:
    Page-based pagination:
        >>> pagination = PagePagination(page=1, page_size=25)
        >>> pagination.to_query_dict()
        {'pagination[page]': 1, 'pagination[pageSize]': 25, 'pagination[withCount]': True}

    Offset-based pagination:
        >>> pagination = OffsetPagination(start=0, limit=25)
        >>> pagination.to_query_dict()
        {'pagination[start]': 0, 'pagination[limit]': 25, 'pagination[withCount]': True}

    Disable count (performance optimization):
        >>> pagination = PagePagination(page=1, page_size=100, with_count=False)
"""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class PagePagination(BaseModel):
    """Page-based pagination configuration.

    Uses page number and page size for pagination. This is the most
    user-friendly approach for displaying results across multiple pages.

    Attributes:
        page: Page number (1-indexed, must be >= 1)
        page_size: Number of items per page (must be between 1 and 100)
        with_count: Include total count in response (default: True)
    """

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=25, ge=1, le=100, description="Items per page")
    with_count: bool = Field(default=True, description="Include total count in response metadata")

    @field_validator("page")
    @classmethod
    def validate_page(cls, v: int) -> int:
        """Validate page number is positive.

        Args:
            v: Page number to validate

        Returns:
            Validated page number

        Raises:
            ValueError: If page number is less than 1
        """
        if v < 1:
            raise ValueError("Page number must be >= 1")
        return v

    @field_validator("page_size")
    @classmethod
    def validate_page_size(cls, v: int) -> int:
        """Validate page size is within allowed range.

        Args:
            v: Page size to validate

        Returns:
            Validated page size

        Raises:
            ValueError: If page size is out of range [1, 100]
        """
        if v < 1 or v > 100:
            raise ValueError("Page size must be between 1 and 100")
        return v

    def to_query_dict(self) -> dict[str, Any]:
        """Convert to query parameters dictionary.

        Returns:
            Dictionary with pagination parameters in Strapi format

        Examples:
            >>> PagePagination(page=2, page_size=50).to_query_dict()
            {'pagination[page]': 2, 'pagination[pageSize]': 50, 'pagination[withCount]': True}
        """
        return {
            "pagination[page]": self.page,
            "pagination[pageSize]": self.page_size,
            "pagination[withCount]": self.with_count,
        }


class OffsetPagination(BaseModel):
    """Offset-based pagination configuration.

    Uses start offset and limit for pagination. This approach is more
    flexible but requires manual calculation of offsets.

    Attributes:
        start: Starting offset (0-indexed, must be >= 0)
        limit: Maximum number of items to return (must be between 1 and 100)
        with_count: Include total count in response (default: True)
    """

    start: int = Field(default=0, ge=0, description="Starting offset (0-indexed)")
    limit: int = Field(default=25, ge=1, le=100, description="Maximum items to return")
    with_count: bool = Field(default=True, description="Include total count in response metadata")

    @field_validator("start")
    @classmethod
    def validate_start(cls, v: int) -> int:
        """Validate start offset is non-negative.

        Args:
            v: Start offset to validate

        Returns:
            Validated start offset

        Raises:
            ValueError: If start is negative
        """
        if v < 0:
            raise ValueError("Start offset must be >= 0")
        return v

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, v: int) -> int:
        """Validate limit is within allowed range.

        Args:
            v: Limit to validate

        Returns:
            Validated limit

        Raises:
            ValueError: If limit is out of range [1, 100]
        """
        if v < 1 or v > 100:
            raise ValueError("Limit must be between 1 and 100")
        return v

    def to_query_dict(self) -> dict[str, Any]:
        """Convert to query parameters dictionary.

        Returns:
            Dictionary with pagination parameters in Strapi format

        Examples:
            >>> OffsetPagination(start=50, limit=25).to_query_dict()
            {'pagination[start]': 50, 'pagination[limit]': 25, 'pagination[withCount]': True}
        """
        return {
            "pagination[start]": self.start,
            "pagination[limit]": self.limit,
            "pagination[withCount]": self.with_count,
        }


# Type alias for either pagination strategy
Pagination = PagePagination | OffsetPagination
