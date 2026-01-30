"""Filter builder for Strapi API queries.

Provides a fluent API for constructing complex filters with:
- 24 filter operators (eq, gt, contains, etc.)
- Logical operators (AND, OR, NOT)
- Deep filtering on relations
- Nested filter groups

Examples:
    Simple filter:
        >>> filter_builder = FilterBuilder().eq("status", "published")
        >>> filter_builder.to_query_dict()
        {'status': {'$eq': 'published'}}

    Complex filter with logical operators:
        >>> filter_builder = (FilterBuilder()
        ...     .eq("status", "published")
        ...     .gt("views", 100)
        ...     .or_group(
        ...         FilterBuilder().contains("title", "Python"),
        ...         FilterBuilder().contains("title", "Django")
        ...     ))

    Deep filtering on relations:
        >>> filter_builder = FilterBuilder().eq("author.name", "John Doe")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from py_strapi.models.enums import FilterOperator

if TYPE_CHECKING:
    pass


class FilterCondition(BaseModel):
    """A single filter condition.

    Represents a field-operator-value triple like "status = published".

    Attributes:
        field: Field name (supports dot notation for relations, e.g., "author.name")
        operator: Filter operator from FilterOperator enum
        value: Value to filter against (type depends on operator)
    """

    field: str = Field(..., min_length=1, description="Field name to filter on")
    operator: FilterOperator = Field(..., description="Filter operator")
    value: Any = Field(..., description="Value to compare against")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for query parameters.

        Returns:
            Dictionary with nested structure for field path and operator.

        Examples:
            >>> FilterCondition(field="status", operator=FilterOperator.EQ, value="published").to_dict()
            {'status': {'$eq': 'published'}}

            >>> FilterCondition(field="author.name", operator=FilterOperator.EQ, value="John").to_dict()
            {'author': {'name': {'$eq': 'John'}}}
        """
        # Handle dot notation for nested fields (e.g., "author.name")
        parts = self.field.split(".")
        result: dict[str, Any] = {self.operator.value: self.value}

        # Build nested dictionary from right to left
        for part in reversed(parts):
            result = {part: result}

        return result


