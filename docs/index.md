# strapi-kit

A modern Python client for Strapi CMS with comprehensive import/export capabilities.

## Features

- 🚀 **Full Strapi Support**: Works with both v4 and v5 APIs with automatic version detection
- ⚡ **Async & Sync**: Choose between synchronous and asynchronous clients based on your needs
- 🔒 **Type Safe**: Built with Pydantic for robust data validation and type safety
- 🔄 **Import/Export**: Comprehensive backup/restore and data migration tools
- 🔁 **Smart Retry**: Automatic retry with exponential backoff for transient failures
- 📦 **Modern Python**: Built for Python 3.12+ with full type hints

## Quick Example

### Synchronous

```python
from py_strapi import SyncClient, StrapiConfig

config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token="your-api-token"
)

with SyncClient(config) as client:
    response = client.get("articles")
    print(response)
```

### Asynchronous

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

## Installation

```bash
pip install strapi-kit
```

For development:

```bash
pip install strapi-kit[dev]
```

## Documentation

- [Installation Guide](installation.md)
- [Quick Start](quickstart.md)
- [Configuration](configuration.md)
- [API Reference](api/client.md)
- [Examples](examples/basic.md)

## Project Status

This project is in active development. See [IMPLEMENTATION_STATUS.md](https://github.com/mehdizare/strapi-kit/blob/main/IMPLEMENTATION_STATUS.md) for detailed progress.

Currently implemented:
- ✅ HTTP clients (sync and async)
- ✅ Configuration with Pydantic
- ✅ Authentication (API tokens)
- ✅ Exception hierarchy
- ✅ API version detection (v4/v5)
- 🚧 CRUD operations (in progress)
- 🚧 Import/Export (planned)

## Contributing

Contributions are welcome! Please see the [Contributing Guide](development/contributing.md) for details.

## License

MIT License - see [LICENSE](https://github.com/mehdizare/strapi-kit/blob/main/LICENSE) for details.
