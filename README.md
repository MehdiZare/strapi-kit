# py-strapi

**PyPI Package**: `strapi-kit`

A modern Python client for Strapi CMS with comprehensive import/export capabilities.

## Features

- 🚀 **Full Strapi Support**: Works with both v4 and v5 APIs with automatic version detection
- ⚡ **Async & Sync**: Choose between synchronous and asynchronous clients based on your needs
- 🔒 **Type Safe**: Built with Pydantic for robust data validation and type safety
- 🔄 **Import/Export**: Comprehensive backup/restore and data migration tools
- 🔁 **Smart Retry**: Automatic retry with exponential backoff for transient failures
- 📦 **Modern Python**: Built for Python 3.12+ with full type hints

## Installation

```bash
pip install strapi-kit
```

Or with uv (recommended for faster installs):

```bash
uv pip install strapi-kit
```

For development:

```bash
# With pip
pip install -e ".[dev]"

# With uv (recommended)
uv pip install -e ".[dev]"
```

## Quick Start

### Type-Safe API (Recommended)

The typed API provides full type safety, IDE autocomplete, and automatic v4/v5 normalization:

```python
from py_strapi import SyncClient, StrapiConfig
from py_strapi.models import StrapiQuery, FilterBuilder, SortDirection

config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token="your-api-token"
)

with SyncClient(config) as client:
    # Build a type-safe query
    query = (StrapiQuery()
        .filter(FilterBuilder()
            .eq("status", "published")
            .gt("views", 100))
        .sort_by("publishedAt", SortDirection.DESC)
        .paginate(page=1, page_size=25)
        .populate_fields(["author", "category"]))

    # Get normalized, type-safe response
    response = client.get_many("articles", query=query)

    # Works with both v4 and v5 automatically!
    for article in response.data:
        print(f"{article.id}: {article.attributes['title']}")
        print(f"Published: {article.published_at}")
```

### Raw API (Backward Compatible)

The raw API returns dictionaries directly from Strapi:

```python
from py_strapi import SyncClient, StrapiConfig

config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token="your-api-token"
)

with SyncClient(config) as client:
    # Get raw JSON response
    response = client.get("articles")
    print(response)  # dict
```

### Asynchronous Usage

Both typed and raw APIs work with async:

```python
import asyncio
from py_strapi import AsyncClient, StrapiConfig
from py_strapi.models import StrapiQuery, FilterBuilder

async def main():
    config = StrapiConfig(
        base_url="http://localhost:1337",
        api_token="your-api-token"
    )

    async with AsyncClient(config) as client:
        # Typed API
        query = StrapiQuery().filter(FilterBuilder().eq("status", "published"))
        response = await client.get_many("articles", query=query)

        for article in response.data:
            print(article.attributes["title"])

asyncio.run(main())
```

## Configuration

Configuration can be provided via environment variables with the `STRAPI_` prefix:

```bash
export STRAPI_BASE_URL="http://localhost:1337"
export STRAPI_API_TOKEN="your-token"
export STRAPI_API_VERSION="auto"  # or "v4" or "v5"
export STRAPI_TIMEOUT=30
```

Or via code:

```python
from py_strapi import StrapiConfig

config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token="your-token",
    api_version="auto",  # Automatic detection
    timeout=30.0,
    max_connections=10,
)
```

## Usage Examples

### Filtering

Use the `FilterBuilder` to create complex filters with 24 operators:

```python
from py_strapi.models import StrapiQuery, FilterBuilder

# Simple equality
query = StrapiQuery().filter(FilterBuilder().eq("status", "published"))

# Comparison operators
query = StrapiQuery().filter(
    FilterBuilder()
        .gt("views", 100)
        .lte("price", 50)
)

# String matching
query = StrapiQuery().filter(
    FilterBuilder()
        .contains("title", "Python")
        .starts_with("slug", "blog-")
)

# Array operators
query = StrapiQuery().filter(
    FilterBuilder().in_("category", ["tech", "science"])
)

# Logical operators (AND, OR, NOT)
query = StrapiQuery().filter(
    FilterBuilder()
        .eq("status", "published")
        .or_group(
            FilterBuilder().gt("views", 1000),
            FilterBuilder().gt("likes", 500)
        )
)

# Deep relation filtering
query = StrapiQuery().filter(
    FilterBuilder()
        .eq("author.name", "John Doe")
        .eq("author.country", "USA")
)
```

