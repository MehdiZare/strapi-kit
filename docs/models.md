# Models Reference

Complete reference for py-strapi's type-safe models and query builder.

## Table of Contents

- [Overview](#overview)
- [Query Builder](#query-builder)
- [Filter Operators](#filter-operators)
- [Response Models](#response-models)
- [Normalization](#normalization)
- [Advanced Patterns](#advanced-patterns)

## Overview

py-strapi provides a complete type-safe interface for building Strapi queries and parsing responses. The models work with both Strapi v4 and v5, automatically detecting the version and normalizing responses to a consistent format.

### Key Components

- **`StrapiQuery`**: Main query builder combining filters, sort, pagination, etc.
- **`FilterBuilder`**: Fluent API for building complex filters
- **`Populate`**: Configure relation expansion with nested filtering
- **`NormalizedEntity`**: Version-agnostic response model

## Query Builder

### StrapiQuery

The main interface for building complete queries:

```python
from py_strapi.models import StrapiQuery

query = StrapiQuery()
```

### Methods

#### `.filter(filters: FilterBuilder) -> StrapiQuery`

Add filter conditions:

```python
query = StrapiQuery().filter(
    FilterBuilder()
        .eq("status", "published")
        .gt("views", 100)
)
```

#### `.sort_by(field: str, direction: SortDirection) -> StrapiQuery`

Add primary sort field:

```python
from py_strapi.models import SortDirection

query = StrapiQuery().sort_by("publishedAt", SortDirection.DESC)
```

#### `.then_sort_by(field: str, direction: SortDirection) -> StrapiQuery`

Add secondary sort fields:

```python
query = (StrapiQuery()
    .sort_by("status")
    .then_sort_by("publishedAt", SortDirection.DESC))
```

#### `.paginate(...) -> StrapiQuery`

Add pagination (page-based or offset-based):

```python
# Page-based
query = StrapiQuery().paginate(page=1, page_size=25)

# Offset-based
query = StrapiQuery().paginate(start=0, limit=50)

# Disable count
query = StrapiQuery().paginate(page=1, page_size=100, with_count=False)
```

#### `.populate(populate: Populate) -> StrapiQuery`

Advanced population configuration:

```python
from py_strapi.models import Populate

query = StrapiQuery().populate(
    Populate()
        .add_field("author", fields=["name", "email"])
        .add_field("category")
)
```

#### `.populate_all() -> StrapiQuery`

Populate all first-level relations:

```python
query = StrapiQuery().populate_all()
```

#### `.populate_fields(fields: list[str]) -> StrapiQuery`

Populate specific fields (simple):

```python
query = StrapiQuery().populate_fields(["author", "category", "tags"])
```

#### `.select(fields: list[str]) -> StrapiQuery`

Select specific fields to return:

```python
query = StrapiQuery().select(["title", "description", "publishedAt"])
```

#### `.with_locale(locale: str) -> StrapiQuery`

Set locale for i18n content:

```python
query = StrapiQuery().with_locale("fr")
```

#### `.with_publication_state(state: PublicationState) -> StrapiQuery`

Filter by publication state:

```python
from py_strapi.models import PublicationState

query = StrapiQuery().with_publication_state(PublicationState.LIVE)
```

#### `.to_query_params() -> dict[str, Any]`

Convert to query parameters for HTTP requests:

```python
params = query.to_query_params()
# Use with httpx: client.get(url, params=params)
```

## Filter Operators

### FilterBuilder

Fluent API for building filters with 24 operators:

```python
from py_strapi.models import FilterBuilder

builder = FilterBuilder()
```

### Equality Operators

```python
.eq(field, value)        # Equal (case-sensitive)
.eqi(field, value)       # Equal (case-insensitive)
.ne(field, value)        # Not equal (case-sensitive)
.nei(field, value)       # Not equal (case-insensitive)
```

**Examples:**
```python
FilterBuilder().eq("status", "published")
FilterBuilder().eqi("title", "HELLO WORLD")
FilterBuilder().ne("category", "draft")
```

### Comparison Operators

```python
.lt(field, value)        # Less than
.lte(field, value)       # Less than or equal
.gt(field, value)        # Greater than
.gte(field, value)       # Greater than or equal
```

**Examples:**
```python
FilterBuilder().gt("views", 1000)
FilterBuilder().between("price", 10, 100)
FilterBuilder().gte("publishedAt", "2024-01-01")
```

### String Matching Operators

```python
.contains(field, value)          # Contains substring
.not_contains(field, value)      # Does not contain
.containsi(field, value)         # Contains (case-insensitive)
.not_containsi(field, value)     # Does not contain (case-insensitive)
.starts_with(field, value)       # Starts with
.starts_withi(field, value)      # Starts with (case-insensitive)
.ends_with(field, value)         # Ends with
.ends_withi(field, value)        # Ends with (case-insensitive)
```

**Examples:**
```python
FilterBuilder().contains("title", "Python")
FilterBuilder().starts_with("slug", "blog-")
FilterBuilder().containsi("description", "tutorial")
```

### Array Operators

```python
.in_(field, values)      # Value is in array
.not_in(field, values)   # Value is not in array
```

**Examples:**
```python
FilterBuilder().in_("status", ["published", "draft"])
FilterBuilder().not_in("category", ["archived", "deleted"])
```

### Null Operators

```python
.null(field, is_null=True)    # Is null
.not_null(field)              # Is not null
```

**Examples:**
```python
FilterBuilder().null("deletedAt")        # Match null values
FilterBuilder().null("deletedAt", False) # Match non-null values
FilterBuilder().not_null("publishedAt")
```

### Range Operators

```python
.between(field, start, end)   # Value between start and end (inclusive)
```

**Examples:**
```python
FilterBuilder().between("price", 10, 100)
FilterBuilder().between("publishedAt", "2024-01-01", "2024-12-31")
```

### Logical Operators

```python
.and_group(*builders)     # AND group
.or_group(*builders)      # OR group
.not_group(builder)       # NOT group
```

**Examples:**
```python
# OR: category is "tech" OR "science"
FilterBuilder().or_group(
    FilterBuilder().eq("category", "tech"),
    FilterBuilder().eq("category", "science")
)

# Complex: published AND (views > 1000 OR likes > 500)
FilterBuilder()
    .eq("status", "published")
    .or_group(
        FilterBuilder().gt("views", 1000),
        FilterBuilder().gt("likes", 500)
    )

# NOT: status is NOT "draft"
FilterBuilder().not_group(
    FilterBuilder().eq("status", "draft")
)
```

### Deep Relation Filtering

Use dot notation to filter on nested relations:

```python
FilterBuilder().eq("author.name", "John Doe")
FilterBuilder().eq("author.profile.country", "USA")
FilterBuilder().gt("author.posts_count", 10)
```

### Chaining Filters

All filter methods return `self` for chaining:

```python
filters = (FilterBuilder()
    .eq("status", "published")
    .gt("views", 100)
    .contains("title", "Python")
    .null("deletedAt"))
```

## Response Models

### NormalizedEntity

Version-agnostic entity representation:

```python
class NormalizedEntity:
    id: int                          # Numeric ID (v4 and v5)
    document_id: str | None          # Document ID (v5 only, None for v4)
    created_at: datetime | None      # Creation timestamp
    updated_at: datetime | None      # Last update timestamp
    published_at: datetime | None    # Publication timestamp
    locale: str | None               # Locale code
    attributes: dict[str, Any]       # All custom fields
```

**Example:**
```python
response = client.get_one("articles/1")
article = response.data

print(article.id)                       # 1
print(article.document_id)              # "abc123" (v5) or None (v4)
print(article.attributes["title"])      # "My Article"
print(article.published_at)             # datetime object
```

### NormalizedSingleResponse

Response for single entity endpoints:

```python
class NormalizedSingleResponse:
    data: NormalizedEntity | None    # Entity or None if not found
    meta: ResponseMeta | None        # Response metadata
```

**Example:**
```python
response = client.get_one("articles/1")

if response.data:
    print(response.data.attributes["title"])
else:
    print("Article not found")
```

### NormalizedCollectionResponse

Response for collection endpoints:

```python
class NormalizedCollectionResponse:
    data: list[NormalizedEntity]     # List of entities
    meta: ResponseMeta | None        # Response metadata
```

**Example:**
```python
response = client.get_many("articles")

print(f"Total: {response.meta.pagination.total}")
for article in response.data:
    print(article.attributes["title"])
```

### PaginationMeta

Pagination metadata:

```python
class PaginationMeta:
    page: int | None         # Current page number
    page_size: int | None    # Items per page
    page_count: int | None   # Total pages
    total: int | None        # Total items
```

**Example:**
```python
response = client.get_many("articles", query)

if response.meta and response.meta.pagination:
    p = response.meta.pagination
    print(f"Page {p.page} of {p.page_count}")
    print(f"Total: {p.total} items")
```

## Normalization

### V4 vs V5 Structure

**Strapi v4** (nested attributes):
```json
{
  "data": {
    "id": 1,
    "attributes": {
      "title": "Article",
      "content": "Body",
      "createdAt": "2024-01-01T00:00:00.000Z"
    }
  }
}
```

**Strapi v5** (flattened):
```json
{
  "data": {
    "id": 1,
    "documentId": "abc123",
    "title": "Article",
    "content": "Body",
    "createdAt": "2024-01-01T00:00:00.000Z"
  }
}
```

**Normalized** (version-agnostic):
```python
NormalizedEntity(
    id=1,
    document_id="abc123",  # or None for v4
    created_at=datetime(2024, 1, 1),
    updated_at=None,
    published_at=None,
    locale=None,
    attributes={
        "title": "Article",
        "content": "Body"
    }
)
```

### Conversion Methods

```python
# From v4
v4_entity = V4Entity(**v4_response_data)
normalized = NormalizedEntity.from_v4(v4_entity)

# From v5
v5_entity = V5Entity(**v5_response_data)
normalized = NormalizedEntity.from_v5(v5_entity)
```

The client handles this automatically based on version detection.

## Advanced Patterns

### Nested Population with Filtering

Populate relations with their own filters and sorting:

```python
from py_strapi.models import Populate, FilterBuilder, Sort, SortDirection

query = StrapiQuery().populate(
    Populate()
        .add_field(
            "comments",
            filters=FilterBuilder().eq("approved", True),
            sort=Sort().by_field("createdAt", SortDirection.DESC),
            fields=["content", "author", "createdAt"],
            nested=Populate().add_field(
                "author",
                fields=["name", "avatar"]
            )
        )
)
```

### Deep Filtering on Multiple Relations

Filter on nested relation fields:

```python
query = StrapiQuery().filter(
    FilterBuilder()
        .eq("author.profile.verified", True)
        .eq("category.parent.name", "Technology")
        .gt("author.followers_count", 1000)
)
```

### Complex Logical Filters

Combine multiple conditions with AND/OR/NOT:

```python
# (status = published) AND ((views > 1000) OR (likes > 500)) AND (NOT archived)
query = StrapiQuery().filter(
    FilterBuilder()
        .eq("status", "published")
        .or_group(
            FilterBuilder().gt("views", 1000),
            FilterBuilder().gt("likes", 500)
        )
        .not_group(
            FilterBuilder().eq("archived", True)
        )
)
```

### Pagination with Sorting

Combine pagination and sorting for consistent results:

```python
query = (StrapiQuery()
    .filter(FilterBuilder().eq("status", "published"))
    .sort_by("publishedAt", SortDirection.DESC)
    .then_sort_by("id", SortDirection.ASC)  # Stable sort
    .paginate(page=1, page_size=25))
```

### Locale-Specific Queries

Query content in specific locales:

```python
query = (StrapiQuery()
    .filter(FilterBuilder().eq("status", "published"))
    .with_locale("fr")
    .populate_fields(["localizations"]))
```

### Working with Both APIs

Use typed and raw APIs together:

```python
with SyncClient(config) as client:
    # Typed API for complex queries
    query = StrapiQuery().filter(FilterBuilder().eq("status", "published"))
    typed_response = client.get_many("articles", query=query)

    # Raw API for flexibility
    raw_response = client.get("articles", params={"filters[status][$eq]": "published"})

    # Both work!
    assert len(typed_response.data) == len(raw_response["data"])
```

### Accessing Metadata

Extract pagination and other metadata:

```python
response = client.get_many("articles", query)

# Pagination
if response.meta and response.meta.pagination:
    total = response.meta.pagination.total
    pages = response.meta.pagination.page_count

# Available locales (if i18n enabled)
if response.meta and response.meta.available_locales:
    locales = response.meta.available_locales
```

### Type Safety Benefits

```python
from py_strapi.models import NormalizedEntity

response = client.get_one("articles/1")

# IDE autocomplete works!
article: NormalizedEntity = response.data
article.id                      # int
article.document_id             # str | None
article.created_at              # datetime | None
article.attributes              # dict[str, Any]

# Type checking with mypy
reveal_type(article.id)         # Revealed type is 'int'
reveal_type(article.attributes) # Revealed type is 'dict[str, Any]'
```

## Migration Guide

### From Raw API to Typed API

**Before (Raw API):**
```python
# Manual query building
params = {
    "filters[status][$eq]": "published",
    "filters[views][$gt]": 100,
    "sort": ["publishedAt:desc"],
    "pagination[page]": 1,
    "pagination[pageSize]": 25,
    "populate": ["author", "category"]
}

response = client.get("articles", params=params)

# Manual response parsing
for item in response["data"]:
    if "attributes" in item:  # v4
        title = item["attributes"]["title"]
    else:  # v5
        title = item["title"]
    print(title)
```

**After (Typed API):**
```python
# Type-safe query building
query = (StrapiQuery()
    .filter(FilterBuilder()
        .eq("status", "published")
        .gt("views", 100))
    .sort_by("publishedAt", SortDirection.DESC)
    .paginate(page=1, page_size=25)
    .populate_fields(["author", "category"]))

response = client.get_many("articles", query=query)

# Normalized response (works with both v4 and v5)
for article in response.data:
    print(article.attributes["title"])
```

### Benefits

1. **Type Safety**: Full IDE autocomplete and mypy checking
2. **Version Agnostic**: Works with both v4 and v5 automatically
3. **Cleaner Code**: Fluent API is more readable
4. **Less Error-Prone**: Pydantic validates all inputs
5. **Better Docs**: Inline documentation via docstrings
