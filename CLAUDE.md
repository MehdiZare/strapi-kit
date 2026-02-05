# Claude Code Context for strapi-kit

This file helps Claude Code instances work efficiently in this codebase. It contains architecture patterns, critical commands, and design decisions specific to strapi-kit.

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
pytest --cov=strapi_kit --cov-report=html --cov-report=term

# Run specific test file
pytest tests/unit/test_client.py -v
```

#### Type Checking
```bash
# Full type check (strict mode enabled)
mypy src/strapi_kit/

# Type check with verbose output
mypy src/strapi_kit/ --show-error-codes
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
from strapi_kit.models import StrapiQuery, FilterBuilder, SortDirection

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
- `src/strapi_kit/protocols.py`: Protocol definitions
- `src/strapi_kit/parsers/version_detecting.py`: Default parser implementation
- `src/strapi_kit/auth/api_token.py`: Default auth implementation (satisfies AuthProvider)
- `tests/unit/test_dependency_injection.py`: DI tests and usage examples

### Exception Hierarchy

**Semantic exception design** (exceptions/errors.py):

```
StrapiError (base)
├─ ConfigurationError (invalid config, missing token, bad URL)
├─ AuthenticationError (401)
├─ AuthorizationError (403)
├─ NotFoundError (404)
├─ ValidationError (400, input validation)
├─ ConflictError (409)
├─ ServerError (5xx)
├─ NetworkError (connection issues)
│  ├─ ConnectionError (from strapi_kit.exceptions, not builtin)
│  ├─ TimeoutError (from strapi_kit.exceptions, not builtin)
│  └─ RateLimitError
└─ ImportExportError (data operations)
   ├─ FormatError
   ├─ RelationError
   └─ MediaError
```

**Usage pattern**: Always catch specific exceptions before generic ones. All exceptions carry optional `details: dict[str, Any]` for context.

**Non-HTTP exceptions**:
- `ConfigurationError`: Invalid API token, missing config, bad base URL
- `ValidationError`: Invalid query parameters (pagination, filters), invalid function arguments
- `FormatError`: Invalid export data format, path traversal prevention
- `MediaError`: File not found, upload/download failures, context manager misuse

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

## Import/Export Architecture

The import/export system enables large-scale Strapi data migrations and backups with streaming support.

### Module Structure
```
strapi_kit/
├─ export/
│  ├─ exporter.py          # StrapiExporter class - main export orchestration
│  ├─ importer.py          # StrapiImporter class - main import orchestration
│  ├─ media_handler.py     # MediaHandler - media download/upload
│  ├─ relation_resolver.py # RelationResolver - schema-based relation resolution
│  ├─ jsonl_writer.py      # JSONLExportWriter - streaming JSONL export
│  └─ jsonl_reader.py      # JSONLImportReader - streaming JSONL import
└─ models/
   ├─ export_format.py     # ExportData, ExportedEntity, ExportMetadata
   └─ import_options.py    # ImportOptions, ImportResult, ConflictResolution
```

### Export Operations (`StrapiExporter`)

```python
from strapi_kit import SyncClient
from strapi_kit.export import StrapiExporter

with SyncClient(config) as client:
    exporter = StrapiExporter(client)

    # Export content types with media
    export_data = exporter.export_content_types(
        ["api::article.article", "api::author.author"],
        include_media=True,
        media_dir="export/media",
        progress_callback=lambda cur, total, msg: print(f"{cur}/{total}: {msg}")
    )

    # Save to JSON file
    exporter.save_to_file(export_data, "export.json")

    # Or stream to JSONL for large datasets (O(1) memory)
    exporter.export_to_jsonl(
        ["api::article.article"],
        "export.jsonl",
        media_dir="export/media"
    )
```

### Import Operations (`StrapiImporter`)

```python
from strapi_kit.export import StrapiImporter, StrapiExporter
from strapi_kit.models.import_options import ImportOptions, ConflictResolution

# Load export data
export_data = StrapiExporter.load_from_file("export.json")

with SyncClient(target_config) as client:
    importer = StrapiImporter(client)

    # Import with options
    result = importer.import_data(
        export_data,
        options=ImportOptions(
            dry_run=True,  # Validate without writing
            conflict_resolution=ConflictResolution.SKIP  # or UPDATE, FAIL
        ),
        media_dir="export/media"
    )

    if result.success:
        print(f"Imported {result.entities_imported} entities")

    # Or stream from JSONL (two-pass for relation resolution)
    result = importer.import_from_jsonl(
        "export.jsonl",
        media_dir="export/media"
    )
```

### Key Features

1. **JSONL Streaming**: O(1) memory for large datasets via `JSONLExportWriter`/`JSONLImportReader`
2. **Schema-based Relation Resolution**: `RelationResolver` uses Strapi schema to detect and resolve relations
3. **Conflict Resolution**: SKIP (ignore duplicates), UPDATE (overwrite), FAIL (abort on conflict)
4. **Media Handling**: `MediaHandler` downloads/uploads media with deduplication
5. **Dry-run Mode**: Validate imports without writing to Strapi
6. **Progress Callbacks**: Track long-running operations with `progress_callback`

