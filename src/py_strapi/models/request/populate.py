"""Population (relation expansion) for Strapi API queries.

Strapi supports populating (expanding) relations, components, and dynamic zones.
This module provides a fluent API for building complex population configurations.

Examples:
    Simple population:
        >>> populate = Populate().fields_list(["author", "category"])
        >>> populate.to_query_dict()
        {'populate': ['author', 'category']}

    Populate all relations:
        >>> populate = Populate().all()
        >>> populate.to_query_dict()
        {'populate': '*'}

    Nested population with filtering:
        >>> from py_strapi.models.request.filters import FilterBuilder
        >>> populate = Populate().add_field(
        ...     "author",
        ...     fields=["name", "email"],
        ...     filters=FilterBuilder().eq("active", True)
        ... )
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from py_strapi.models.request.filters import FilterBuilder
from py_strapi.models.request.sort import Sort


class PopulateField(BaseModel):
    """Configuration for populating a single field.

    Attributes:
        field: Field name to populate
        nested: Nested population configuration
        filters: Filter conditions for the populated data
        fields: Specific fields to select from the relation
        sort: Sort configuration for the populated data
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    field: str = Field(..., min_length=1, description="Field name to populate")
    nested: Populate | None = Field(None, description="Nested population")
    filters: FilterBuilder | None = Field(None, description="Filter populated data")
    fields: list[str] | None = Field(None, description="Fields to select")
    sort: Sort | None = Field(None, description="Sort configuration")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for query parameters.

        Returns:
            Dictionary with field name as key and configuration as value

        Examples:
            >>> # Simple populate
            >>> pf = PopulateField(field="author")
            >>> pf.to_dict()
            {'author': {'populate': '*'}}

            >>> # With field selection
            >>> pf = PopulateField(field="author", fields=["name", "email"])
            >>> pf.to_dict()
            {'author': {'fields': ['name', 'email'], 'populate': '*'}}
        """
        config: dict[str, Any] = {}

        # Add field selection
        if self.fields:
            config["fields"] = self.fields

        # Add filters
        if self.filters:
            filter_dict = self.filters.to_query_dict()
            if filter_dict:
                config["filters"] = filter_dict

        # Add sort
        if self.sort:
            sort_list = self.sort.to_query_list()
            if sort_list:
                config["sort"] = sort_list

        # Add nested population
        if self.nested:
            nested_dict = self.nested.to_query_dict()
            if "populate" in nested_dict:
                config["populate"] = nested_dict["populate"]
        else:
            # Default: populate all fields of this relation
            config["populate"] = "*"

        return {self.field: config}


class Populate:
    """Fluent API for building population configurations.

    Strapi population allows expanding relations, components, and dynamic zones.
    This class provides methods to configure simple and complex population scenarios.

    Examples:
        >>> # Populate all relations
        >>> populate = Populate().all()

        >>> # Populate specific fields
        >>> populate = Populate().fields_list(["author", "category"])

        >>> # Populate with nested relations
        >>> populate = (Populate()
        ...     .add_field("author")
        ...     .add_field("posts", nested=Populate().add_field("comments")))

        >>> # Populate with filtering
        >>> populate = Populate().add_field(
        ...     "author",
        ...     filters=FilterBuilder().eq("active", True),
        ...     fields=["name", "email"]
        ... )
    """

    def __init__(self) -> None:
        """Initialize an empty populate configuration."""
        self._populate_all: bool = False
        self._fields: list[PopulateField] = []

    def all(self) -> Populate:
        """Populate all first-level relations.

        Returns:
            Self for method chaining

        Examples:
            >>> populate = Populate().all()
            >>> populate.to_query_dict()
            {'populate': '*'}
        """
        self._populate_all = True
        return self

    def fields_list(self, fields: list[str]) -> Populate:
        """Populate specific fields (simple list).

        Args:
            fields: List of field names to populate

        Returns:
            Self for method chaining

        Examples:
            >>> populate = Populate().fields_list(["author", "category", "tags"])
            >>> populate.to_query_dict()
            {'populate': ['author', 'category', 'tags']}
        """
        # Convert simple field names to PopulateField objects
        for field_name in fields:
            self._fields.append(
                PopulateField(field=field_name, nested=None, filters=None, fields=None, sort=None)
            )
        return self

    def add_field(
        self,
        field: str,
        nested: Populate | None = None,
        filters: FilterBuilder | None = None,
        fields: list[str] | None = None,
        sort: Sort | None = None,
    ) -> Populate:
        """Add a field to populate with advanced configuration.

        Args:
            field: Field name to populate
            nested: Nested population configuration
            filters: Filter conditions for the populated data
            fields: Specific fields to select from the relation
            sort: Sort configuration for the populated data

        Returns:
            Self for method chaining

        Examples:
            >>> # Simple field
            >>> populate = Populate().add_field("author")

            >>> # With field selection
            >>> populate = Populate().add_field("author", fields=["name", "email"])

            >>> # With filtering
            >>> populate = Populate().add_field(
            ...     "comments",
            ...     filters=FilterBuilder().eq("approved", True),
            ...     sort=Sort().by_field("createdAt", SortDirection.DESC)
            ... )

            >>> # Nested population
            >>> populate = Populate().add_field(
            ...     "author",
            ...     nested=Populate().add_field("profile")
            ... )
        """
        self._fields.append(
            PopulateField(field=field, nested=nested, filters=filters, fields=fields, sort=sort)
        )
        return self

    def to_query_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for query parameters.

        Returns:
            Dictionary with 'populate' key

        Examples:
            >>> # Populate all
            >>> Populate().all().to_query_dict()
            {'populate': '*'}

            >>> # Simple list
            >>> Populate().fields_list(["author", "category"]).to_query_dict()
            {'populate': ['author', 'category']}

            >>> # Complex with configuration
            >>> populate = Populate().add_field("author", fields=["name"])
            >>> # Returns nested structure
        """
        if not self._populate_all and not self._fields:
            return {}

        # Populate all
        if self._populate_all:
            return {"populate": "*"}

        # Check if all fields are simple (no config)
        all_simple = all(
            not f.nested and not f.filters and not f.fields and not f.sort for f in self._fields
        )

        if all_simple:
            # Simple array format
            return {"populate": [f.field for f in self._fields]}

        # Complex object format
        result: dict[str, Any] = {}
        for field_config in self._fields:
            field_dict = field_config.to_dict()
            result.update(field_dict)

        return {"populate": result}
