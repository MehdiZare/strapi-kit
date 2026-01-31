"""Main query builder combining all request parameters.

The StrapiQuery class provides a fluent API for building complete Strapi API queries
with filters, sorting, pagination, population, and field selection.

Examples:
    Simple query:
        >>> query = (StrapiQuery()
        ...     .filter(FilterBuilder().eq("status", "published"))
        ...     .sort_by("publishedAt", SortDirection.DESC)
        ...     .paginate(page=1, page_size=25))

    Complex query with relations:
        >>> query = (StrapiQuery()
        ...     .filter(FilterBuilder()
        ...         .eq("status", "published")
        ...         .gt("views", 100))
        ...     .sort_by("views", SortDirection.DESC)
        ...     .paginate(page=1, page_size=10)
        ...     .populate_fields(["author", "category"])
        ...     .select(["title", "description", "publishedAt"]))

    Advanced query with nested population:
        >>> query = (StrapiQuery()
        ...     .filter(FilterBuilder().eq("featured", True))
        ...     .populate(Populate()
        ...         .add_field("author", fields=["name", "email"])
        ...         .add_field("comments",
        ...             filters=FilterBuilder().eq("approved", True),
        ...             sort=Sort().by_field("createdAt", SortDirection.DESC)))
        ...     .with_locale("fr"))
"""

from __future__ import annotations

from typing import Any

from py_strapi.models.enums import PublicationState, SortDirection
from py_strapi.models.request.fields import FieldSelection
from py_strapi.models.request.filters import FilterBuilder
from py_strapi.models.request.pagination import OffsetPagination, PagePagination, Pagination
from py_strapi.models.request.populate import Populate
from py_strapi.models.request.sort import Sort


def _flatten_dict(d: dict[str, Any], parent_key: str = "", sep: str = "") -> dict[str, Any]:
    """Flatten a nested dictionary into bracket notation for query parameters.

    Args:
        d: Dictionary to flatten
        parent_key: Parent key prefix
        sep: Separator (empty for bracket notation)

    Returns:
        Flattened dictionary with bracket notation keys

    Examples:
        >>> _flatten_dict({"status": {"$eq": "published"}}, "filters")
        {'filters[status][$eq]': 'published'}

        >>> _flatten_dict({"$or": [{"views": {"$gt": 100}}]}, "filters")
        {'filters[$or][0][views][$gt]': 100}
    """
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}[{k}]" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep).items())
        elif isinstance(v, list):
            # Check if list contains dicts (nested filters like $or, $and)
            if v and isinstance(v[0], dict):
                # Flatten each dict in the array with index
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        indexed_key = f"{new_key}[{i}]"
                        items.extend(_flatten_dict(item, indexed_key, sep).items())
                    else:
                        items.append((f"{new_key}[{i}]", item))
            else:
                # Simple list (e.g., $in values) - keep as-is for httpx
                items.append((new_key, v))
        else:
            items.append((new_key, v))
    return dict(items)


