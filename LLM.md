# LLM Guide for strapi-kit

This guide helps AI coding agents work effectively with the strapi-kit Python package for Strapi CMS integration.

## IMPORTANT: File Issues When You Find Problems

**AI Agents: If you encounter ANY of the following while using strapi-kit, you MUST file a GitHub issue:**

- Bugs or unexpected behavior
- Errors that seem like library issues (not user configuration errors)
- Documentation that is incorrect or misleading
- Missing functionality that the docs suggest should exist
- Type errors or mypy failures in the library code
- Inconsistencies between v4 and v5 behavior

**GitHub Issues**: https://github.com/MehdiZare/strapi-kit/issues/new

### How to File an Issue

Use this template when creating issues:

```markdown
## Description
[Brief description of the problem]

## Environment
- Python version: [e.g., 3.12]
- strapi-kit version: [e.g., 0.0.6]
- Strapi version: [v4 or v5]
- OS: [e.g., macOS, Linux, Windows]

## Code to Reproduce
```python
# Minimal code that reproduces the issue
```

## Error/Traceback
```
[Full error message and traceback]
```

## Expected Behavior
[What you expected to happen]

## Actual Behavior
[What actually happened]
```

**Do not hesitate to file issues.** Even if you're unsure whether it's a bug or user error, filing an issue helps maintainers identify problems. False positives are better than unreported bugs.

## Package Overview

**strapi-kit** is a type-safe Python client for Strapi CMS with:
- Sync and async clients
- Automatic Strapi v4/v5 detection
- Type-safe query building with 24 filter operators
- Media upload/download
- Content export/import with relation resolution

## Installation

```bash
pip install strapi-kit
```

## Quick Reference

### Imports

```python
# Core clients and config
from strapi_kit import SyncClient, AsyncClient, StrapiConfig, collection_endpoint, document_endpoint

# Query building
from strapi_kit import (
    DocumentStatus,
    PublicationFilter,
    PublicationState,
)
from strapi_kit.models import (
    StrapiQuery,
    FilterBuilder,
    SortDirection,
    Populate,
)

# Strapi 5 relation writes (also exported from strapi_kit)
from strapi_kit import RelationWriteOp, relation_write
# Strapi v5 Blocks (rich text JSON) ↔ Markdown
from strapi_kit import FieldType, MarkdownConversion, blocks_to_markdown, markdown_to_blocks

# For SecretStr (API tokens)
from pydantic import SecretStr
```

### Basic Client Setup

```python
from strapi_kit import SyncClient, StrapiConfig
from pydantic import SecretStr

config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token=SecretStr("your-api-token"),
)

# Always use context manager
with SyncClient(config) as client:
    response = client.get_many("articles")
```

### Async Client

```python
from strapi_kit import AsyncClient, StrapiConfig

async with AsyncClient(config) as client:
    response = await client.get_many("articles")
```

## CRUD Operations

REST collection paths come from `schema.pluralName`, not the UID. Resolve the path once, then pass that string to `get_many` / `create` / `get_one`:

```python
from strapi_kit import collection_endpoint, document_endpoint

# From Content-Type Builder list items or schemas
endpoint = collection_endpoint(content_type)  # e.g. "blog-posts", never "posts" from api::post.post
response = client.get_many(endpoint)
response = client.create(endpoint, {"title": "Hello"})
response = client.get_one(document_endpoint(content_type, document_id))
```

`collection_endpoint` raises `ValidationError` if `pluralName` is missing, blank, or not a string. `document_endpoint` raises if `document_id` is blank. Do not append `s`, use `apiID`, or split the UID.

### Read

```python
# Get many (returns NormalizedCollectionResponse)
response = client.get_many("articles")
for article in response.data:
    print(article.id, article.attributes["title"])

# Get one — prefer collection + document_id so the ID is percent-encoded
response = client.get_one("articles", document_id="abc123")
article = response.data
print(article.attributes["title"])

# String endpoint still works (caller must encode `/`, `?`, `#`, `%` themselves)
response = client.get_one("articles/1")

# Shared helper used by get_one / update / remove
path = client.document_path("articles", "a/b?x=1")  # "articles/a%2Fb%3Fx%3D1"

# Raw API (returns dict)
response = client.get("articles")  # dict

# Origin-rooted admin probe (no /api prefix)
info = client.get_admin_information()
print(info.strapi_version)  # str | None
```

## Admin Information and Origin Paths

Content, Content-Type Builder, and upload stay under `/api`. `admin/` is origin-rooted.

Default `get("admin/information")` **still** prefixes `/api` (no silent change):

```python
client.get("admin/information")  # GET {base}/api/admin/information
```

Opt out with `api_prefix=False`, or use the first-class helper:

```python
from strapi_kit.models import AdminInformation

