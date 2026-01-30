"""py-strapi: A modern Python client for Strapi CMS.

This package provides a comprehensive interface for interacting with
Strapi v4 and v5 APIs, including:
- Synchronous and asynchronous clients
- Full CRUD operations
- Import/export functionality
- Type-safe data models with Pydantic
- Automatic retry and rate limiting
"""

from .__version__ import __version__
from .client import AsyncClient, SyncClient
from .exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    FormatError,
    ImportExportError,
    MediaError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    RelationError,
    ServerError,
    StrapiError,
    ValidationError,
)
from .models import StrapiConfig
from .parsers import VersionDetectingParser
from .protocols import (
    AsyncHTTPClient,
    AuthProvider,
    ConfigProvider,
    HTTPClient,
    ResponseParser,
)

__all__ = [
    "__version__",
    # Clients
    "SyncClient",
    "AsyncClient",
    # Configuration
    "StrapiConfig",
    # Protocols (for dependency injection)
    "AuthProvider",
    "ConfigProvider",
    "HTTPClient",
    "AsyncHTTPClient",
    "ResponseParser",
    # Parsers
    "VersionDetectingParser",
    # Exceptions
    "StrapiError",
    "AuthenticationError",
    "AuthorizationError",
    "NotFoundError",
    "ValidationError",
    "ConflictError",
    "NetworkError",
    "RateLimitError",
    "ServerError",
    "ImportExportError",
    "FormatError",
    "RelationError",
    "MediaError",
]