### Exception Handling

- `ImportExportError`: Base for all import/export errors
- `FormatError`: Invalid export data format
- `RelationError`: Unresolvable entity relations
- `MediaError`: Media download/upload failures

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
@pytest.mark.respx
def test_get_many_typed(strapi_config, respx_mock: respx.Router):
    # Mock v5 response
    mock_response = {
        "data": [
            {"id": 1, "documentId": "abc", "title": "Article 1"},
            {"id": 2, "documentId": "def", "title": "Article 2"}
        ],
        "meta": {"pagination": {"page": 1, "pageSize": 25, "total": 2}}
    }

    respx_mock.get("http://localhost:1337/api/articles").mock(
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

**strapi-kit uses uv for fast dependency management:**

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

### Pre-commit Hooks

The project uses pre-commit hooks to enforce quality standards:

```bash
# One-time setup
make install-hooks

# Hooks run automatically on git commit
# They will:
# 1. Format code (ruff format)
# 2. Fix linting issues (ruff check --fix)
# 3. Run type checking (mypy)
# 4. Check for security issues (ruff S rules)
# 5. Prevent committing secrets (detect-secrets)

# Run hooks manually on all files
make run-hooks

# Update hooks to latest versions
make update-hooks
```

**What the hooks check:**
- ✅ Code formatting (ruff format)
- ✅ Linting (ruff check with auto-fix)
- ✅ Type checking (mypy strict mode on src/ only)
- ✅ Security issues (ruff S rules on src/ only)
- ✅ Secrets detection (detect-secrets)
- ✅ File consistency (trailing whitespace, EOF, YAML/TOML syntax, etc.)

**Bypass hooks** (use sparingly):
```bash
git commit --no-verify
```

**Important notes:**
- Hooks only run on staged files by default (fast)
- Type checking and security checks only scan `src/` directory (not tests or examples)
- mkdocs.yml is excluded from YAML checks (uses custom tags)
- Hooks are configured in `.pre-commit-config.yaml`
- Secrets baseline is stored in `.secrets.baseline`

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

**Automatic (via git hooks):**
```bash
# Hooks run automatically on commit
git add .
git commit -m "feat: your message"

# Hooks will:
# 1. Format code automatically
# 2. Fix linting issues
# 3. Type check src/ directory
# 4. Check for security issues
# 5. Prevent committing secrets
```

**Manual (for testing before commit):**
```bash
# 1. Format code
ruff format src/ tests/

# 2. Fix linting
ruff check src/ tests/ --fix

# 3. Type check
mypy src/strapi_kit/

# 4. Run security checks
make security

# 5. Run tests with coverage
pytest --cov=strapi_kit --cov-report=term

# 6. Or run all quality checks at once
make pre-commit
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

### Retry Logic (ACTIVE)
- Automatic retry with exponential backoff on transient failures
- Configured via nested `RetryConfig` in `StrapiConfig`
- Retries automatically on:
  - Connection errors (`StrapiConnectionError`)
  - Rate limit errors (429) with `Retry-After` header support
  - Server errors (5xx) - configurable via `retry_on_status`
  - Custom status codes via `retry_on_status` set
- Exponential backoff with configurable base, initial wait, and max wait times
- Respects `Retry-After` headers from Strapi API
- Applied to both sync and async clients transparently
- Full test coverage: 18 retry tests covering all scenarios

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

**Completed (Phase 4 - Retry & Bulk Operations)**:
- ✅ Automatic retry with exponential backoff
- ✅ Rate limit handling with retry-after support
- ✅ Connection error recovery
- ✅ Bulk operations (create, update, delete)
- ✅ Progress callbacks for long operations
- ✅ **18 passing retry tests**, full retry coverage

**Completed (Phase 5 - Import/Export)**:
- ✅ Content export with automatic relation extraction
- ✅ JSONL streaming export (O(1) memory)
- ✅ Schema-driven relation resolution
- ✅ Media export/import with deduplication
- ✅ Content import with conflict resolution (SKIP, UPDATE, FAIL)
- ✅ Two-pass streaming import for memory efficiency
- ✅ Dry-run mode for validation
- ✅ Progress callbacks for long operations

**Future phases**: See IMPLEMENTATION_STATUS.md for full roadmap

---

## Common Gotchas

1. **Version detection caching**: Once detected, `_api_version` is cached. Reset client instance to re-detect.

2. **Context manager requirement**: Always use `with SyncClient(...)` or `async with AsyncClient(...)` to ensure connection cleanup.

3. **Exception chaining**: Use `raise StrapiError(...) from e` to preserve original traceback.

4. **Async test setup**: No need for explicit event loop fixtures - pytest-asyncio auto mode handles it.

5. **Import naming conflict**: `ConnectionError` and `TimeoutError` conflict with builtins - always import explicitly from `strapi_kit.exceptions` to avoid confusion.

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
from strapi_kit.models import (
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