### Sorting

Sort by one or multiple fields:

```python
from py_strapi.models import StrapiQuery, SortDirection

# Single field
query = StrapiQuery().sort_by("publishedAt", SortDirection.DESC)

# Multiple fields
query = (StrapiQuery()
    .sort_by("status", SortDirection.ASC)
    .then_sort_by("publishedAt", SortDirection.DESC)
    .then_sort_by("title", SortDirection.ASC))

# Sort by relation field
query = StrapiQuery().sort_by("author.name", SortDirection.ASC)
```

### Pagination

Choose between page-based or offset-based pagination:

```python
from py_strapi.models import StrapiQuery

# Page-based pagination
query = StrapiQuery().paginate(page=1, page_size=25)

# Offset-based pagination
query = StrapiQuery().paginate(start=0, limit=50)

# Disable count for performance
query = StrapiQuery().paginate(page=1, page_size=100, with_count=False)
```

### Population (Relations)

Expand relations, components, and dynamic zones:

```python
from py_strapi.models import StrapiQuery, Populate, FilterBuilder, SortDirection

# Populate all relations
query = StrapiQuery().populate_all()

# Populate specific fields
query = StrapiQuery().populate_fields(["author", "category", "tags"])

# Advanced population with filtering and field selection
query = StrapiQuery().populate(
    Populate()
        .add_field("author", fields=["name", "email", "avatar"])
        .add_field("category")
        .add_field("comments",
            filters=FilterBuilder().eq("approved", True),
            sort=Sort().by_field("createdAt", SortDirection.DESC),
            fields=["content", "author"])
)

# Nested population
query = StrapiQuery().populate(
    Populate().add_field(
        "author",
        nested=Populate().add_field("profile")
    )
)
```

### Field Selection

Select specific fields to reduce payload size:

```python
from py_strapi.models import StrapiQuery

query = StrapiQuery().select(["title", "description", "publishedAt"])
```

### Locale & Publication State

For i18n and draft/publish workflows:

```python
from py_strapi.models import StrapiQuery, PublicationState

# Set locale
query = StrapiQuery().with_locale("fr")

# Set publication state
query = StrapiQuery().with_publication_state(PublicationState.LIVE)
```

### Complete Example

Combine all features for complex queries:

```python
from py_strapi import SyncClient, StrapiConfig
from py_strapi.models import (
    StrapiQuery,
    FilterBuilder,
    SortDirection,
    Populate,
    PublicationState,
)

config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token="your-token"
)

with SyncClient(config) as client:
    # Build complex query
    query = (StrapiQuery()
        # Filters
        .filter(FilterBuilder()
            .eq("status", "published")
            .gte("publishedAt", "2024-01-01")
            .null("deletedAt")
            .or_group(
                FilterBuilder().contains("title", "Python"),
                FilterBuilder().contains("title", "Django")
            ))
        # Sorting
        .sort_by("publishedAt", SortDirection.DESC)
        .then_sort_by("views", SortDirection.DESC)
        # Pagination
        .paginate(page=1, page_size=20)
        # Population
        .populate(Populate()
            .add_field("author", fields=["name", "avatar", "bio"])
            .add_field("category")
            .add_field("comments",
                filters=FilterBuilder().eq("approved", True)))
        # Field selection
        .select(["title", "slug", "excerpt", "coverImage", "publishedAt"])
        # Locale & publication
        .with_locale("en")
        .with_publication_state(PublicationState.LIVE))

    # Execute query with type-safe response
    response = client.get_many("articles", query=query)

    # Access normalized data (works with both v4 and v5!)
    print(f"Total articles: {response.meta.pagination.total}")
    print(f"Page {response.meta.pagination.page} of {response.meta.pagination.page_count}")

    for article in response.data:
        # All responses are normalized to the same structure
        print(f"ID: {article.id}")
        print(f"Document ID: {article.document_id}")  # v5 only, None for v4
        print(f"Title: {article.attributes['title']}")
        print(f"Published: {article.published_at}")
        print("---")
```

### CRUD Operations

Create, read, update, and delete entities:

```python
from py_strapi import SyncClient, StrapiConfig

config = StrapiConfig(base_url="http://localhost:1337", api_token="your-token")

with SyncClient(config) as client:
    # Create
    data = {"title": "New Article", "content": "Article body"}
    response = client.create("articles", data)
    created_id = response.data.id

    # Read one
    response = client.get_one(f"articles/{created_id}")
    article = response.data

    # Read many
    response = client.get_many("articles")
    all_articles = response.data

    # Update
    data = {"title": "Updated Title"}
    response = client.update(f"articles/{created_id}", data)

    # Delete
    response = client.remove(f"articles/{created_id}")
```

### Media Upload/Download

Upload, download, and manage media files in Strapi's media library:

```python
from py_strapi import SyncClient, StrapiConfig
from py_strapi.models import StrapiQuery, FilterBuilder

config = StrapiConfig(base_url="http://localhost:1337", api_token="your-token")

with SyncClient(config) as client:
    # Upload a file
    media = client.upload_file(
        "hero-image.jpg",
        alternative_text="Hero image",
        caption="Main article hero image"
    )
    print(f"Uploaded: {media.name} (ID: {media.id})")
    print(f"URL: {media.url}")

    # Upload and attach to an entity
    cover = client.upload_file(
        "cover.jpg",
        ref="api::article.article",
        ref_id="abc123",  # Article documentId or numeric ID
        field="cover"
    )

    # Upload multiple files
    files = ["image1.jpg", "image2.jpg", "image3.jpg"]
    media_list = client.upload_files(files, folder="gallery")
    print(f"Uploaded {len(media_list)} files")

    # List media library
    response = client.list_media()
    for item in response.data:
        print(f"{item.attributes['name']}: {item.attributes['url']}")

    # List with filters
    query = (StrapiQuery()
        .filter(FilterBuilder().eq("mime", "image/jpeg"))
        .paginate(page=1, page_size=10))
    response = client.list_media(query)

    # Get specific media details
    media = client.get_media(42)
    print(f"Name: {media.name}, Size: {media.size} KB")

    # Download a file
    content = client.download_file(media.url)
    print(f"Downloaded {len(content)} bytes")

    # Download and save
    client.download_file(
        media.url,
        save_path="downloaded_image.jpg"
    )

    # Update media metadata
    updated = client.update_media(
        42,
        alternative_text="Updated alt text",
        caption="Updated caption"
    )

    # Delete media
    client.delete_media(42)
```

**Async version:**

```python
import asyncio
from py_strapi import AsyncClient, StrapiConfig

async def main():
    config = StrapiConfig(base_url="http://localhost:1337", api_token="your-token")

    async with AsyncClient(config) as client:
        # All methods have async equivalents
        media = await client.upload_file("image.jpg")
        content = await client.download_file(media.url)
        await client.delete_media(media.id)

asyncio.run(main())
```

**Media Features:**

- Upload single or multiple files
- Attach uploads to specific entities (articles, pages, etc.)
- Set metadata (alt text, captions)
- Download with streaming for large files
- Query media library with filters
- Update metadata without re-uploading
- Full support for both sync and async

## Dependency Injection

py-strapi supports full dependency injection for testability and customization. All dependencies have sensible defaults but can be overridden.

### Why DI?

- **Testability**: Inject mocks for unit testing without HTTP calls
- **Customization**: Provide custom parsers, auth handlers, or HTTP clients
- **Flexibility**: Share HTTP clients across multiple Strapi instances
- **Control**: Manage lifecycles of shared resources

### Basic DI Example

```python
from py_strapi import SyncClient, StrapiConfig
import httpx

config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token="your-token"
)

# Simple usage - all dependencies created automatically
with SyncClient(config) as client:
    response = client.get_many("articles")

# Advanced usage - inject custom HTTP client
shared_http = httpx.Client()
client1 = SyncClient(config, http_client=shared_http)
client2 = SyncClient(config, http_client=shared_http)
# Both share the same connection pool
```

### Injectable Dependencies