# Escape hatch (also on post/put/delete and the retry wrappers)
client.request("GET", "admin/information", api_prefix=False)
client.get("admin/information", api_prefix=False)

# GET {base}/admin/information
info: AdminInformation = client.get_admin_information()
# info.strapi_version from top-level strapiVersion or data.strapiVersion
# Missing version is still a successful probe (token worked)
# info.raw is the original JSON dict
# Origin-rooted responses do not drive v4/v5 content-API version detection
# Empty / non-object 2xx bodies raise UnstructuredResponseError
```

```python
# Async
info = await client.get_admin_information()
```

### Create

```python
data = {"title": "New Article", "content": "Body text"}
response = client.create("articles", data)
new_id = response.data.document_id or str(response.data.id)
```

### Update

```python
data = {"title": "Updated Title"}
response = client.update("articles", data, document_id="abc123")
# Also valid: client.update("articles/1", data)

# Opt-in: write 404 while the draft is still readable → AuthorizationError
# (token likely lacks Update/Publish). status_code=404 and
# details["classified_from"] == "write_404".
client.update("articles", data, document_id="abc123", classify_write_404=True)
```

### Delete

```python
response = client.remove("articles", document_id="abc123")
# Also valid: client.remove("articles/1")
client.remove("articles", document_id="abc123", classify_write_404=True)
```

### Exists (published, then draft)

Strapi 5 omitted `status=` means published. Draft-only documents 404 on
the default GET. `exists()` retries once with `status=draft`. A draft
`ValidationError` (Draft & Publish off) is `False`. Auth / 5xx / network
on either read raise. Collection must be one path segment; `document_id`
is percent-encoded. A 200 with no `id` / `documentId` is `False`.

```python
if client.exists("articles", document_id):
    ...
```

### Publish / Unpublish (Strapi v5)

```python
from strapi_kit.models import DocumentStatus, StrapiQuery

# See drafts (v5 defaults omitted status to published)
drafts = client.get_many(
    "articles",
    query=StrapiQuery().with_document_status(DocumentStatus.DRAFT),
)

# Never-published drafts (status=draft + publicationFilter)
from strapi_kit.models import PublicationFilter
never_published = client.get_many(
    "articles",
    query=(
        StrapiQuery()
        .with_document_status(DocumentStatus.DRAFT)
        .with_publication_filter(PublicationFilter.NEVER_PUBLISHED)
    ),
)

# Two-step live publish: create as draft, then publish
created = client.create("articles", {"title": "Draft"})
published = client.publish("articles", created.data.document_id)
client.unpublish("articles", created.data.document_id)
client.discard_draft("articles", created.data.document_id)
```

A 2xx empty body or a non-object JSON body (`"Created"`) raises
`UnstructuredResponseError` with `status_code`. Do not treat that as a
successful entity. Empty 204 / DELETE remains `{}`.

### Relation Writes (Strapi 5)

v5 REST relation writes take **documentId** strings, not numeric `id`.
Do not send v4 `{ connect: [{ id: 1 }] }` shapes.

```python
from strapi_kit import RelationWriteOp, relation_write

# One-side: 0 ids → None, 1 id → documentId string, 2+ raises ValidationError
data = {
    "title": "New Article",
    "author": relation_write(document_ids=["authorDocId"], multiple=False),
}

# Many-side replace
data = {
    "categories": relation_write(
        document_ids=["cat1", "cat2"],
        multiple=True,  # default op is RelationWriteOp.SET
    ),
}

# Incremental
data = {
    "categories": relation_write(
        document_ids=["cat3"],
        multiple=True,
        op=RelationWriteOp.CONNECT,
    ),
}

# {"documentId": "..."} objects normalize to short strings
data = {
    "author": relation_write(
        document_ids=[{"documentId": "authorDocId"}],
        multiple=False,
    ),
}

response = client.create("articles", data)
```

## Query Building

### Filters

```python
from strapi_kit.models import StrapiQuery, FilterBuilder

# Basic equality
query = StrapiQuery().filter(FilterBuilder().eq("status", "published"))

# Multiple conditions (AND)
query = StrapiQuery().filter(
    FilterBuilder()
        .eq("status", "published")
        .gt("views", 100)
        .contains("title", "Python")
)

# OR conditions
query = StrapiQuery().filter(
    FilterBuilder()
        .eq("status", "published")
        .or_group(
            FilterBuilder().gt("views", 1000),
            FilterBuilder().gt("likes", 500)
        )
)