class StrapiQuery:
    """Main query builder for Strapi API requests.

    Combines filters, sorting, pagination, population, and field selection
    into a complete query configuration.

    Examples:
        >>> # Basic query
        >>> query = StrapiQuery().filter(FilterBuilder().eq("status", "published"))

        >>> # Complete query
        >>> query = (StrapiQuery()
        ...     .filter(FilterBuilder().eq("status", "published"))
        ...     .sort_by("publishedAt", SortDirection.DESC)
        ...     .paginate(page=1, page_size=25)
        ...     .populate_fields(["author", "category"])
        ...     .select(["title", "description"]))

        >>> # Convert to query parameters
        >>> params = query.to_query_params()
        >>> # params can be passed to httpx: client.get(url, params=params)
    """

    def __init__(self) -> None:
        """Initialize an empty query."""
        self._filters: FilterBuilder | None = None
        self._sort: Sort | None = None
        self._pagination: Pagination | None = None
        self._populate: Populate | None = None
        self._fields: FieldSelection | None = None
        self._locale: str | None = None
        self._publication_state: PublicationState | None = None

    def filter(self, filters: FilterBuilder) -> StrapiQuery:
        """Add filter conditions to the query.

        Args:
            filters: FilterBuilder with filter conditions

        Returns:
            Self for method chaining

        Examples:
            >>> query = StrapiQuery().filter(
            ...     FilterBuilder()
            ...         .eq("status", "published")
            ...         .gt("views", 100)
            ... )
        """
        self._filters = filters
        return self

    def sort_by(self, field: str, direction: SortDirection = SortDirection.ASC) -> StrapiQuery:
        """Add sorting to the query.

        Args:
            field: Field name to sort by
            direction: Sort direction (default: ASC)

        Returns:
            Self for method chaining

        Examples:
            >>> query = StrapiQuery().sort_by("publishedAt", SortDirection.DESC)
        """
        if self._sort is None:
            self._sort = Sort()
        self._sort.by_field(field, direction)
        return self

    def then_sort_by(self, field: str, direction: SortDirection = SortDirection.ASC) -> StrapiQuery:
        """Add secondary sort field (alias for sort_by for readability).

        Args:
            field: Field name to sort by
            direction: Sort direction (default: ASC)

        Returns:
            Self for method chaining

        Examples:
            >>> query = (StrapiQuery()
            ...     .sort_by("status")
            ...     .then_sort_by("publishedAt", SortDirection.DESC))
        """
        return self.sort_by(field, direction)

    def paginate(
        self,
        page: int | None = None,
        page_size: int | None = None,
        start: int | None = None,
        limit: int | None = None,
        with_count: bool = True,
    ) -> StrapiQuery:
        """Add pagination to the query.

        Use either page-based (page + page_size) OR offset-based (start + limit).
        Cannot mix both strategies.

        Args:
            page: Page number (1-indexed) for page-based pagination
            page_size: Items per page for page-based pagination
            start: Start offset (0-indexed) for offset-based pagination
            limit: Maximum items for offset-based pagination
            with_count: Include total count in response (default: True)

        Returns:
            Self for method chaining

        Raises:
            ValueError: If mixing page-based and offset-based parameters

        Examples:
            >>> # Page-based
            >>> query = StrapiQuery().paginate(page=1, page_size=25)

            >>> # Offset-based
            >>> query = StrapiQuery().paginate(start=0, limit=25)
        """
        # Detect pagination strategy
        page_based = page is not None or page_size is not None
        offset_based = start is not None or limit is not None

        if page_based and offset_based:
            raise ValueError("Cannot mix page-based and offset-based pagination")

        if page_based:
            self._pagination = PagePagination(
                page=page or 1, page_size=page_size or 25, with_count=with_count
            )
        elif offset_based:
            self._pagination = OffsetPagination(
                start=start or 0, limit=limit or 25, with_count=with_count
            )

        return self

    def populate(self, populate: Populate) -> StrapiQuery:
        """Add population configuration to the query.

        Args:
            populate: Populate configuration

        Returns:
            Self for method chaining

        Examples:
            >>> query = StrapiQuery().populate(
            ...     Populate()
            ...         .add_field("author", fields=["name", "email"])
            ...         .add_field("category")
            ... )
        """
        self._populate = populate
        return self

    def populate_all(self) -> StrapiQuery:
        """Populate all first-level relations.

        Returns:
            Self for method chaining

        Examples:
            >>> query = StrapiQuery().populate_all()
        """
        self._populate = Populate().all()
        return self

    def populate_fields(self, fields: list[str]) -> StrapiQuery:
        """Populate specific fields (simple list).

        Args:
            fields: List of field names to populate

        Returns:
            Self for method chaining

        Examples:
            >>> query = StrapiQuery().populate_fields(["author", "category", "tags"])
        """
        self._populate = Populate().fields_list(fields)
        return self

    def select(self, fields: list[str]) -> StrapiQuery:
        """Select specific fields to return.

        Args:
            fields: List of field names to include in response

        Returns:
            Self for method chaining

        Examples:
            >>> query = StrapiQuery().select(["title", "description", "publishedAt"])
        """
        self._fields = FieldSelection(fields=fields)
        return self

    def with_locale(self, locale: str) -> StrapiQuery:
        """Set locale for i18n content.

        Args:
            locale: Locale code (e.g., "en", "fr", "de")

        Returns:
            Self for method chaining

        Examples:
            >>> query = StrapiQuery().with_locale("fr")
        """
        self._locale = locale
        return self

    def with_publication_state(self, state: PublicationState) -> StrapiQuery:
        """Set publication state filter (draft & publish).

        Args:
            state: Publication state (LIVE or PREVIEW)

        Returns:
            Self for method chaining

        Examples:
            >>> query = StrapiQuery().with_publication_state(PublicationState.LIVE)
        """
        self._publication_state = state
        return self

    def to_query_params(self) -> dict[str, Any]:
        """Convert query to flat dictionary for HTTP query parameters.

        Returns:
            Dictionary of query parameters ready for httpx

        Examples:
            >>> query = (StrapiQuery()
            ...     .filter(FilterBuilder().eq("status", "published"))
            ...     .sort_by("publishedAt", SortDirection.DESC)
            ...     .paginate(page=1, page_size=10))
            >>> params = query.to_query_params()
            >>> # Use with httpx: client.get(url, params=params)
        """
        params: dict[str, Any] = {}

        # Add filters (flattened to bracket notation for Strapi)
        if self._filters:
            filter_dict = self._filters.to_query_dict()
            if filter_dict:
                # Flatten nested filter dict into bracket notation
                # e.g., {"status": {"$eq": "published"}} -> {"filters[status][$eq]": "published"}
                flattened = _flatten_dict(filter_dict, "filters")
                params.update(flattened)

        # Add sort
        if self._sort:
            sort_list = self._sort.to_query_list()
            if sort_list:
                params["sort"] = sort_list

        # Add pagination
        if self._pagination:
            pagination_dict = self._pagination.to_query_dict()
            params.update(pagination_dict)

        # Add populate
        if self._populate:
            populate_dict = self._populate.to_query_dict()
            if populate_dict:
                params.update(populate_dict)

        # Add fields
        if self._fields:
            fields_dict = self._fields.to_query_dict()
            if fields_dict:
                params.update(fields_dict)

        # Add locale
        if self._locale:
            params["locale"] = self._locale

        # Add publication state
        if self._publication_state:
            params["publicationState"] = self._publication_state.value

        return params

    def to_query_dict(self) -> dict[str, Any]:
        """Convert query to nested dictionary structure.

        This is an alias for to_query_params() for consistency with other models.

        Returns:
            Dictionary of query parameters

        Examples:
            >>> query = StrapiQuery().filter(FilterBuilder().eq("status", "published"))
            >>> query.to_query_dict()
            {'filters': {'status': {'$eq': 'published'}}}
        """
        return self.to_query_params()
