"""Exception classes for strapi-kit."""

from .errors import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    ConflictError,
    ConnectionError,
    FormatError,
    ImportExportError,
    MediaError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    RelationError,
    ServerError,
    StrapiError,
    TimeoutError,
    ValidationError,
)

__all__ = [
    "StrapiError",
    "ConfigurationError",
    "AuthenticationError",
    "AuthorizationError",
    "NotFoundError",
    "ValidationError",
    "ConflictError",
    "NetworkError",
    "ConnectionError",
    "TimeoutError",
    "RateLimitError",
    "ServerError",
    "ImportExportError",
    "FormatError",
    "RelationError",
    "MediaError",
]