class FilterGroup(BaseModel):
    """A group of filter conditions combined with logical operators.

    Supports AND, OR, and NOT logical operators for combining conditions.

    Attributes:
        conditions: List of filter conditions
        logical_operator: Logical operator combining conditions (default: AND)
    """

    conditions: list[FilterCondition | FilterGroup] = Field(
        default_factory=list, description="Filter conditions or nested groups"
    )
    logical_operator: FilterOperator | None = Field(
        None, description="Logical operator (AND, OR, NOT)"
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for query parameters.

        Returns:
            Dictionary with conditions merged or wrapped in logical operator.

        Examples:
            >>> # Simple AND (default)
            >>> group = FilterGroup(conditions=[
            ...     FilterCondition(field="status", operator=FilterOperator.EQ, value="published")
            ... ])
            >>> group.to_dict()
            {'status': {'$eq': 'published'}}

            >>> # Explicit OR
            >>> group = FilterGroup(
            ...     conditions=[
            ...         FilterCondition(field="views", operator=FilterOperator.GT, value=100),
            ...         FilterCondition(field="likes", operator=FilterOperator.GT, value=50)
            ...     ],
            ...     logical_operator=FilterOperator.OR
            ... )
            >>> group.to_dict()
            {'$or': [{'views': {'$gt': 100}}, {'likes': {'$gt': 50}}]}
        """
        if not self.conditions:
            return {}

        # Convert all conditions to dictionaries
        condition_dicts = [
            cond.to_dict() if isinstance(cond, FilterCondition) else cond.to_dict()
            for cond in self.conditions
        ]

        # If no logical operator, merge dictionaries (implicit AND)
        if self.logical_operator is None:
            result: dict[str, Any] = {}
            for cond_dict in condition_dicts:
                # Deep merge dictionaries
                self._deep_merge(result, cond_dict)
            return result

        # Wrap in logical operator (OR, AND, NOT)
        return {self.logical_operator.value: condition_dicts}

    @staticmethod
    def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> None:
        """Deep merge source dictionary into target dictionary.

        Args:
            target: Target dictionary to merge into (modified in place)
            source: Source dictionary to merge from
        """
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                FilterGroup._deep_merge(target[key], value)
            else:
                target[key] = value


class FilterBuilder:
    """Fluent API for building Strapi filters.

    Provides chainable methods for all 24 Strapi filter operators plus
    logical grouping with AND/OR/NOT.

    Examples:
        >>> # Simple filter
        >>> builder = FilterBuilder().eq("status", "published")

        >>> # Chained filters (implicit AND)
        >>> builder = (FilterBuilder()
        ...     .eq("status", "published")
        ...     .gt("views", 100)
        ...     .contains("title", "Python"))

        >>> # OR group
        >>> builder = FilterBuilder().or_group(
        ...     FilterBuilder().eq("category", "tech"),
        ...     FilterBuilder().eq("category", "science")
        ... )

        >>> # Complex nested filters
        >>> builder = (FilterBuilder()
        ...     .eq("status", "published")
        ...     .or_group(
        ...         FilterBuilder().gt("views", 1000),
        ...         FilterBuilder().gt("likes", 500)
        ...     ))
    """

    def __init__(self) -> None:
        """Initialize an empty filter builder."""
        self._conditions: list[FilterCondition | FilterGroup] = []

    def _add_condition(self, field: str, operator: FilterOperator, value: Any) -> FilterBuilder:
        """Add a filter condition to the builder.

        Args:
            field: Field name to filter on
            operator: Filter operator
            value: Value to compare against

        Returns:
            Self for method chaining
        """
        self._conditions.append(FilterCondition(field=field, operator=operator, value=value))
        return self

    # Equality operators
    def eq(self, field: str, value: Any) -> FilterBuilder:
        """Equal to (case-sensitive).

        Args:
            field: Field name
            value: Value to match

        Returns:
            Self for chaining

        Examples:
            >>> FilterBuilder().eq("status", "published")
        """
        return self._add_condition(field, FilterOperator.EQ, value)

    def eqi(self, field: str, value: str) -> FilterBuilder:
        """Equal to (case-insensitive).

        Args:
            field: Field name
            value: String value to match

        Returns:
            Self for chaining

        Examples:
            >>> FilterBuilder().eqi("status", "PUBLISHED")
        """
        return self._add_condition(field, FilterOperator.EQI, value)

    def ne(self, field: str, value: Any) -> FilterBuilder:
        """Not equal to (case-sensitive).

        Args:
            field: Field name
            value: Value to exclude

        Returns:
            Self for chaining
        """
        return self._add_condition(field, FilterOperator.NE, value)

    def nei(self, field: str, value: str) -> FilterBuilder:
        """Not equal to (case-insensitive).

        Args:
            field: Field name
            value: String value to exclude

        Returns:
            Self for chaining
        """
        return self._add_condition(field, FilterOperator.NEI, value)

    # Comparison operators
    def lt(self, field: str, value: Any) -> FilterBuilder:
        """Less than.

        Args:
            field: Field name
            value: Upper bound (exclusive)

        Returns:
            Self for chaining

        Examples:
            >>> FilterBuilder().lt("price", 100)
        """
        return self._add_condition(field, FilterOperator.LT, value)

    def lte(self, field: str, value: Any) -> FilterBuilder:
        """Less than or equal to.

        Args:
            field: Field name
            value: Upper bound (inclusive)

        Returns:
            Self for chaining
        """
        return self._add_condition(field, FilterOperator.LTE, value)

    def gt(self, field: str, value: Any) -> FilterBuilder:
        """Greater than.

        Args:
            field: Field name
            value: Lower bound (exclusive)

        Returns:
            Self for chaining

        Examples:
            >>> FilterBuilder().gt("views", 1000)
        """
        return self._add_condition(field, FilterOperator.GT, value)

    def gte(self, field: str, value: Any) -> FilterBuilder:
        """Greater than or equal to.

        Args:
            field: Field name
            value: Lower bound (inclusive)

        Returns:
            Self for chaining
        """
        return self._add_condition(field, FilterOperator.GTE, value)

    # String matching operators
    def contains(self, field: str, value: str) -> FilterBuilder:
        """Contains substring (case-sensitive).

        Args:
            field: Field name
            value: Substring to search for

        Returns:
            Self for chaining

        Examples:
            >>> FilterBuilder().contains("title", "Python")
        """
        return self._add_condition(field, FilterOperator.CONTAINS, value)

    def not_contains(self, field: str, value: str) -> FilterBuilder:
        """Does not contain substring (case-sensitive).

        Args:
            field: Field name
            value: Substring to exclude

        Returns:
            Self for chaining
        """
        return self._add_condition(field, FilterOperator.NOT_CONTAINS, value)

    def containsi(self, field: str, value: str) -> FilterBuilder:
        """Contains substring (case-insensitive).

        Args:
            field: Field name
            value: Substring to search for

        Returns:
            Self for chaining
        """
        return self._add_condition(field, FilterOperator.CONTAINSI, value)

    def not_containsi(self, field: str, value: str) -> FilterBuilder:
        """Does not contain substring (case-insensitive).

        Args:
            field: Field name
            value: Substring to exclude

        Returns:
            Self for chaining
        """
        return self._add_condition(field, FilterOperator.NOT_CONTAINSI, value)

    def starts_with(self, field: str, value: str) -> FilterBuilder:
        """Starts with string (case-sensitive).

        Args:
            field: Field name
            value: Prefix to match

        Returns:
            Self for chaining
        """
        return self._add_condition(field, FilterOperator.STARTS_WITH, value)

    def starts_withi(self, field: str, value: str) -> FilterBuilder:
        """Starts with string (case-insensitive).

        Args:
            field: Field name
            value: Prefix to match

        Returns:
            Self for chaining
        """
        return self._add_condition(field, FilterOperator.STARTS_WITHI, value)

    def ends_with(self, field: str, value: str) -> FilterBuilder:
        """Ends with string (case-sensitive).

        Args:
            field: Field name
            value: Suffix to match

        Returns:
            Self for chaining
        """
        return self._add_condition(field, FilterOperator.ENDS_WITH, value)

    def ends_withi(self, field: str, value: str) -> FilterBuilder:
        """Ends with string (case-insensitive).

        Args:
            field: Field name
            value: Suffix to match

        Returns:
            Self for chaining
        """
        return self._add_condition(field, FilterOperator.ENDS_WITHI, value)

    # Array operators
    def in_(self, field: str, values: list[Any]) -> FilterBuilder:
        """Value is in array.

        Args:
            field: Field name
            values: List of acceptable values

        Returns:
            Self for chaining

        Examples:
            >>> FilterBuilder().in_("status", ["published", "draft"])
        """
        return self._add_condition(field, FilterOperator.IN, values)

    def not_in(self, field: str, values: list[Any]) -> FilterBuilder:
        """Value is not in array.

        Args:
            field: Field name
            values: List of values to exclude

        Returns:
            Self for chaining
        """
        return self._add_condition(field, FilterOperator.NOT_IN, values)

    # Null operators
    def null(self, field: str, is_null: bool = True) -> FilterBuilder:
        """Value is null.

        Args:
            field: Field name
            is_null: True to match null, False to match not null

        Returns:
            Self for chaining

        Examples:
            >>> FilterBuilder().null("deletedAt")  # Match null values
            >>> FilterBuilder().null("deletedAt", False)  # Match non-null values
        """
        return self._add_condition(field, FilterOperator.NULL, is_null)

    def not_null(self, field: str) -> FilterBuilder:
        """Value is not null.

        Args:
            field: Field name

        Returns:
            Self for chaining
        """
        return self._add_condition(field, FilterOperator.NOT_NULL, True)

    # Range operators
    def between(self, field: str, start: Any, end: Any) -> FilterBuilder:
        """Value is between start and end (inclusive).

        Args:
            field: Field name
            start: Lower bound
            end: Upper bound

        Returns:
            Self for chaining

        Examples:
            >>> FilterBuilder().between("price", 10, 100)
            >>> FilterBuilder().between("publishedAt", "2024-01-01", "2024-12-31")
        """
        return self._add_condition(field, FilterOperator.BETWEEN, [start, end])

    # Logical operators
    def and_group(self, *builders: FilterBuilder) -> FilterBuilder:
        """Create an AND group of filters.

        Args:
            *builders: FilterBuilder instances to combine with AND

        Returns:
            Self for chaining

        Examples:
            >>> FilterBuilder().and_group(
            ...     FilterBuilder().eq("status", "published"),
            ...     FilterBuilder().gt("views", 100)
            ... )
        """
        conditions = []
        for builder in builders:
            conditions.extend(builder._conditions)

        group = FilterGroup(conditions=conditions, logical_operator=FilterOperator.AND)
        self._conditions.append(group)
        return self

    def or_group(self, *builders: FilterBuilder) -> FilterBuilder:
        """Create an OR group of filters.

        Args:
            *builders: FilterBuilder instances to combine with OR

        Returns:
            Self for chaining

        Examples:
            >>> FilterBuilder().or_group(
            ...     FilterBuilder().eq("category", "tech"),
            ...     FilterBuilder().eq("category", "science")
            ... )
        """
        conditions = []
        for builder in builders:
            conditions.extend(builder._conditions)

        group = FilterGroup(conditions=conditions, logical_operator=FilterOperator.OR)
        self._conditions.append(group)
        return self

    def not_group(self, builder: FilterBuilder) -> FilterBuilder:
        """Create a NOT group (negation).

        Args:
            builder: FilterBuilder instance to negate

        Returns:
            Self for chaining

        Examples:
            >>> FilterBuilder().not_group(
            ...     FilterBuilder().eq("status", "draft")
            ... )
        """
        group = FilterGroup(conditions=builder._conditions, logical_operator=FilterOperator.NOT)
        self._conditions.append(group)
        return self

    def to_query_dict(self) -> dict[str, Any]:
        """Convert filter builder to dictionary format for query parameters.

        Returns:
            Dictionary with nested filter structure

        Examples:
            >>> builder = FilterBuilder().eq("status", "published").gt("views", 100)
            >>> builder.to_query_dict()
            {'status': {'$eq': 'published'}, 'views': {'$gt': 100}}
        """
        if not self._conditions:
            return {}

        # If single condition, return it directly
        if len(self._conditions) == 1:
            cond = self._conditions[0]
            return cond.to_dict() if isinstance(cond, FilterCondition) else cond.to_dict()

        # Multiple conditions - wrap in implicit AND
        group = FilterGroup(conditions=self._conditions, logical_operator=None)
        return group.to_dict()


# Rebuild models to resolve forward references
FilterGroup.model_rebuild()
