# Claude Code Context for py-strapi

This file helps Claude Code instances work efficiently in this codebase. It contains architecture patterns, critical commands, and design decisions specific to py-strapi.

**About this file**: This is a CLAUDE.md file, created to help Claude Code (Anthropic's official CLI for Claude) work more effectively in this repository. Learn more at https://claude.com/claude-code

---

## Essential Commands

### Using Makefile (Recommended)

The project includes a comprehensive Makefile for common tasks:

```bash
# See all available commands
make help

# Quick shortcuts
make t          # Run tests
make c          # Run tests with coverage
make f          # Format code
make l          # Run linting
make tc         # Type check

# Full pre-commit checks (format + lint + type-check + test)
make pre-commit

# Documentation
make docs-serve  # Serve docs locally at http://127.0.0.1:8000
make docs-build  # Build documentation

# Quality checks
make quality     # Run lint + type-check
make clean       # Remove all build/test artifacts
```

### Direct Commands (without Make)

#### Testing
```bash
# Run all tests with output
pytest -v

# Run with coverage report
pytest --cov=py_strapi --cov-report=html --cov-report=term

# Run specific test file
pytest tests/unit/test_client.py -v
```

#### Type Checking
```bash
# Full type check (strict mode enabled)
mypy src/py_strapi/

# Type check with verbose output
mypy src/py_strapi/ --show-error-codes
```

#### Linting & Formatting
```bash
# Format all code (modifies files)
ruff format src/ tests/

# Check linting (no changes)
ruff check src/ tests/

# Auto-fix linting issues
ruff check src/ tests/ --fix
```

#### Documentation
```bash
# Serve documentation locally
mkdocs serve

# Build documentation
mkdocs build

# Deploy to GitHub Pages
mkdocs gh-deploy
```

### Coverage Requirements
- Target: 85%+ overall coverage
- All new code should have accompanying tests
- Test both sync and async variants when applicable

---

## Architecture Overview

### Dual Client Design Pattern

The codebase implements a **shared base with dual client specialization** pattern:

```
BaseClient (client/base.py)
├─ Shared logic: URL building, error mapping, version detection
├─ Abstract HTTP operations
│
├── SyncClient (client/sync_client.py)
│   └─ httpx.Client for blocking operations
│
└── AsyncClient (client/async_client.py)
    └─ httpx.AsyncClient for non-blocking operations
```

**Key principle**: All HTTP logic lives in BaseClient. Subclasses only implement the actual HTTP calls (GET/POST/PUT/DELETE) using their respective httpx client types.

**Why this matters**: When adding features, implement shared logic in BaseClient once. Only duplicate when sync/async semantics differ (like context managers).

### Strapi Version Detection

**Auto-detection mechanism** (client/base.py):
- Detects v4 vs v5 from first API response structure
- v4: nested `{"data": {"id": 1, "attributes": {...}}}`
- v5: flattened `{"data": {"documentId": "xyz", ...}}`
- Detection cached in `self._api_version` after first successful request
- Can be overridden via `StrapiConfig(api_version="v4"|"v5")`

**Implementation detail**: `_detect_api_version()` inspects response JSON for presence of `attributes` (v4) or `documentId` (v5).

### Typed Models & Query Builder

**Type-safe API** (`client/sync_client.py`, `client/async_client.py`):
- New methods: `get_one()`, `get_many()`, `create()`, `update()`, `remove()`
- Accept `StrapiQuery` parameter for type-safe filtering, sorting, pagination
- Return normalized responses (`NormalizedSingleResponse` | `NormalizedCollectionResponse`)
- Automatic v4/v5 detection and normalization via `BaseClient._parse_*_response()`

**Query Building** (`models/request/query.py`):
```python
from py_strapi.models import StrapiQuery, FilterBuilder, SortDirection

query = (StrapiQuery()
    .filter(FilterBuilder()
        .eq("status", "published")
        .gt("views", 100))
    .sort_by("publishedAt", SortDirection.DESC)
    .paginate(page=1, page_size=25)
    .populate_fields(["author", "category"]))

response = client.get_many("articles", query=query)
```

**Response Normalization** (`models/response/normalized.py`):
- `NormalizedEntity` provides version-agnostic interface
- Factory methods: `.from_v4()` and `.from_v5()`
- Flattens v4 nested attributes, preserves v5 structure
- System fields (timestamps, locale) promoted to top level
- Custom fields grouped in `attributes` dict

**Key principle**: Old raw methods (`get`, `post`, etc.) still work for backward compatibility. New typed methods provide better DX.

### Media Operations Architecture

**Design**: Media methods extend existing clients (`client/sync_client.py`, `client/async_client.py`):
- 7 media methods in each client: `upload_file()`, `upload_files()`, `download_file()`, `list_media()`, `get_media()`, `delete_media()`, `update_media()`
- Shared utilities in `operations/media.py` for payload building, response normalization, URL construction
- Full v4/v5 support with automatic detection
- Streaming downloads for large files
- Multipart uploads with metadata (alt text, captions, entity attachments)

**Media Methods** (`client/sync_client.py`, `client/async_client.py`):
```python
# Upload single file
media = client.upload_file(
    "image.jpg",
    alternative_text="Alt text",
    caption="Caption",
    ref="api::article.article",  # Optional entity attachment
    ref_id="abc123",
    field="cover"
)

# Batch upload
media_list = client.upload_files(["img1.jpg", "img2.jpg", "img3.jpg"])

# Download with streaming
content = client.download_file("/uploads/image.jpg", save_path="local.jpg")

# List with queries
response = client.list_media(query)  # Returns NormalizedCollectionResponse

# Get single media
media = client.get_media(42)  # Returns MediaFile

# Update metadata
updated = client.update_media(42, alternative_text="New alt text")

# Delete
client.delete_media(42)
```

**Shared Utilities** (`operations/media.py`):
- `build_upload_payload()`: Constructs multipart form data with JSON-encoded fileInfo
- `normalize_media_response()`: Handles v4/v5 MediaFile normalization
- `build_media_download_url()`: Constructs absolute URLs for downloads

**BaseClient Extensions** (`client/base.py`):
- `_build_upload_headers()`: Headers without Content-Type for multipart (httpx auto-sets boundary)
- `_parse_media_response()`: Single media file parsing with version detection
- `_parse_media_list_response()`: Media collection parsing (reuses `_parse_collection_response()`)

**Key implementation details**:
1. **Multipart uploads**: `fileInfo` JSON-encoded as string for httpx compatibility
2. **Streaming downloads**: Use `response.iter_bytes()` (sync) or `aiter_bytes()` (async)
3. **Error handling**: `MediaError` wraps upload/download failures, includes context
4. **Batch uploads**: Sequential (no rollback on failure), reports which file failed
5. **URL handling**: Supports both relative (`/uploads/...`) and absolute (`https://cdn...`) URLs

### Dependency Injection Architecture

**Protocol-based DI** (`protocols.py`):
- Defines interfaces for core dependencies using Python `Protocol`
- `AuthProvider`: Authentication interface
- `HTTPClient` / `AsyncHTTPClient`: HTTP client interfaces
- `ResponseParser`: Response parsing interface
- All implementations are runtime-checkable with `isinstance()`

**Dependency Injection Points** (`client/base.py`, `client/sync_client.py`, `client/async_client.py`):

```python
# BaseClient accepts auth and parser
BaseClient(
    config: StrapiConfig,
    auth: AuthProvider | None = None,        # Defaults to APITokenAuth
    parser: ResponseParser | None = None     # Defaults to VersionDetectingParser
)

# SyncClient/AsyncClient accept HTTP client
SyncClient(
    config: StrapiConfig,
    http_client: HTTPClient | None = None,   # Defaults to httpx.Client
    auth: AuthProvider | None = None,
    parser: ResponseParser | None = None
)
```

**Design Principles**:
1. **Sensible defaults**: All dependencies have defaults for simple usage
2. **Ownership tracking**: `_owns_client` flag tracks whether to close injected resources
3. **Factory methods**: `_create_default_http_client()` creates configured defaults
4. **Backward compatible**: Simple API unchanged, DI is optional for advanced users

**When to use DI**:
- **Testing**: Inject mocks to avoid real HTTP calls
- **Customization**: Provide custom parsers for non-standard formats
- **Resource sharing**: Share HTTP clients across multiple Strapi instances
- **Custom auth**: Implement alternative authentication schemes

**Example - Testing with mocks**:
```python
class MockHTTPClient:
    def __init__(self):
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url))
        return mock_response

    def close(self):
        pass

# Inject mock for unit testing (no HTTP calls)
mock_http = MockHTTPClient()
client = SyncClient(config, http_client=mock_http)
client.get("articles")  # No actual HTTP

assert len(mock_http.requests) == 1
```

**Implementation modules**:
- `src/py_strapi/protocols.py`: Protocol definitions
- `src/py_strapi/parsers/version_detecting.py`: Default parser implementation
- `src/py_strapi/auth/api_token.py`: Default auth implementation (satisfies AuthProvider)
- `tests/unit/test_dependency_injection.py`: DI tests and usage examples

### Exception Hierarchy

**Semantic exception design** (exceptions/errors.py):

```
StrapiError (base)
├─ AuthenticationError (401)
├─ AuthorizationError (403)
├─ NotFoundError (404)
├─ ValidationError (400)
├─ ConflictError (409)
├─ ServerError (5xx)
├─ NetworkError (connection issues)
│  ├─ ConnectionError (from py_strapi.exceptions, not builtin)
│  ├─ TimeoutError (from py_strapi.exceptions, not builtin)
│  └─ RateLimitError
└─ ImportExportError (data operations)
   ├─ FormatError
   ├─ RelationError
   └─ MediaError
```

**Usage pattern**: Always catch specific exceptions before generic ones. All exceptions carry optional `details: dict[str, Any]` for context.

**HTTP mapping** (client/base.py:_handle_error_response):
- 401 → AuthenticationError
- 403 → AuthorizationError
- 404 → NotFoundError
- 400 → ValidationError
- 409 → ConflictError
- 429 → RateLimitError
- 5xx → ServerError

---

## Configuration System

**Pydantic Settings-based** (models/config.py):

```python
StrapiConfig(
    base_url: str                    # Required: Strapi instance URL (trailing slash stripped)
    api_token: SecretStr             # Required for authenticated endpoints
    api_version: Literal["auto", "v4", "v5"] = "auto"
    timeout: float = 30.0
    max_connections: int = 10
    retry: RetryConfig
    rate_limit_per_second: float | None = None
    verify_ssl: bool = True
)

RetryConfig(
    max_attempts: int = 3
    initial_wait: float = 1.0
    max_wait: float = 60.0
    exponential_base: float = 2.0
    retry_on_status: set[int] = {500, 502, 503, 504}
)
```

**Environment variable support**: All fields can be set via `STRAPI_*` env vars (e.g., `STRAPI_BASE_URL`).

**Validation rules**:
- `base_url` trailing slash is stripped; enforce HTTP(S) URLs if you change config types
- `timeout` must be positive
- `retry.max_attempts` range: 1-10

---

## Import/Export Architecture (Planned - Phase 5-6)

While import/export functionality isn't implemented yet, the foundation is prepared:

### Exception Infrastructure
- `ImportExportError`, `FormatError`, `RelationError`, `MediaError` already defined
- These will be raised during data validation and transfer operations

### Design Principles for Future Implementation
1. **Large dataset handling**: Use streaming/generators for memory efficiency
2. **Relation resolution**: Track entity dependencies, import in correct order
3. **Media handling**: Separate media downloads/uploads from content data
4. **Progress tracking**: Emit events/callbacks for long-running operations
5. **Dry-run mode**: Validate before executing (especially for imports)
6. **Idempotency**: Safe to retry failed imports

### Planned Module Structure
```
py_strapi/
├─ export/
│  ├─ exporter.py          # Main export orchestration
│  ├─ content_collector.py # Gather content types and entries
│  └─ media_downloader.py  # Handle media files
├─ import/
│  ├─ importer.py          # Main import orchestration
│  ├─ validator.py         # Pre-import validation
│  ├─ resolver.py          # Relation resolution
│  └─ media_uploader.py    # Handle media uploads
└─ models/
   ├─ export_format.py     # Export file format models
   └─ import_options.py    # Import configuration models
```

**When implementing**: Follow the sync/async dual pattern. Export/import should work with both SyncClient and AsyncClient.

---

## Testing Patterns

### HTTP Mocking with respx
All HTTP tests use `respx` to mock Strapi API responses:

```python
@pytest.mark.respx
def test_something(respx_mock):
    # Mock a GET request
    respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(200, json={"data": []})
    )
```

### Shared Fixtures (tests/conftest.py)
- `mock_v4_response`: Typical Strapi v4 format response
- `mock_v5_response`: Typical Strapi v5 format response
- `strapi_config`: Standard test configuration

### Test Organization
- `tests/unit/`: Fast, isolated unit tests (no external dependencies)
- Future: `tests/integration/`: Tests against real Strapi instance (Docker)

### Async Testing
- pytest-asyncio handles `async def test_*` automatically (marks optional with auto mode)
- Use `async with AsyncClient(...) as client` in tests
- No need for `@pytest.mark.asyncio` (auto mode enabled)

### Testing Typed Models
When testing typed client methods, mock responses should match v4 or v5 format:

```python
@respx.mock
def test_get_many_typed(strapi_config):
    # Mock v5 response
    mock_response = {
        "data": [
            {"id": 1, "documentId": "abc", "title": "Article 1"},
            {"id": 2, "documentId": "def", "title": "Article 2"}
        ],
        "meta": {"pagination": {"page": 1, "pageSize": 25, "total": 2}}
    }

    respx.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(200, json=mock_response)
    )

    with SyncClient(strapi_config) as client:
        response = client.get_many("articles")

        # Response is normalized automatically
        assert isinstance(response, NormalizedCollectionResponse)
        assert len(response.data) == 2
        assert response.data[0].document_id == "abc"
```

**Pattern**: The client automatically detects v4/v5 from response and normalizes. Tests can use either format.

---

## Code Quality Standards

### Mypy (Type Checking)
- **Strict mode enabled**: All type errors must be resolved
- All functions require type hints (return type + parameters)
- No `Any` types without explicit reason
- Test files exempt from `disallow_untyped_defs`

### Ruff (Linting)
- Line length: 100 characters
- Enabled rule sets: E, W, F, I, B, C4, UP
- Import sorting via isort rules
- `__init__.py` files allowed unused imports (F401)

### Exception Handling
- Always use `raise ... from e` for exception chaining
- Catch specific exceptions before generic ones
- Include context in exception `details` dict when available

### Docstring Convention
- All public classes and methods require docstrings
- Format: Google-style docstrings
- Include Args, Returns, Raises sections

---

## Development Workflow

### Code Review & CI

**Automated Code Review:**
- CodeRabbit AI reviews all pull requests automatically
- Configuration: `.coderabbit.yaml`
- Focuses on: security, type safety, test coverage, code quality
- Checks: conventional commits, PR title format
- Auto-labels PRs based on changed files

**Required Checks:**
- All tests must pass (pytest)
- Type checking must pass (mypy strict mode)
- Linting must pass (ruff)
- Coverage should maintain 85%+

### Dependency Management

**py-strapi uses uv for fast dependency management:**

```bash
# Install dependencies
uv pip install -e ".[dev]"

# Install specific package
uv pip install package-name

# Upgrade dependencies
uv pip install --upgrade package-name
```

**Why uv?**
- 10-100x faster than pip
- Drop-in pip replacement (`uv pip` command)
- Used in CI/CD workflows
- Better dependency resolution

**Fallback to pip:** If uv is not available, `pip` commands work identically.

### Adding New Features
1. **Update models** if new data structures needed (models/)
2. **Implement in BaseClient** if shared logic (client/base.py)
3. **Extend sync/async clients** if client-specific (client/sync_client.py, client/async_client.py)
4. **Add exceptions** if new error cases (exceptions/errors.py)
5. **Write tests** for both sync and async paths (tests/unit/)
6. **Update docs/metadata** so README, `pyproject.toml`, and public docstrings match reality
7. **Update type hints** and verify with mypy
8. **Run full test suite** including coverage check

### Pre-commit Checklist
```bash
# 1. Format code
ruff format src/ tests/

# 2. Fix linting
ruff check src/ tests/ --fix

# 3. Type check
mypy src/py_strapi/

# 4. Run tests with coverage
pytest --cov=py_strapi --cov-report=term

# 5. Verify all checks pass
```

---

## Critical Implementation Details

### URL Building (client/base.py)
- **Strapi v4/v5 prefix**: All endpoints automatically prefixed with `/api/`
- **Trailing slash handling**: Removed from base_url, not added to paths
- **Example**: `base_url="http://localhost:1337"` + `"articles"` → `"http://localhost:1337/api/articles"`

### Authentication (auth/api_token.py)
- API token injected as `Authorization: Bearer <token>` header
- Token validation happens in `BaseClient.__init__`
- Token masked in logs/repr as `"abcd...wxyz"` (or `"****"` if too short)

### Connection Pooling
- **Sync**: `httpx.Client` with limits (max_connections, keepalive uses same value)
- **Async**: `httpx.AsyncClient` with same limits
- **Context managers**: Ensure proper cleanup (`__enter__`/`__exit__` and `__aenter__`/`__aexit__`)

### Retry Logic (Planned - Phase 4)
- Decorator infrastructure ready with tenacity
- Configured via nested `RetryConfig`
- Not yet active - needs explicit use of `self._create_retry_decorator()`
- `retry_on_status` is currently unused; wire it up if retry is implemented

---

## Project Goals & Priorities

**Primary use case**: Large-scale Strapi data migrations and backups

**Key requirements**:
1. Handle thousands of entries efficiently (streaming/pagination)
2. Preserve relations and media during export/import
3. Support both Strapi v4 and v5 seamlessly
4. Type-safe operations with comprehensive error handling
5. Support both sync (scripts) and async (web apps) contexts

**Non-goals**:
- Not a full CMS admin UI
- Not focusing on GraphQL (REST API only)
- Not implementing Strapi plugins (core API only)

---

## Current Phase Status

**Completed (Phase 1 - Core Infrastructure)**:
- ✅ HTTP clients (sync/async)
- ✅ Configuration with environment support
- ✅ Authentication (API tokens)
- ✅ Exception hierarchy (all types defined)
- ✅ Version detection (v4/v5)
- ✅ Testing infrastructure

**Completed (Phase 2 - Type-Safe Query Builder)**:
- ✅ Request models: Filters (24 operators), sorting, pagination, population, field selection
- ✅ Response models: V4/V5 parsing with automatic normalization
- ✅ Query builder: `StrapiQuery` fluent API with full type safety
- ✅ Typed client methods: `get_one()`, `get_many()`, `create()`, `update()`, `remove()`
- ✅ **179 passing tests**, **96% coverage**, **mypy strict compliance**

**Completed (Phase 3 - Media Upload/Download)**:
- ✅ Media upload with metadata (alt text, captions, entity attachments)
- ✅ Batch file uploads with error handling
- ✅ File downloads with streaming support
- ✅ Media library queries with filters
- ✅ Media metadata updates
- ✅ Media file deletion
- ✅ Full sync/async support
- ✅ **58 passing media tests**, **100% operations coverage**, **85% overall coverage**

**In Progress (Phase 4 - Advanced Features)**:
- Bulk operations with streaming
- Advanced retry strategies

**Future phases**: See IMPLEMENTATION_STATUS.md for full roadmap

---

## Common Gotchas

1. **Version detection caching**: Once detected, `_api_version` is cached. Reset client instance to re-detect.

2. **Context manager requirement**: Always use `with SyncClient(...)` or `async with AsyncClient(...)` to ensure connection cleanup.

3. **Exception chaining**: Use `raise StrapiError(...) from e` to preserve original traceback.

4. **Async test setup**: No need for explicit event loop fixtures - pytest-asyncio auto mode handles it.

5. **Import naming conflict**: `ConnectionError` and `TimeoutError` conflict with builtins - always import explicitly from `py_strapi.exceptions` to avoid confusion.

6. **API prefix**: Don't include `/api/` in endpoint strings - it's added automatically.

7. **Typed vs Raw methods**:
   - Raw methods (`get`, `post`, etc.) return `dict[str, Any]`
   - Typed methods (`get_one`, `get_many`, etc.) return `NormalizedSingleResponse` | `NormalizedCollectionResponse`
   - Use typed methods for new code, raw methods for backward compatibility

8. **Pagination strategies**: Cannot mix page-based (`page`, `page_size`) with offset-based (`start`, `limit`) in the same query.

9. **FilterBuilder chaining**: All filter methods implicitly AND together. Use `.or_group()` for OR logic.

10. **Populate configuration**: Simple field lists use array format `["author", "category"]`. Advanced config (filters, nested) uses object format.

---

## Working with Typed Models

### Building Queries

**Import all model types from single location**:
```python
from py_strapi.models import (
    StrapiQuery,
    FilterBuilder,
    SortDirection,
    Populate,
    PublicationState,
)
```

**Pattern 1: Simple queries**
```python
query = (StrapiQuery()
    .filter(FilterBuilder().eq("status", "published"))
    .sort_by("publishedAt", SortDirection.DESC)
    .paginate(page=1, page_size=25))
```

**Pattern 2: Complex nested queries**
```python
query = (StrapiQuery()
    .filter(FilterBuilder()
        .eq("status", "published")
        .or_group(
            FilterBuilder().gt("views", 1000),
            FilterBuilder().gt("likes", 500)))
    .populate(Populate()
        .add_field("author", fields=["name", "email"])
        .add_field("comments",
            filters=FilterBuilder().eq("approved", True),
            nested=Populate().add_field("author"))))
```

**Pattern 3: Deep relation filtering**
```python
# Filter on nested relations using dot notation
query = StrapiQuery().filter(
    FilterBuilder()
        .eq("author.profile.verified", True)
        .gt("author.followers_count", 1000))
```

### Working with Responses

**Pattern 1: Accessing normalized data**
```python
response = client.get_one("articles/1")

if response.data:
    article = response.data
    print(article.id)                    # int
    print(article.document_id)           # str | None (v5 only)
    print(article.attributes["title"])   # Any custom field
    print(article.published_at)          # datetime | None
```

**Pattern 2: Iterating collections**
```python
response = client.get_many("articles", query)

for article in response.data:
    # All articles are NormalizedEntity instances
    print(f"{article.id}: {article.attributes['title']}")
```

**Pattern 3: Pagination metadata**
```python
response = client.get_many("articles", query)

if response.meta and response.meta.pagination:
    total = response.meta.pagination.total
    pages = response.meta.pagination.page_count
    print(f"Showing page 1 of {pages} ({total} total)")
```

### Adding Features with Models

**When adding new query capabilities**:
1. Add to appropriate request model (filters.py, sort.py, etc.)
2. Add fluent method to `StrapiQuery` (query.py)
3. Add tests to `tests/unit/models/`
4. Verify mypy passes with strict mode

**When adding new response types**:
1. Add Pydantic model to `models/response/`
2. Update `NormalizedEntity` if needed for v4/v5 compatibility
3. Add tests comparing v4 and v5 normalization
4. Verify 100% coverage of new code

**Example: Adding a new filter operator**
```python
# 1. Add to FilterOperator enum (if not already present)
class FilterOperator(str, Enum):
    # ... existing operators
    REGEX = "$regex"  # New operator

# 2. Add method to FilterBuilder
def regex(self, field: str, pattern: str) -> "FilterBuilder":
    """Match field against regex pattern."""
    return self._add_condition(field, FilterOperator.REGEX, pattern)

# 3. Add test
def test_regex_operator():
    builder = FilterBuilder().regex("email", r".*@example\.com")
    assert builder.to_query_dict() == {"email": {"$regex": r".*@example\.com"}}
```

---

## Dependencies Overview

**Core runtime**:
- `httpx`: HTTP client (sync/async)
- `pydantic`: Data validation and settings
- `tenacity`: Retry logic infrastructure
- `orjson`: Fast JSON parsing (for large exports)

**Development**:
- `pytest` + `pytest-asyncio`: Testing
- `respx`: HTTP mocking
- `mypy`: Type checking
- `ruff`: Linting and formatting

**Philosophy**: Minimal dependencies, prefer stdlib when reasonable, prioritize type safety.

---

## Additional Resources

- **Strapi API docs**: https://docs.strapi.io/dev-docs/api/rest
- **Strapi v4 → v5 migration**: https://docs.strapi.io/dev-docs/migration/v4-to-v5
- **httpx docs**: https://www.python-httpx.org/
- **Pydantic Settings**: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