# Available operators
# eq, ne, gt, gte, lt, lte, contains, not_contains,
# starts_with, ends_with, in_, not_in, null, not_null,
# between, is_empty, is_not_empty
```

### Sorting

```python
from strapi_kit.models import StrapiQuery, SortDirection

query = (StrapiQuery()
    .sort_by("publishedAt", SortDirection.DESC)
    .then_sort_by("title", SortDirection.ASC))
```

### Pagination

```python
# Page-based
query = StrapiQuery().paginate(page=1, page_size=25)

# Offset-based
query = StrapiQuery().paginate(start=0, limit=50)
```

Stock Strapi silently caps `pageSize` at `maxLimit` (default 100).
`PagePagination` is already `le=100`. `get_many()` does **not** verify the
echo — use the opt-in helper for import/export completeness:

```python
from strapi_kit import assert_pagination_echo

response = client.get_many("articles", query)
total = assert_pagination_echo(
    response.meta,
    requested_page=1,
    requested_page_size=25,
)
```

`page_size > 100` is unsafe unless the server `maxLimit` is raised. Digit
strings (`"12"`) are accepted; `bool` is not an int. Signed digit strings
(`"-1"`) are readable negatives and fail the non-negative `total` check.
Absent `page`/`pageSize` keys are tolerated; a present but unreadable echo
raises `ValidationError`.

### Population (Relations)

```python
from strapi_kit.models import StrapiQuery, Populate

# Populate all
query = StrapiQuery().populate_all()

# Specific fields
query = StrapiQuery().populate_fields(["author", "category"])

# Advanced with nested
query = StrapiQuery().populate(
    Populate()
        .add_field("author", fields=["name", "email"])
        .add_field("comments", nested=Populate().add_field("author"))
)
```

### Complete Query Example

```python
query = (StrapiQuery()
    .filter(FilterBuilder().eq("status", "published").gt("views", 100))
    .sort_by("publishedAt", SortDirection.DESC)
    .paginate(page=1, page_size=20)
    .populate_fields(["author", "category"])
    .select(["title", "slug", "publishedAt"]))

response = client.get_many("articles", query=query)
```

## Strapi v5 Blocks ↔ Markdown

Strapi 5 rich text (`FieldType.BLOCKS = "blocks"`) is a JSON tree, **not** a
markdown string. Classic `richtext` strings pass through as markdown at the call
site — do not run them through these converters.

There is **no** HTML ↔ blocks conversion and **no** image upload here (use the
media API for uploads).

```python
from strapi_kit import FieldType, blocks_to_markdown, markdown_to_blocks

assert FieldType.BLOCKS == "blocks"

# Read: blocks JSON → markdown
conversion = blocks_to_markdown(entity.attributes["body"])
md = conversion.markdown
# conversion.lossy_reasons is () iff the conversion is faithful.
# Reasons are deduplicated. Underline, missing image/link URLs, unknown
# types, malformed nodes, and trees deeper than 32 are recorded — never
# silent. A depth guard prevents recursion bombs and cyclic children.

# Write: best-effort markdown → blocks (inline markdown stays literal text)
body = markdown_to_blocks("# Title\n\nA paragraph\n\n- item")
client.create("articles", {"title": "Hello", "body": body})

# Empty input is pinned to one empty paragraph
assert markdown_to_blocks("") == [
    {"type": "paragraph", "children": [{"type": "text", "text": ""}]}
]
```

Supported read nodes: `paragraph`, `heading` (1–6), `list` + `list-item`,
`quote`, `code`, `image`, `link`, `text`. Marks: bold, italic, strikethrough,
code. Text leaves are escaped before marks so `**literal**` cannot invent
formatting.

`markdown_to_blocks` is **not** a full CommonMark AST. It recognizes headings,
paragraphs, fenced code, lists, and blockquotes. Inline constructs stay as
literal text.

## Media Operations

### Upload

```python
# Single file
media = client.upload_file(
    "image.jpg",
    alternative_text="Alt text",
    caption="Caption"
)
print(media.id, media.url)

# Attach to entity
media = client.upload_file(
    "cover.jpg",
    ref="api::article.article",
    ref_id="abc123",
    field="cover"
)

# Multiple files
media_list = client.upload_files(["img1.jpg", "img2.jpg"])
```

### Download

```python
# Get bytes
content = client.download_file("/uploads/image.jpg")

# Save to file
client.download_file("/uploads/image.jpg", save_path="local.jpg")
```

### Manage

```python
# List media
response = client.list_media()

# Get specific
media = client.get_media(42)

# Update metadata
client.update_media(42, alternative_text="New alt text")

# Delete
client.delete_media(42)
```

## Export/Import

```python
from strapi_kit import StrapiExporter, StrapiImporter

