# Quick Start

## Basic Setup

### 1. Install py-strapi

```bash
pip install py-strapi
```

### 2. Configure Your Client

```python
from py_strapi import StrapiConfig

config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token="your-api-token"
)
```

### 3. Make Your First Request

=== "Synchronous"

    ```python
    from py_strapi import SyncClient

    with SyncClient(config) as client:
        # Get all articles
        articles = client.get("articles")
        print(articles)
    ```

=== "Asynchronous"

    ```python
    import asyncio
    from py_strapi import AsyncClient

    async def main():
        async with AsyncClient(config) as client:
            articles = await client.get("articles")
            print(articles)

    asyncio.run(main())
    ```

## Environment Variables

Instead of hardcoding credentials, use environment variables:

```bash
export STRAPI_BASE_URL="http://localhost:1337"
export STRAPI_API_TOKEN="your-api-token"
```

Then create config without parameters:

```python
from py_strapi import StrapiConfig

# Loads from environment variables
config = StrapiConfig()
```

## Next Steps

- [Configuration Guide](configuration.md)
- [Client Documentation](guide/clients.md)
- [More Examples](examples/basic.md)
