"""Enumerations for Strapi API parameters and types.

This module defines core enums used throughout the models package:
- FilterOperator: 24 operators for query filtering
- SortDirection: Ascending/descending sort
- PublicationState: v4 live/preview content states
- DocumentStatus: v5 draft/published ``status``
- PublicationFilter: v5 draft/published relationship filter
- DocumentAction: v5 ``/actions/{publish|unpublish|discardDraft}``
- QueryParam: closed REST query-parameter keys
- HttpMethod: HTTP verbs used by the client
- RelationWriteOp: Strapi 5 REST relation write operations
"""

from enum import StrEnum
from typing import Literal

# Type aliases for common Strapi types
StrapiVersion = Literal["v4", "v5", "auto"]
LocaleCode = str  # ISO 639-1 language codes (e.g., "en", "fr", "de")


class FilterOperator(StrEnum):
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


class SortDirection(StrEnum):
    """Sort direction for query results.

    Examples:
        >>> SortDirection.ASC.value
        'asc'
        >>> SortDirection.DESC.value
        'desc'
    """

    ASC = "asc"  # Ascending order (A-Z, 0-9, oldest-newest)
    DESC = "desc"  # Descending order (Z-A, 9-0, newest-oldest)


class PublicationState(StrEnum):
    """v4 content publication state filter (``publicationState``).

    Only applicable to content types with draft & publish enabled.
    Strapi v5 uses :class:`DocumentStatus` (``status``) instead.

    Examples:
        >>> PublicationState.LIVE.value
        'live'
        >>> PublicationState.PREVIEW.value
        'preview'
    """

    LIVE = "live"  # Only published content
    PREVIEW = "preview"  # Both draft and published content


class DocumentStatus(StrEnum):
    """v5 document status filter (``status``).

    Strapi 5 Draft & Publish lists default to the published version when
    ``status`` is omitted. Every document has a draft version (a published
    document has both, sharing one ``documentId``), so ``draft`` enumerates
    every document regardless of publication state.

    Do not mix this with :class:`PublicationState` on the same query.

    Examples:
        >>> DocumentStatus.DRAFT.value
        'draft'
        >>> DocumentStatus.PUBLISHED.value
        'published'
    """

    DRAFT = "draft"
    PUBLISHED = "published"


class PublicationFilter(StrEnum):
    """v5 ``publicationFilter`` (how draft and published versions relate).

    ``status`` chooses *which version* to return (draft or published).
    ``publicationFilter`` chooses *which documents* to include based on
    the relationship between those versions.

    ``published-without-draft`` and ``published-with-draft`` are
    diagnostic-only values (data-integrity checks), not everyday queries.

    Do not mix this with :class:`PublicationState` on the same query.
    Combining with :class:`DocumentStatus` is valid and expected.

    Examples:
        >>> PublicationFilter.NEVER_PUBLISHED.value
        'never-published'
        >>> PublicationFilter.MODIFIED.value
        'modified'
    """

    NEVER_PUBLISHED = "never-published"
    NEVER_PUBLISHED_DOCUMENT = "never-published-document"
    MODIFIED = "modified"
    UNMODIFIED = "unmodified"
    HAS_PUBLISHED_VERSION = "has-published-version"
    HAS_PUBLISHED_VERSION_DOCUMENT = "has-published-version-document"
    PUBLISHED_WITHOUT_DRAFT = "published-without-draft"
    PUBLISHED_WITH_DRAFT = "published-with-draft"


class DocumentAction(StrEnum):
    """Strapi v5 document-action path segment.

    Used by ``POST /api/{collection}/{documentId}/actions/{action}``.

    Examples:
        >>> DocumentAction.PUBLISH.value
        'publish'
        >>> DocumentAction.DISCARD_DRAFT.value
        'discardDraft'
    """

    PUBLISH = "publish"
    UNPUBLISH = "unpublish"
    DISCARD_DRAFT = "discardDraft"


class QueryParam(StrEnum):
    """Closed set of Strapi REST query-parameter keys.

    These are protocol keys (``status=``, ``publicationState=``), not
    content-type field names such as an article attribute named
    ``status``.

    Examples:
        >>> QueryParam.STATUS.value
        'status'
        >>> QueryParam.PUBLICATION_FILTER.value
        'publicationFilter'
    """

    STATUS = "status"
    PUBLICATION_STATE = "publicationState"
    PUBLICATION_FILTER = "publicationFilter"
    LOCALE = "locale"


class HttpMethod(StrEnum):
    """HTTP methods used by the client.

    Examples:
        >>> HttpMethod.DELETE.value
        'DELETE'
    """

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class RelationWriteOp(StrEnum):
    """Strapi 5 REST relation write operations.

    v5 many-side writes use a closed vocabulary on the relation field:

    * ``set`` — replace the full relation list
    * ``connect`` — add documentIds without removing existing links
    * ``disconnect`` — remove documentIds without touching other links

    One-side writes take a documentId string or ``None`` and do not use this
    object shape. v5 relation writes take **documentId** strings, not numeric
    ``id``. This enum does not model v4 ``{ connect: [{ id: 1 }] }`` payloads.

    Examples:
        >>> RelationWriteOp.SET.value
        'set'
        >>> RelationWriteOp.CONNECT.value
        'connect'
        >>> RelationWriteOp.DISCONNECT.value
        'disconnect'
    """

    SET = "set"
    CONNECT = "connect"
    DISCONNECT = "disconnect"