# Export
with SyncClient(source_config) as client:
    exporter = StrapiExporter(client)
    export_data = exporter.export_content_types([
        "api::article.article",
        "api::author.author"
    ])
    exporter.save_to_file(export_data, "backup.json")

# Import
with SyncClient(target_config) as client:
    importer = StrapiImporter(client)
    export_data = StrapiExporter.load_from_file("backup.json")
    result = importer.import_data(export_data)
    print(f"Imported {result.entities_imported} entities")
```

## Error Handling

```python
from strapi_kit.exceptions import (
    StrapiError,          # Base exception
    AuthenticationError,  # 401
    AuthorizationError,   # 403
    NotFoundError,        # 404
    ValidationError,      # 400/422 (including unique-index collisions)
    ServerError,          # 5xx
    NetworkError,         # Connection issues
    is_uniqueness_violation,
    format_validation_errors,
)

try:
    response = client.get_one("articles/999")
except NotFoundError:
    print("Article not found")
except AuthenticationError:
    print("Invalid API token")
except ValidationError as e:
    # Unique-index collisions stay ValidationError (HTTP 400/422), not ConflictError
    if is_uniqueness_violation(e):
        print(format_validation_errors(e) or str(e))
    else:
        print(f"Invalid payload: {e}")
except StrapiError as e:
    print(f"Strapi error: {e}")
```

## Response Structure

### NormalizedEntity (from get_one, get_many)

```python
response = client.get_one("articles/1")
entity = response.data

entity.id            # int - Entity ID
entity.document_id   # str | None - v5 documentId (None for v4)
entity.attributes    # dict - Custom fields {"title": "...", "content": "..."}
entity.published_at  # datetime | None
entity.created_at    # datetime | None
entity.updated_at    # datetime | None
entity.locale        # str | None
```

### Content-Type Builder (Draft & Publish)

```python
content_types = client.get_content_types()
schema = client.get_content_type_schema("api::article.article")

# Tri-state: True / False / None. Absence is NOT False.
ct.draft_and_publish      # bool | None
schema.draft_and_publish  # bool | None
ct.options                # dict | None (other option keys kept)

# Do not infer D&P from publishedAt.
# True if any of item / options / schema / schema.options has boolean
# draftAndPublish or draft_and_publish == True.

# Unparsable list items raise ValidationError unless you opt in:
client.get_content_types(skip_unparsable=True)
```

### Pagination Metadata

```python
response = client.get_many("articles", query)

response.meta.pagination.page        # Current page
response.meta.pagination.page_size   # Items per page
response.meta.pagination.page_count  # Total pages
response.meta.pagination.total       # Total items
```

## Configuration Options

```python
from strapi_kit import StrapiConfig, RetryConfig

config = StrapiConfig(
    base_url="http://localhost:1337",      # Required
    api_token=SecretStr("token"),          # Required
    api_version="auto",                    # "auto" | "v4" | "v5"
    timeout=30.0,                          # Request timeout (seconds)
    max_connections=10,                    # Connection pool size
    verify_ssl=True,                       # SSL verification
    retry=RetryConfig(
        max_attempts=3,                    # Retry count
        initial_wait=1.0,                  # First retry delay
        max_wait=60.0,                     # Max retry delay
        retry_on_status={500, 502, 503, 504},
    ),
)
```

`base_url` is the Strapi origin without a trailing `/api`. A final `/api` segment is stripped so `_build_url` does not produce `/api/api/...`. The same applies to `STRAPI_BASE_URL`. Mid-path `/api` (`https://host/api/v1`) and `/admin` are not stripped.

## Environment Variables

```bash
STRAPI_BASE_URL=http://localhost:1337
STRAPI_API_TOKEN=your-token
STRAPI_TIMEOUT=30.0
STRAPI_MAX_CONNECTIONS=10
```

```python
from strapi_kit import load_config

config = load_config()  # Auto-loads from .env or environment
```

## Common Patterns

### Content Type UID to Endpoint

Do **not** guess a REST path from the UID (no appending `s`, no `apiID`, no splitting `api::post.post`). Use `pluralName`:

```python
from strapi_kit import collection_endpoint, document_endpoint

# content_type is a ContentTypeListItem / ContentTypeSchema / dict with info.pluralName
endpoint = collection_endpoint(content_type)  # "blog-posts"
client.get_many(endpoint)
client.create(endpoint, data)
client.get_one(document_endpoint(content_type, document_id))
```

`uid_to_endpoint()` is a heuristic only. If `pluralName` is missing or blank, `collection_endpoint` raises `ValidationError` — that is the correct failure mode (guessing produces silent empty lists).

