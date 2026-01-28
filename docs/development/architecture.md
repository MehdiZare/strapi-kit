# Architecture

This document provides an overview of py-strapi's architecture and design decisions.

## High-Level Overview

```
py_strapi/
├── client/          # HTTP clients (sync/async)
├── models/          # Pydantic models for config & data
├── auth/            # Authentication mechanisms
├── exceptions/      # Exception hierarchy
├── operations/      # High-level operations (planned)
└── importexport/    # Import/export functionality (planned)
```

## Core Components

### Dual Client Design

The project uses a **shared base with specialized implementations** pattern:

```
BaseClient
├─ Shared HTTP logic
├─ Version detection (v4/v5)
├─ Error handling
└─ URL building

SyncClient              AsyncClient
├─ httpx.Client         ├─ httpx.AsyncClient
├─ Blocking I/O         ├─ Non-blocking I/O
└─ Context manager      └─ Async context manager
```

**Design Benefits:**
- Code reuse for common logic
- Identical APIs for sync/async
- Easy to maintain and extend
- Type-safe implementations

**Implementation Pattern:**
```python
class BaseClient:
    def _build_url(self, endpoint: str) -> str:
        # Shared logic
        return f"{self.config.base_url}/api/{endpoint}"

class SyncClient(BaseClient):
    def get(self, endpoint: str) -> dict[str, Any]:
        url = self._build_url(endpoint)  # Uses shared logic
        response = self._client.get(url)  # Sync-specific
        return response.json()

class AsyncClient(BaseClient):
    async def get(self, endpoint: str) -> dict[str, Any]:
        url = self._build_url(endpoint)  # Uses shared logic
        response = await self._client.get(url)  # Async-specific
        return response.json()
```

### Strapi Version Detection

**Automatic v4/v5 Detection:**

Strapi v4 and v5 have different response formats:

```python
# Strapi v4
{
    "data": {
        "id": 1,
        "attributes": {
            "title": "Hello"
        }
    }
}

# Strapi v5
{
    "data": {
        "documentId": "abc123",
        "title": "Hello"
    }
}
```

**Detection Logic:**
1. First API response is inspected
2. Presence of `attributes` → v4
3. Presence of `documentId` → v5
4. Cached in `_api_version` for subsequent requests

### Configuration System

**Pydantic Settings-Based:**

```python
StrapiConfig
├─ base_url: str
├─ api_token: SecretStr
├─ api_version: Literal["auto", "v4", "v5"]
├─ timeout: float
├─ max_connections: int
└─ retry: RetryConfig
```

**Environment Variable Support:**
- All fields can be set via `STRAPI_*` env vars
- `.env` file support
- Type validation with Pydantic
- Secure handling of secrets with `SecretStr`

### Exception Hierarchy

**Semantic Exception Design:**

```
StrapiError (base)
├─ AuthenticationError (401)
├─ AuthorizationError (403)
├─ NotFoundError (404)
├─ ValidationError (400)
├─ ConflictError (409)
├─ ServerError (5xx)
├─ NetworkError
│  ├─ ConnectionError
│  ├─ TimeoutError
│  └─ RateLimitError
└─ ImportExportError
   ├─ FormatError
   ├─ RelationError
   └─ MediaError
```

**Usage Pattern:**
```python
try:
    response = client.get("articles")
except NotFoundError:
    # Handle 404 specifically
    pass
except AuthenticationError:
    # Handle 401 specifically
    pass
except StrapiError:
    # Catch all other Strapi errors
    pass
```

## Design Principles

### 1. Type Safety First

- All public APIs have full type hints
- Mypy strict mode enforced
- Pydantic for runtime validation
- No `Any` types without explicit reason

### 2. Explicit Over Implicit

- Clear, obvious APIs
- No magic behavior
- Configuration is explicit
- Error messages are informative

### 3. No Over-Engineering

- Simple solutions over clever ones
- Avoid premature abstractions
- Three similar lines > one complex abstraction
- YAGNI (You Aren't Gonna Need It)

### 4. Performance Where It Matters

- Connection pooling for reuse
- Streaming for large datasets (planned)
- Efficient JSON parsing with orjson
- Async support for concurrency

### 5. Fail Fast, Fail Loud

- Validate early (at config time)
- Specific exception types
- Include context in errors
- No silent failures

## Key Patterns

### Context Managers

Both clients use context managers for resource cleanup:

```python
# Sync
with SyncClient(config) as client:
    # Client open, connection pool active
    response = client.get("articles")
# Client closed, resources cleaned up

# Async
async with AsyncClient(config) as client:
    # Client open
    response = await client.get("articles")
# Client closed
```

### Exception Chaining

Always preserve the original exception:

```python
try:
    response = httpx_client.get(url)
except httpx.HTTPError as e:
    raise ConnectionError(
        "Failed to connect to Strapi",
        details={"url": url, "error": str(e)}
    ) from e  # Preserve original traceback
```

### Retry Infrastructure

Ready for use but not yet active:

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(config.retry_max_attempts),
    wait=wait_exponential(multiplier=config.retry_multiplier)
)
def _request_with_retry(self, method: str, url: str) -> httpx.Response:
    return self._client.request(method, url)
```

## Future Architecture

### Import/Export (Planned)

```
Exporter
├─ ContentCollector
│  └─ Discovers and fetches all content types
├─ RelationResolver
│  └─ Tracks and preserves relationships
└─ MediaDownloader
   └─ Downloads media files

Importer
├─ Validator
│  └─ Pre-import validation
├─ ConflictResolver
│  └─ Handles existing content
├─ RelationLinker
│  └─ Recreates relationships
└─ MediaUploader
   └─ Uploads media files
```

**Design Goals:**
- Handle large datasets (streaming)
- Preserve all relationships
- Idempotent (safe to retry)
- Progress tracking
- Dry-run mode

### Operations Layer (Planned)

High-level operations built on clients:

```python
# Current (low-level)
response = client.get("articles", params={"filters": {"title": {"$eq": "Hello"}}})

# Future (high-level)
articles = operations.find_articles(title="Hello")
```

## Testing Architecture

### Test Pyramid

```
              /\
             /  \  Integration Tests (few)
            /____\
           /      \  Unit Tests (many)
          /________\
```

### Mocking Strategy

- Use `respx` for HTTP mocking
- Mock at HTTP boundary, not internals
- Shared fixtures for common responses
- Fast, isolated unit tests

### Test Coverage

- Target: 85%+
- All public APIs covered
- Both success and error paths
- Both sync and async variants

## Dependencies

**Core:**
- httpx: HTTP client
- pydantic: Validation & settings
- tenacity: Retry logic
- orjson: Fast JSON parsing

**Philosophy:**
- Minimal dependencies
- Prefer stdlib when reasonable
- Only production-ready libraries
- Type-safe by default

## Further Reading

- [Contributing Guide](contributing.md)
- [Testing Guide](testing.md)
- [CLAUDE.md](../../CLAUDE.md) - Technical details for AI assistants
