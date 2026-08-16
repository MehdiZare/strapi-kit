# strapi-kit

A modern Python client for Strapi CMS with comprehensive import/export capabilities.

## Features

- 🚀 **Full Strapi Support**: Works with both v4 and v5 APIs with automatic version detection
- ⚡ **Async & Sync**: Choose between synchronous and asynchronous clients based on your needs
- 🔒 **Type Safe**: Built with Pydantic for robust data validation and type safety
- 🔄 **Import/Export**: Comprehensive backup/restore and data migration tools
- 🔁 **Smart Retry**: Automatic retry with exponential backoff for transient failures
- 🔍 **Schema Introspection**: Content-Type Builder API support for schema discovery
- 📝 **Blocks ↔ Markdown**: Convert Strapi v5 `blocks` rich text JSON to and from Markdown
- 📦 **Modern Python**: Built for Python 3.12+ with full type hints

## Quick Example

### Synchronous

```python
from strapi_kit import SyncClient, StrapiConfig

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
from strapi_kit import AsyncClient, StrapiConfig

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
- [Type-Safe Queries](models.md)
- [Media Operations](media.md)
- [Export/Import](export-import.md)
- [Changelog](changelog.md)

## Project Status

0.2.0 is the Strapi 5 connector surface (Draft & Publish, Content-Type
Builder discovery, origin-path probe, relation writes, blocks ↔ markdown,
complete stream/export). See the [changelog](changelog.md) and
[release process](development/release-process.md).

Currently implemented:
- ✅ HTTP clients (sync and async)
- ✅ Configuration with Pydantic
- ✅ Authentication (API tokens)
- ✅ Exception hierarchy
- ✅ API version detection (v4/v5)
- ✅ Typed CRUD, `exists()`, and v5 document actions
- ✅ Content-Type Builder discovery and collection path helpers
- ✅ Import/Export with automatic relation resolution
- ✅ Blocks ↔ Markdown converters

## Contributing

Contributions are welcome! Please see the [Contributing Guide](development/contributing.md) for details.

## License

MIT License - see [LICENSE](https://github.com/mehdizare/strapi-kit/blob/main/LICENSE) for details.
