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
│  ├─ ConnectionError
│  ├─ TimeoutError
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

**Completed (Phase 1)**:
- ✅ HTTP clients (sync/async)
- ✅ Configuration with environment support
- ✅ Authentication (API tokens)
- ✅ Exception hierarchy (all types defined)
- ✅ Version detection (v4/v5)
- ✅ Testing infrastructure (82% coverage)

**Next (Phase 2 - Models & Response Handling)**:
- Response models with v4/v5 normalization
- Request models (filters, sorting, pagination)
- Content type introspection models
- Type-safe query builders

**Future phases**: See IMPLEMENTATION_STATUS.md for full roadmap

---

## Common Gotchas

1. **Version detection caching**: Once detected, `_api_version` is cached. Reset client instance to re-detect.

2. **Context manager requirement**: Always use `with SyncClient(...)` or `async with AsyncClient(...)` to ensure connection cleanup.

3. **Exception chaining**: Use `raise StrapiError(...) from e` to preserve original traceback.

4. **Async test setup**: No need for explicit event loop fixtures - pytest-asyncio auto mode handles it.

5. **Import naming conflict**: `ConnectionError` conflicts with builtin - import as `StrapiConnectionError`.

6. **API prefix**: Don't include `/api/` in endpoint strings - it's added automatically.

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
