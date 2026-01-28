"""Exception hierarchy for py-strapi.

This module defines all custom exceptions used throughout the package,
organized in a clear hierarchy for better error handling.
"""

from typing import Any


class StrapiError(Exception):
    """Base exception for all py-strapi errors.

    All custom exceptions in this package inherit from this class,
    making it easy to catch all package-specific errors.
    """

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error message
            details: Optional dictionary with additional error context
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        """Return string representation of the error."""
        if self.details:
            return f"{self.message} (details: {self.details})"
        return self.message


# HTTP Status Code Related Errors


class AuthenticationError(StrapiError):
    """Raised when authentication fails (HTTP 401).

    This typically means the API token is invalid, expired, or missing.
    """

    pass


class AuthorizationError(StrapiError):
    """Raised when authorization fails (HTTP 403).

    The authentication was successful, but the user doesn't have
    permission to access the requested resource.
    """

    pass


class NotFoundError(StrapiError):
    """Raised when a resource is not found (HTTP 404).

    This can mean the content type, document ID, or endpoint doesn't exist.
    """

    pass


class ValidationError(StrapiError):
    """Raised when request validation fails (HTTP 400).

    This typically means the request data doesn't match the expected schema
    or contains invalid values.
    """

    pass


class ConflictError(StrapiError):
    """Raised when a conflict occurs (HTTP 409).

    This typically happens when trying to create a resource that already exists
    or when there's a version conflict during updates.
    """

    pass


class ServerError(StrapiError):
    """Raised when the server returns a 5xx error.

    This indicates an internal server error that is typically temporary
    and may succeed if retried.
    """

    def __init__(
        self, message: str, status_code: int, details: dict[str, Any] | None = None
    ) -> None:
        """Initialize server error with status code.

        Args:
            message: Human-readable error message
            status_code: HTTP status code (5xx)
            details: Optional dictionary with additional error context
        """
        super().__init__(message, details)
        self.status_code = status_code


# Network Related Errors


class NetworkError(StrapiError):
    """Base class for network-related errors.

    This is raised when there's a problem with the network connection
    rather than an HTTP error response.
    """

    pass


class ConnectionError(NetworkError):
    """Raised when a connection to the server cannot be established.

    This typically means the server is unreachable or the URL is incorrect.
    """

    pass


class TimeoutError(NetworkError):
    """Raised when a request times out.

    The server didn't respond within the configured timeout period.
    """

    pass


class RateLimitError(NetworkError):
    """Raised when rate limit is exceeded (HTTP 429).

    The client has sent too many requests in a given time period.
    """

    def __init__(
        self,
        message: str,
        retry_after: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize rate limit error.

        Args:
            message: Human-readable error message
            retry_after: Seconds to wait before retrying (from Retry-After header)
            details: Optional dictionary with additional error context
        """
        super().__init__(message, details)
        self.retry_after = retry_after


# Import/Export Related Errors


class ImportExportError(StrapiError):
    """Base class for import/export related errors.

    Raised during data export or import operations when something goes wrong.
    """

    pass


class FormatError(ImportExportError):
    """Raised when data format is invalid or unsupported.

    This happens when the import data doesn't match the expected format
    or contains malformed JSON/data structures.
    """

    pass


class RelationError(ImportExportError):
    """Raised when there's an error resolving or mapping relations.

    This can happen when:
    - A referenced document doesn't exist
    - Circular relations are detected
    - Relation format is invalid
    """

    pass


class MediaError(ImportExportError):
    """Raised when there's an error handling media files.

    This can happen during:
    - Media file download (export)
    - Media file upload (import)
    - Invalid media references
    - File system errors
    """

    pass
