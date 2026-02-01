"""Sort configuration for Strapi API queries.

Provides models and builders for sorting query results by one or more fields.

Examples:
    Single field sort:
        >>> sort = Sort().by_field("publishedAt", SortDirection.DESC)
        >>> sort.to_query_list()
        ['publishedAt:desc']

    Multi-field sort:
        >>> sort = (Sort()
        ...     .by_field("status", SortDirection.ASC)
        ...     .then_by("publishedAt", SortDirection.DESC))
        >>> sort.to_query_list()
        ['status:asc', 'publishedAt:desc']

    Sort by nested relation:
        >>> sort = Sort().by_field("author.name", SortDirection.ASC)
        >>> sort.to_query_list()
        ['author.name:asc']
"""

from typing import Any

from pydantic import BaseModel, Field

from strapi_kit.models.enums import SortDirection


class SortField(BaseModel):
    """A single sort field with direction.

    Attributes:
        field: Field name (supports dot notation for relations, e.g., "author.name")
        direction: Sort direction (ASC or DESC)
    """

    field: str = Field(..., min_length=1, description="Field name to sort by")
    direction: SortDirection = Field(
        default=SortDirection.ASC, description="Sort direction (asc or desc)"
    )

    def to_string(self) -> str:
        """Convert to Strapi query string format.

        Returns:
            String in format "field:direction" (e.g., "publishedAt:desc")

        Examples:
            >>> SortField(field="publishedAt", direction=SortDirection.DESC).to_string()
            'publishedAt:desc'
        """
        return f"{self.field}:{self.direction.value}"


class Sort:
    """Fluent API for building multi-field sort configurations.

    Supports sorting by multiple fields with different directions.
    Fields are applied in the order they are added.

    Examples:
        >>> # Single field
        >>> sort = Sort().by_field("publishedAt", SortDirection.DESC)

        >>> # Multiple fields
        >>> sort = (Sort()
        ...     .by_field("status", SortDirection.ASC)
        ...     .then_by("publishedAt", SortDirection.DESC)
        ...     .then_by("title", SortDirection.ASC))

        >>> # Shorthand with default ASC
        >>> sort = Sort().by_field("title")  # Defaults to ASC
    """

    def __init__(self) -> None:
        """Initialize an empty sort builder."""
        self._fields: list[SortField] = []

    def by_field(self, field: str, direction: SortDirection = SortDirection.ASC) -> "Sort":
        """Add a sort field (first field or when starting a new sort).

        Args:
            field: Field name to sort by
            direction: Sort direction (default: ASC)

        Returns:
            Self for method chaining

        Examples:
            >>> Sort().by_field("publishedAt", SortDirection.DESC)
            >>> Sort().by_field("title")  # Defaults to ASC
        """
        self._fields.append(SortField(field=field, direction=direction))
        return self

    def then_by(self, field: str, direction: SortDirection = SortDirection.ASC) -> "Sort":
        """Add a secondary sort field (alias for by_field for readability).

        Args:
            field: Field name to sort by
            direction: Sort direction (default: ASC)

        Returns:
            Self for method chaining

        Examples:
            >>> (Sort()
            ...     .by_field("status")
            ...     .then_by("publishedAt", SortDirection.DESC))
        """
        return self.by_field(field, direction)

    def to_query_list(self) -> list[str]:
        """Convert sort configuration to list of query strings.

        Returns:
            List of strings in format "field:direction"

        Examples:
            >>> sort = Sort().by_field("publishedAt", SortDirection.DESC)
            >>> sort.to_query_list()
            ['publishedAt:desc']

            >>> sort = (Sort()
            ...     .by_field("status")
            ...     .then_by("publishedAt", SortDirection.DESC))
            >>> sort.to_query_list()
            ['status:asc', 'publishedAt:desc']
        """
        return [field.to_string() for field in self._fields]

    def to_query_dict(self) -> dict[str, Any]:
        """Convert sort configuration to dictionary format for query parameters.

        Returns:
            Dictionary with "sort" key containing list of sort strings

        Examples:
            >>> sort = Sort().by_field("publishedAt", SortDirection.DESC)
            >>> sort.to_query_dict()
            {'sort': ['publishedAt:desc']}
        """
        if not self._fields:
            return {}
        return {"sort": self.to_query_list()}
