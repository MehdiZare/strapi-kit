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

import copy
from typing import Any

from strapi_kit.exceptions import ValidationError
from strapi_kit.models.enums import (
    DocumentStatus,
    PublicationFilter,
    PublicationState,
    QueryParam,
    SortDirection,
)
from strapi_kit.models.request.fields import FieldSelection
from strapi_kit.models.request.filters import FilterBuilder
from strapi_kit.models.request.pagination import OffsetPagination, PagePagination, Pagination
from strapi_kit.models.request.populate import Populate
from strapi_kit.models.request.sort import Sort


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
        self._document_status: DocumentStatus | None = None
        self._publication_filter: PublicationFilter | None = None

    def copy(self) -> StrapiQuery:
        """Create a deep copy of this query.

        Useful for modifying a query without affecting the original,
        especially in streaming operations that modify pagination.

        Returns:
            Deep copy of this query

        Examples:
            >>> base_query = StrapiQuery().filter(FilterBuilder().eq("status", "published"))
            >>> modified = base_query.copy().paginate(page=2)
            >>> # base_query is unchanged
        """
        new_query = StrapiQuery()
        new_query._filters = copy.deepcopy(self._filters)
        new_query._sort = copy.deepcopy(self._sort)
        new_query._pagination = copy.deepcopy(self._pagination)
        new_query._populate = copy.deepcopy(self._populate)
        new_query._fields = copy.deepcopy(self._fields)
        new_query._locale = self._locale
        new_query._publication_state = self._publication_state
        new_query._document_status = self._document_status
        new_query._publication_filter = self._publication_filter
        return new_query

    def filter(self, filters: FilterBuilder) -> StrapiQuery:
        """Add filter conditions to the query.

        Args:
            filters: FilterBuilder with filter conditions

        Returns:
            Self for method chaining

        Raises:
            ValidationError: If ``filters`` is not a :class:`FilterBuilder`
                instance (for example a raw dict)

        Examples:
            >>> query = StrapiQuery().filter(
            ...     FilterBuilder()
            ...         .eq("status", "published")
            ...         .gt("views", 100)
            ... )
        """
        if not isinstance(filters, FilterBuilder):
            raise ValidationError(
                "filter() expected a FilterBuilder instance, "
                f"got {type(filters).__name__}. "
                "Use filter(FilterBuilder().eq(...))."
            )
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
            strapi_kit.exceptions.ValidationError: If mixing page-based and
                offset-based parameters, or if pagination values are invalid
                (page < 1, page_size < 1, start < 0, limit < 1)

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
            raise ValidationError("Cannot mix page-based and offset-based pagination")

        if page_based:
            # Validate page value if explicitly provided
            if page is not None and page < 1:
                raise ValidationError("page must be >= 1")
            # Validate page_size value if explicitly provided
            if page_size is not None and page_size < 1:
                raise ValidationError("page_size must be >= 1")
            self._pagination = PagePagination(
                page=1 if page is None else page,
                page_size=25 if page_size is None else page_size,
                with_count=with_count,
            )
        elif offset_based:
            # Validate start value if explicitly provided
            if start is not None and start < 0:
                raise ValidationError("start must be >= 0")
            # Validate limit value if explicitly provided
            if limit is not None and limit < 1:
                raise ValidationError("limit must be >= 1")
            self._pagination = OffsetPagination(
                start=0 if start is None else start,
                limit=25 if limit is None else limit,
                with_count=with_count,
            )

        return self

    def populate(self, populate: Populate) -> StrapiQuery:
        """Add population configuration to the query.

        Args:
            populate: Populate configuration

        Returns:
            Self for method chaining

        Raises:
            ValidationError: If ``populate`` is not a :class:`Populate`
                instance (for example a comma-separated string)

        Examples:
            >>> query = StrapiQuery().populate(
            ...     Populate()
            ...         .add_field("author", fields=["name", "email"])
            ...         .add_field("category")
            ... )
        """
        if not isinstance(populate, Populate):
            raise ValidationError(
                "populate() expected a Populate instance, "
                f"got {type(populate).__name__}. "
                "Use populate_all(), populate_fields([...]), "
                "or populate(Populate().add_field(...))."
            )
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
        """Set the v4 ``publicationState`` filter (draft & publish).

        Do not combine with :meth:`with_document_status` or
        :meth:`with_publication_filter` — those emit v5 params instead.

        Args:
            state: Publication state (LIVE or PREVIEW)

        Returns:
            Self for method chaining

        Raises:
            ValidationError: If a v5 Draft & Publish param was already set

        Examples:
            >>> query = StrapiQuery().with_publication_state(PublicationState.LIVE)
        """
        if self._document_status is not None or self._publication_filter is not None:
            raise ValidationError(
                "Cannot mix with_document_status / with_publication_filter "
                "(v5) and with_publication_state (v4 publicationState=)"
            )
        self._publication_state = state
        return self

    def with_document_status(self, status: DocumentStatus) -> StrapiQuery:
        """Set the v5 ``status`` filter (Draft & Publish).

        Strapi 5 defaults omitted ``status`` to published, which hides
        unpublished documents. Use ``DocumentStatus.DRAFT`` to see every
        document (each has a draft version sharing one ``documentId``).

        Do not combine with :meth:`with_publication_state`.

        Args:
            status: Document status (DRAFT or PUBLISHED)

        Returns:
            Self for method chaining

        Raises:
            ValidationError: If :meth:`with_publication_state` was already set

        Examples:
            >>> query = StrapiQuery().with_document_status(DocumentStatus.DRAFT)
        """
        if self._publication_state is not None:
            raise ValidationError(
                "Cannot mix with_document_status (v5 status=) and "
                "with_publication_state (v4 publicationState=)"
            )
        self._document_status = status
        return self

    def with_publication_filter(self, publication_filter: PublicationFilter) -> StrapiQuery:
        """Set the v5 ``publicationFilter`` (draft/published relationship).

        Selects documents by how their draft and published versions relate
        (never published, modified since last publish, and so on). Combine
        with :meth:`with_document_status` to choose which version is
        returned. Pairings that cannot exist (for example
        ``never-published`` with ``status=published``) return an empty
        list from Strapi rather than an error.

        Do not combine with :meth:`with_publication_state`.

        Args:
            publication_filter: Relationship filter

        Returns:
            Self for method chaining

        Raises:
            ValidationError: If :meth:`with_publication_state` was already set

        Examples:
            >>> query = (StrapiQuery()
            ...     .with_document_status(DocumentStatus.DRAFT)
            ...     .with_publication_filter(PublicationFilter.NEVER_PUBLISHED))
        """
        if self._publication_state is not None:
            raise ValidationError(
                "Cannot mix with_publication_filter (v5 publicationFilter=) "
                "and with_publication_state (v4 publicationState=)"
            )
        self._publication_filter = publication_filter
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
            params[QueryParam.LOCALE] = self._locale

        # Add publication state (v4) or document status / filter (v5)
        if self._publication_state:
            params[QueryParam.PUBLICATION_STATE] = self._publication_state.value
        if self._document_status:
            params[QueryParam.STATUS] = self._document_status.value
        if self._publication_filter:
            params[QueryParam.PUBLICATION_FILTER] = self._publication_filter.value

        return params

    def to_query_dict(self) -> dict[str, Any]:
        """Convert query to flattened dictionary for HTTP query parameters.

        This is an alias for to_query_params() for consistency with other models.
        Returns bracket-notation flattened params ready for httpx.

        Returns:
            Dictionary of query parameters (flattened bracket notation)

        Examples:
            >>> query = StrapiQuery().filter(FilterBuilder().eq("status", "published"))
            >>> query.to_query_dict()
            {'filters[status][$eq]': 'published'}
        """
        return self.to_query_params()
