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

py-strapi provides flexible configuration options through dependency injection:

### 1. Using .env Files (Recommended for Development)

Create a `.env` file in your project root:

```bash
# .env
STRAPI_BASE_URL=http://localhost:1337
STRAPI_API_TOKEN=your-api-token-here
STRAPI_TIMEOUT=30.0
STRAPI_MAX_CONNECTIONS=10
STRAPI_RETRY_MAX_ATTEMPTS=3
```

Then load it automatically:

```python
from py_strapi import load_config, SyncClient

# Automatically searches for .env, .env.local, or ~/.config/strapi/.env
config = load_config()

with SyncClient(config) as client:
    response = client.get("articles")
```

### 2. Using Environment Variables (Recommended for Production)

Perfect for containerized deployments (Docker, Kubernetes):

```bash
export STRAPI_BASE_URL=https://api.production.com
export STRAPI_API_TOKEN=production-secret-token
export STRAPI_TIMEOUT=120.0
export STRAPI_MAX_CONNECTIONS=100
```

```python
from py_strapi import ConfigFactory, SyncClient

# Load from environment variables only (no .env files)
config = ConfigFactory.from_environment_only()

with SyncClient(config) as client:
    response = client.get("articles")
```

### 3. Explicit Configuration (Recommended for Testing)

Create configuration programmatically:

```python
from py_strapi import create_config, SyncClient

config = create_config(
    base_url="http://localhost:1337",
    api_token="your-token",
    timeout=60.0,
    max_connections=50,
    verify_ssl=True
)

with SyncClient(config) as client:
    response = client.get("articles")
```

### 4. Advanced Configuration Patterns

#### Custom .env File Location

```python
from py_strapi import ConfigFactory

# Load from specific file
config = ConfigFactory.from_env_file("/path/to/custom.env")

# Search multiple locations
config = ConfigFactory.from_env(
    search_paths=[
        ".env.local",      # Local overrides (highest priority)
        ".env",            # Base config
        "~/.strapi/.env"   # User config (lowest priority)
    ]
)
```

#### Layered Configuration (Development → Production)

```python
from py_strapi import ConfigFactory

# Base configuration from .env file
base_config = ConfigFactory.from_env_file(".env")

# Override specific values for production
production_overrides = ConfigFactory.from_dict({
    "base_url": "https://api.production.com",
    "api_token": "production-token",
    "timeout": 120.0,
    "max_connections": 100
})

# Merge configs (later configs override earlier ones)
final_config = ConfigFactory.merge(base_config, production_overrides)
```

#### Retry Configuration

Configure automatic retry behavior:

```python
from py_strapi import StrapiConfig, RetryConfig

config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token="your-token",
    retry=RetryConfig(
        max_attempts=5,           # Retry up to 5 times
        initial_wait=2.0,         # Wait 2 seconds before first retry
        max_wait=120.0,          # Maximum 2 minutes between retries
        exponential_base=3.0,    # Faster backoff growth
        retry_on_status={500, 502, 503, 504, 408}  # Retry on these status codes
    )
)
```

Or via environment variables:

```bash
STRAPI_RETRY_MAX_ATTEMPTS=5
STRAPI_RETRY_INITIAL_WAIT=2.0
STRAPI_RETRY_MAX_WAIT=120.0
STRAPI_RETRY_EXPONENTIAL_BASE=3.0
```

### Configuration Reference

All available options:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `base_url` | `str` | **Required** | Strapi instance URL |
| `api_token` | `str` | **Required** | API authentication token |
| `api_version` | `"v4" \| "v5" \| "auto"` | `"auto"` | API version (auto-detect or explicit) |
| `timeout` | `float` | `30.0` | Request timeout in seconds |
| `max_connections` | `int` | `10` | Maximum concurrent connections |
| `verify_ssl` | `bool` | `True` | Verify SSL certificates |
| `rate_limit_per_second` | `float \| None` | `None` | Rate limiting (None = unlimited) |
| `retry.max_attempts` | `int` | `3` | Maximum retry attempts (1-10) |
| `retry.initial_wait` | `float` | `1.0` | Initial retry wait time (seconds) |
| `retry.max_wait` | `float` | `60.0` | Maximum retry wait time (seconds) |
| `retry.exponential_base` | `float` | `2.0` | Exponential backoff multiplier |

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

### Export/Import with Relation Resolution

py-strapi provides comprehensive export/import functionality with automatic relation resolution for migrating content between Strapi instances.

```python
from py_strapi import StrapiConfig, StrapiExporter, StrapiImporter, SyncClient

# Export from source instance
source_config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token="source-token"
)

with SyncClient(source_config) as client:
    exporter = StrapiExporter(client)

    # Export content types with schemas for relation resolution
    export_data = exporter.export_content_types([
        "api::article.article",
        "api::author.author",
        "api::category.category"
    ])

    # Save to file
    exporter.save_to_file(export_data, "migration.json")

# Import to target instance
target_config = StrapiConfig(
    base_url="http://localhost:1338",
    api_token="target-token"
)

with SyncClient(target_config) as client:
    importer = StrapiImporter(client)

    # Load export
    export_data = StrapiExporter.load_from_file("migration.json")

    # Import with automatic relation resolution
    result = importer.import_data(export_data)

    print(f"Imported {result.entities_imported} entities")
    print(f"ID mapping: {result.id_mapping}")
```

