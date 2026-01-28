# py-strapi

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
pip install py-strapi
```

For development:

```bash
pip install py-strapi[dev]
```

## Quick Start

### Synchronous Usage

```python
from py_strapi import SyncClient, StrapiConfig

# Configure client
config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token="your-api-token"
)

# Use client
with SyncClient(config) as client:
    # Get all articles
    response = client.get("articles")
    print(response)
```

### Asynchronous Usage

```python
import asyncio
from py_strapi import AsyncClient, StrapiConfig

async def main():
    config = StrapiConfig(
        base_url="http://localhost:1337",
        api_token="your-api-token"
    )

    async with AsyncClient(config) as client:
        response = await client.get("articles")
        print(response)

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

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/mehdizare/py-strapi.git
cd py-strapi

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
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

- ✅ HTTP clients (sync and async)
- ✅ Configuration with Pydantic
- ✅ Authentication (API tokens)
- ✅ Exception hierarchy
- ✅ API version detection (v4/v5)
- 🚧 CRUD operations (in progress)
- 🚧 Import/Export (planned)
- 🚧 Media handling (planned)

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