### Iterate All Pages

```python
from strapi_kit import assert_pagination_echo

page = 1
page_size = 100
while True:
    query = StrapiQuery().paginate(page=page, page_size=page_size)
    response = client.get_many("articles", query=query)
    total = assert_pagination_echo(
        response.meta,
        requested_page=page,
        requested_page_size=page_size,
    )

    for item in response.data:
        process(item)

    if page * page_size >= total:
        break
    page += 1
```

### Check API Version

```python
with SyncClient(config) as client:
    # Make a request first to trigger detection
    client.get_many("articles", query=StrapiQuery().paginate(1, 1))

    if client.api_version == "v5":
        # Use documentId
        pass
    else:
        # Use numeric id
        pass
```

## Key Files in Codebase

| Path | Purpose |
|------|---------|
| `src/strapi_kit/client/sync_client.py` | Synchronous client |
| `src/strapi_kit/client/async_client.py` | Async client |
| `src/strapi_kit/client/base.py` | Shared client logic |
| `src/strapi_kit/models/request/query.py` | StrapiQuery builder |
| `src/strapi_kit/models/request/relation_write.py` | v5 relation write helper |
| `src/strapi_kit/models/request/filters.py` | FilterBuilder |
| `src/strapi_kit/models/response/normalized.py` | Response models |
| `src/strapi_kit/models/response/pagination.py` | Pagination echo / maxLimit guard |
| `src/strapi_kit/operations/media.py` | Media utilities |
| `src/strapi_kit/utils/blocks.py` | Strapi v5 Blocks ↔ Markdown |
| `src/strapi_kit/models/schema.py` | FieldType (includes `BLOCKS`) |
| `src/strapi_kit/exceptions/errors.py` | Exception hierarchy |
| `src/strapi_kit/models/config.py` | Configuration models |

## Testing

```python
import pytest
from strapi_kit import SyncClient, StrapiConfig
from pydantic import SecretStr

@pytest.fixture
def config():
    return StrapiConfig(
        base_url="http://localhost:1337",
        api_token=SecretStr("test-token"),
    )

# Use respx for HTTP mocking
import respx
import httpx

@respx.mock
def test_get_articles(config):
    respx.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(200, json={
            "data": [{"id": 1, "attributes": {"title": "Test"}}],
            "meta": {"pagination": {"page": 1, "pageSize": 25, "total": 1}}
        })
    )

    with SyncClient(config) as client:
        response = client.get_many("articles")
        assert len(response.data) == 1
```

## Examples

Complete working examples are available in the `examples/` directory:

| File | Description |
|------|-------------|
| [`examples/basic_crud.py`](examples/basic_crud.py) | Basic CRUD operations (create, read, update, delete) |
| [`examples/simple_migration.py`](examples/simple_migration.py) | Simple content migration between Strapi instances |
| [`examples/full_migration_v5.py`](examples/full_migration_v5.py) | Production-ready migration with auto-discovery |
| [`examples/MIGRATION_GUIDE.md`](examples/MIGRATION_GUIDE.md) | Comprehensive migration documentation |

### Running Examples

```bash
# Set environment variables for migration examples
export SOURCE_STRAPI_TOKEN='your-source-token'
export TARGET_STRAPI_TOKEN='your-target-token'

# Run basic CRUD
python examples/basic_crud.py

# Run simple migration
python examples/simple_migration.py

# Run full migration
python examples/full_migration_v5.py migrate
```

## Tips for LLM Agents

1. **Always use context managers** (`with` / `async with`) for clients
2. **Use typed methods** (`get_many`, `create`) over raw methods (`get`, `post`)
3. **Build queries incrementally** - chain methods on `StrapiQuery()`
4. **Handle errors specifically** - catch `NotFoundError` before `StrapiError`
5. **Check response.data** - it's `None` for 404 on `get_one`
6. **API prefix is automatic** - use `"articles"` not `"/api/articles"`. Resolve that string with `collection_endpoint(schema)` (`pluralName`), never by pluralizing the UID
7. **SecretStr for tokens** - always wrap API tokens in `SecretStr`
8. **v4 vs v5** - use `document_id` for v5, `id` works for both
9. **Encode document IDs** - use `get_one("articles", document_id=id)` (same for `update`/`remove`) instead of f-strings; IDs with `/`, `?`, `#`, `%` change the path if interpolated raw. Blank collection or id raises `ValidationError`.
10. **FILE ISSUES** - If you find bugs, errors, or unexpected behavior, **file an issue immediately** at https://github.com/MehdiZare/strapi-kit/issues/new - this is critical for improving the library
