# Configuration

## StrapiConfig

All configuration is handled through the `StrapiConfig` class using Pydantic Settings.

## Basic Configuration

```python
from py_strapi import StrapiConfig

config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token="your-api-token"
)
```

## All Configuration Options

```python
config = StrapiConfig(
    # Required
    base_url="http://localhost:1337",      # Strapi instance URL
    api_token="your-token",                 # API token for authentication

    # Optional
    api_version="auto",                     # "auto", "v4", or "v5"
    timeout=30.0,                           # Request timeout in seconds
    max_connections=10,                     # Maximum concurrent connections

    # Retry configuration
    retry_max_attempts=3,
    retry_multiplier=1.0,
    retry_min_wait=1.0,
    retry_max_wait=10.0,
)
```

## Environment Variables

All configuration can be set via environment variables with the `STRAPI_` prefix:

```bash
export STRAPI_BASE_URL="http://localhost:1337"
export STRAPI_API_TOKEN="your-token"
export STRAPI_API_VERSION="auto"
export STRAPI_TIMEOUT="30"
export STRAPI_MAX_CONNECTIONS="10"
export STRAPI_RETRY_MAX_ATTEMPTS="3"
```

Then create config without parameters:

```python
config = StrapiConfig()  # Loads from environment
```

## .env File Support

Create a `.env` file in your project root:

```bash
STRAPI_BASE_URL=http://localhost:1337
STRAPI_API_TOKEN=your-token-here
STRAPI_API_VERSION=auto
STRAPI_TIMEOUT=30
```

## API Version Detection

The `api_version` setting controls how py-strapi detects your Strapi version:

- `"auto"` (default): Automatically detects v4 or v5 from first response
- `"v4"`: Forces Strapi v4 format
- `"v5"`: Forces Strapi v5 format

## Timeouts

The `timeout` setting controls how long to wait for responses:

```python
config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token="your-token",
    timeout=60.0  # 60 seconds
)
```

## Connection Pooling

Control concurrent connections:

```python
config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token="your-token",
    max_connections=20  # Allow up to 20 concurrent connections
)
```

## Retry Configuration

Configure automatic retry behavior:

```python
config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token="your-token",
    retry_max_attempts=5,      # Retry up to 5 times
    retry_min_wait=2.0,        # Start with 2 second wait
    retry_max_wait=30.0,       # Max 30 seconds between retries
    retry_multiplier=2.0,      # Exponential backoff multiplier
)
```

## Next Steps

- [Client Documentation](guide/clients.md)
- [Error Handling](guide/errors.md)
