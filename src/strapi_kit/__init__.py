"""strapi-kit: A modern Python client for Strapi CMS.

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
from .config_provider import (
    ConfigFactory,
    create_config,
    load_config,
)
from .exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    ConflictError,
    FormatError,
    ImportExportError,
    MediaError,
    MethodNotAllowedError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    RelationError,
    ServerError,
    StrapiError,
    UnstructuredResponseError,
    UnstructuredResponseReason,
    ValidationError,
    format_validation_errors,
    is_uniqueness_violation,
)
from .export import StrapiExporter, StrapiImporter
from .models import (
    BulkOperationFailure,
    BulkOperationResult,
    DocumentAction,
    DocumentStatus,
    FieldType,
    HttpMethod,
    PublicationFilter,
    PublicationState,
    QueryParam,
    RelationWriteOp,
    RetryConfig,
    StrapiConfig,
    relation_write,
)
from .operations.streaming import stream_entities, stream_entities_async
from .parsers import VersionDetectingParser
from .protocols import (
    AsyncHTTPClient,
    AuthProvider,
    ConfigProvider,
    HTTPClient,
    ResponseParser,
    SchemaProvider,
)
from .utils.blocks import MarkdownConversion, blocks_to_markdown, markdown_to_blocks
from .utils.endpoints import collection_endpoint, document_endpoint
from .utils.pagination import assert_pagination_echo

__all__ = [
    "__version__",
    # Clients
    "SyncClient",
    "AsyncClient",
    # Configuration
    "StrapiConfig",
    "RetryConfig",
    "DocumentStatus",
    "PublicationState",
    "PublicationFilter",
    "DocumentAction",
    "QueryParam",
    "HttpMethod",
    "FieldType",
    # Blocks ↔ Markdown
    "MarkdownConversion",
    "blocks_to_markdown",
    "markdown_to_blocks",
    "ConfigFactory",
    "load_config",
    "create_config",
    "ConfigurationError",
    # Bulk Operations
    "BulkOperationResult",
    "BulkOperationFailure",
    # Relation writes (Strapi 5)
    "RelationWriteOp",
    "relation_write",
    # Streaming
    "stream_entities",
    "stream_entities_async",
    # Pagination
    "assert_pagination_echo",
    # REST collection endpoints (from pluralName only)
    "collection_endpoint",
    "document_endpoint",
    # Export/Import
    "StrapiExporter",
    "StrapiImporter",
    # Protocols (for dependency injection)
    "AuthProvider",
    "ConfigProvider",
    "HTTPClient",
    "AsyncHTTPClient",
    "ResponseParser",
    "SchemaProvider",
    # Parsers
    "VersionDetectingParser",
    # Exceptions
    "StrapiError",
    "AuthenticationError",
    "AuthorizationError",
    "NotFoundError",
    "ValidationError",
    "is_uniqueness_violation",
    "format_validation_errors",
    "ConflictError",
    "MethodNotAllowedError",
    "UnstructuredResponseError",
    "UnstructuredResponseReason",
    "NetworkError",
    "RateLimitError",
    "ServerError",
    "ImportExportError",
    "FormatError",
    "RelationError",
    "MediaError",
]
