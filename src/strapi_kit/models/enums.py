"""Enumerations for Strapi API parameters and types.

This module defines core enums used throughout the models package:
- FilterOperator: 24 operators for query filtering
- SortDirection: Ascending/descending sort
- PublicationState: Draft, published, preview content states
"""

from enum import Enum
from typing import Literal

# Type aliases for common Strapi types
StrapiVersion = Literal["v4", "v5", "auto"]
LocaleCode = str  # ISO 639-1 language codes (e.g., "en", "fr", "de")


class FilterOperator(str, Enum):
    """Filter operators supported by Strapi REST API.

    Strapi supports 24 filter operators for querying content.
    All operators work with both v4 and v5 APIs.

    Examples:
        >>> FilterOperator.EQ.value
        '$eq'
        >>> FilterOperator.CONTAINS.value
        '$contains'
    """

    # Equality operators
    EQ = "$eq"  # Equal
    EQI = "$eqi"  # Equal (case-insensitive)
    NE = "$ne"  # Not equal
    NEI = "$nei"  # Not equal (case-insensitive)

    # Comparison operators
    LT = "$lt"  # Less than
    LTE = "$lte"  # Less than or equal
    GT = "$gt"  # Greater than
    GTE = "$gte"  # Greater than or equal

    # String matching operators
    CONTAINS = "$contains"  # Contains substring
    NOT_CONTAINS = "$notContains"  # Does not contain substring
    CONTAINSI = "$containsi"  # Contains substring (case-insensitive)
    NOT_CONTAINSI = "$notContainsi"  # Does not contain substring (case-insensitive)
    STARTS_WITH = "$startsWith"  # Starts with string
    STARTS_WITHI = "$startsWithi"  # Starts with string (case-insensitive)
    ENDS_WITH = "$endsWith"  # Ends with string
    ENDS_WITHI = "$endsWithi"  # Ends with string (case-insensitive)

    # Array operators
    IN = "$in"  # Value is in array
    NOT_IN = "$notIn"  # Value is not in array

    # Null operators
    NULL = "$null"  # Value is null
    NOT_NULL = "$notNull"  # Value is not null

    # Date/time range operators
    BETWEEN = "$between"  # Value is between two values (inclusive)

    # Logical operators (used at filter group level)
    AND = "$and"  # Logical AND
    OR = "$or"  # Logical OR
    NOT = "$not"  # Logical NOT


class SortDirection(str, Enum):
    """Sort direction for query results.

    Examples:
        >>> SortDirection.ASC.value
        'asc'
        >>> SortDirection.DESC.value
        'desc'
    """

    ASC = "asc"  # Ascending order (A-Z, 0-9, oldest-newest)
    DESC = "desc"  # Descending order (Z-A, 9-0, newest-oldest)


class PublicationState(str, Enum):
    """Content publication state filter.

    Only applicable to content types with draft & publish enabled.
    Used to filter between draft and published versions.

    Examples:
        >>> PublicationState.LIVE.value
        'live'
        >>> PublicationState.PREVIEW.value
        'preview'
    """

    LIVE = "live"  # Only published content
    PREVIEW = "preview"  # Both draft and published content