```python
from py_strapi import (
    SyncClient,
    AsyncClient,
    StrapiConfig,
    AuthProvider,
    HTTPClient,
    AsyncHTTPClient,
    ResponseParser,
    VersionDetectingParser,
)

# Custom authentication
class CustomAuth:
    def get_headers(self) -> dict[str, str]:
        return {"Authorization": "Custom token"}

    def validate_token(self) -> bool:
        return True

# Custom response parser
class CustomParser:
    def parse_single(self, response_data):
        # Custom parsing logic
        ...

    def parse_collection(self, response_data):
        # Custom parsing logic
        ...

# Inject custom dependencies
client = SyncClient(
    config,
    http_client=custom_http,      # Custom HTTP client
    auth=custom_auth,               # Custom auth provider
    parser=custom_parser            # Custom response parser
)
```

### Testing with DI

```python
from unittest.mock import Mock

# Create mock HTTP client for testing (no actual HTTP calls)
class MockHTTPClient:
    def __init__(self):
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url))
        # Return mock response
        mock_response = Mock()
        mock_response.is_success = True
        mock_response.json.return_value = {"data": []}
        return mock_response

    def close(self):
        pass

# Use mock in tests
mock_http = MockHTTPClient()
client = SyncClient(config, http_client=mock_http)

# Make requests (no actual HTTP)
client.get("articles")

# Verify mock was called
assert len(mock_http.requests) == 1
```

### Protocols (Type Interfaces)

py-strapi uses Python protocols for dependency interfaces:

- **`ConfigProvider`**: Configuration interface
- **`AuthProvider`**: Authentication interface
- **`HTTPClient`**: Sync HTTP client interface
- **`AsyncHTTPClient`**: Async HTTP client interface
- **`ResponseParser`**: Response parsing interface

All implementations satisfy these protocols and are type-checked with mypy.

**Example - Custom config from database**:
```python
class DatabaseConfig:
    """Load config from database."""

    def __init__(self, db):
        self.db = db

    def get_base_url(self) -> str:
        return self.db.query("SELECT url FROM config")[0]

    def get_api_token(self) -> str:
        return self.db.query("SELECT token FROM secrets")[0]

    # ... other properties

# Use database config
db_config = DatabaseConfig(db_connection)
client = SyncClient(db_config)
```

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/mehdizare/py-strapi.git
cd py-strapi

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies (uv is recommended for faster installs)
uv pip install -e ".[dev]"
# Or with pip
pip install -e ".[dev]"
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=py_strapi --cov-report=html

# Run specific test file
pytest tests/unit/test_client.py -v
```

### Code Quality

```bash
# Format code
ruff format src/ tests/

# Lint code
ruff check src/ tests/

# Type checking
mypy src/py_strapi/
```

## Project Status

This project is in active development. Currently implemented:

### ✅ Phase 1: Core Infrastructure (Complete)
- HTTP clients (sync and async)
- Configuration with Pydantic
- Authentication (API tokens)
- Exception hierarchy
- API version detection (v4/v5)

### ✅ Phase 2: Type-Safe Query Builder (Complete)
- **Request Models**: Filters (24 operators), sorting, pagination, population, field selection
- **Response Models**: V4/V5 parsing with automatic normalization
- **Query Builder**: `StrapiQuery` fluent API with full type safety
- **Typed Client Methods**: `get_one()`, `get_many()`, `create()`, `update()`, `remove()`
- **Dependency Injection**: Full DI support with protocols for testability
- **93% test coverage** with 196 passing tests

### 🚧 Phase 3-6: Advanced Features (Planned)
- Media upload/download handling
- Bulk operations with streaming
- Import/Export for migrations
- Content type introspection
- Advanced retry strategies
- Rate limiting

### Key Features
- **Type-Safe**: Full Pydantic validation and mypy strict mode compliance
- **Version Agnostic**: Works with both Strapi v4 and v5 seamlessly
- **24 Filter Operators**: Complete filtering support (eq, gt, contains, in, null, between, etc.)
- **Normalized Responses**: Consistent interface regardless of Strapi version
- **Dependency Injection**: Protocol-based DI for testability and customization
- **IDE Autocomplete**: Full type hints for excellent developer experience
- **Dual API**: Use typed methods for safety or raw methods for flexibility

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Development Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes and add tests
4. Run quality checks: `make pre-commit`
5. Commit your changes with conventional commits format
6. Push to your fork and submit a Pull Request

**Automated Reviews:** All PRs are automatically reviewed by CodeRabbit AI for code quality, security, and best practices.