**Export/Import Features:**

- **Automatic Relation Resolution**: Relations are automatically mapped using content type schemas
- **Schema Caching**: Content type metadata cached for fast relation lookups
- **ID Mapping**: Old IDs automatically mapped to new IDs during import
- **Media Support**: Export and import media files with content
- **Progress Tracking**: Optional callbacks for monitoring long operations
- **Dry Run Mode**: Test imports before executing
- **Conflict Resolution**: Configurable strategies for handling existing entities

**How Relation Resolution Works:**

1. During export, content type schemas are fetched from the Content-Type Builder API
2. Schemas include relation metadata (field types, targets)
3. During import, relations are resolved by looking up target content types from schemas
4. Old IDs are mapped to new IDs using the ID mapping table

For example, when importing an article with `{"author": [5]}`, the system:
- Looks up the schema to find that `author` targets `"api::author.author"`
- Maps old author ID 5 to the new ID in the target instance
- Updates the article with the resolved relation

See the [Export/Import Guide](docs/export-import.md) for complete documentation.

### Complete Migration Examples

We provide two complete migration examples for different use cases:

#### Simple Migration (Quick Start)

Perfect for straightforward migrations with known content types:

```bash
# 1. Edit examples/simple_migration.py with your configuration
# 2. Run the migration
python examples/simple_migration.py
```

Features:
- ✅ Single-file, easy to understand
- ✅ Migrates specific content types
- ✅ Includes media files
- ✅ Automatic relation resolution
- ✅ Saves backup to JSON

#### Full Migration (Production-Ready)

Comprehensive migration tool with auto-discovery and verification:

```bash
# Export all content from source
python examples/full_migration_v5.py export

# Import to target
python examples/full_migration_v5.py import

# Or do both in one command
python examples/full_migration_v5.py migrate

# Verify migration success
python examples/full_migration_v5.py verify
```

Features:
- ✅ **Auto-discovers all content types** (no manual configuration needed)
- ✅ Progress bars for long operations
- ✅ Detailed migration reports
- ✅ Entity count verification
- ✅ Error reporting and recovery
- ✅ Batch processing for large datasets
- ✅ ID mapping with detailed logs
- ✅ Media file handling with progress tracking

**Full Migration Example Output:**

```
🔍 Discovering content types...
   Found 12 content types:
   - api::article.article
   - api::author.author
   - api::category.category
   ...

📥 Exporting 12 content types...
[████████████████████████████████████████] 100% | Processing articles

✅ EXPORT COMPLETE
Content types exported: 12
Total entities exported: 1,847
Media files downloaded: 234
Total export size: 45.3 MB

📤 Importing 1,847 entities...
[████████████████████████████████████████] 100% | Importing articles

✅ IMPORT COMPLETE
Entities imported: 1,847
Media files uploaded: 234
Relations resolved: 3,421
```

Both examples include:
- SecretStr for secure token handling
- Proper error handling and reporting
- Progress tracking
- Automatic relation resolution using schemas
- Media file download/upload
- ID mapping for relations

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

# Install pre-commit hooks (one-time setup)
make install-hooks
# Or manually:
pre-commit install
```

### Pre-commit Hooks

This project uses pre-commit hooks to ensure code quality:

```bash
# Install pre-commit hooks (one-time setup)
make install-hooks

# Or manually:
pre-commit install

# Run hooks manually on all files
make run-hooks

# Update hooks to latest versions
make update-hooks
```

**What the hooks check:**
- ✅ Code formatting (ruff format)
- ✅ Linting (ruff check)
- ✅ Type checking (mypy strict mode)
- ✅ Security issues (bandit)
- ✅ Secrets detection (detect-secrets)
- ✅ File consistency (trailing whitespace, EOF, etc.)

**Skip hooks temporarily** (not recommended):
```bash
git commit --no-verify
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

# Security checks
make security

# Run all quality checks
make quality
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

### ✅ Phase 3: Media Operations (Complete)
- **Media Upload**: Single and batch file uploads with metadata
- **Media Download**: Streaming downloads for large files
- **Media Management**: List, get, update, and delete media
- **Entity Attachment**: Link media to specific content types
- **Full async support** for all media operations
- **100% test coverage** on media operations

### ✅ Phase 4: Export/Import (Complete)
- **Content Export**: Export content types with all entities
- **Automatic Relation Resolution**: Schema-based relation mapping
- **Media Export**: Download and package media files
- **Content Import**: Import with ID mapping and relation resolution
- **Schema Caching**: Efficient content type metadata handling
- **89% overall test coverage** with 355 passing tests

### 🚧 Phase 5-6: Advanced Features (Planned)
- Bulk operations with streaming
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
