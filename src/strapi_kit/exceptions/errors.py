"""Exception hierarchy for strapi-kit.

This module defines all custom exceptions used throughout the package,
organized in a clear hierarchy for better error handling.
"""

from typing import Any


class StrapiError(Exception):
    """Base exception for all strapi-kit errors.

    All custom exceptions in this package inherit from this class,
    making it easy to catch all package-specific errors.
    """

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        *,
        status_code: int | None = None,
    ) -> None:
        """Initialize the exception.

        Args:
            message: Human-readable error message
            details: Optional dictionary with additional error context
            status_code: HTTP status when this error came from a response
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.status_code = status_code

    def __str__(self) -> str:
        """Return string representation of the error."""
        if self.details:
            return f"{self.message} (details: {self.details})"
        return self.message


class ConfigurationError(StrapiError):
    """Raised when configuration is invalid or cannot be loaded.

    This includes:
    - Missing required configuration values
    - Invalid configuration values (wrong types, out of range)
    - Invalid URLs or authentication tokens
    - Failed .env file loading
    """

    pass


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
    """Raised when request validation fails (HTTP 400 or 422).

    This typically means the request data doesn't match the expected schema
    or contains invalid values. Client-side query/argument checks use the
    same type (no HTTP status).

    Strapi unique-index collisions also arrive as HTTP 400 or 422 with this
    type. Use :func:`is_uniqueness_violation` to distinguish them from
    malformed payloads, and :attr:`field_errors` /
    :func:`format_validation_errors` to read per-field messages from
    ``details["errors"]``.
    """

    @property
    def field_errors(self) -> list[tuple[str, str]]:
        """Parsed field-level errors as ``(path, message)`` pairs.

        Reads ``details["errors"]``. Empty messages are skipped. Returns an
        empty list when there are no nested field errors.
        """
        return _parse_field_errors(self.details)


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
        super().__init__(message, details, status_code=status_code)


class MethodNotAllowedError(StrapiError):
    """Raised when the HTTP method is not allowed (HTTP 405).

    Typical for a missing or disabled Strapi route (for example a
    Draft & Publish action on a type that does not support it).
    """

    pass


class UnstructuredResponseError(StrapiError):
    """Raised when a 2xx response is empty or not a JSON object.

    Strapi REST should return a JSON object for entry writes. Some
    proxies or custom controllers return an empty body or a bare
    string such as ``"Created"``. Callers must not treat that as a
    successful entity — there is no ``documentId`` to continue with.
    """

    pass


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
        super().__init__(message, details, status_code=429)
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


# ValidationError helpers (unique-index 400s stay ValidationError, not ConflictError)


_UNIQUENESS_SUBSTRING = "must be unique"


def _format_error_path(path: object) -> str:
    """Normalize a Strapi error path to a dotted string."""
    if isinstance(path, str):
        return path
    if isinstance(path, (list, tuple)):
        return ".".join(str(part) for part in path)
    if path is None:
        return ""
    return str(path)


def _parse_field_errors(details: object) -> list[tuple[str, str]]:
    """Extract ``(path, message)`` pairs from ``details["errors"]``.

    Returns an empty list when ``details`` is not a mapping (HTTP payloads
    are normally a dict, but a non-dict ``error.details`` must not raise).
    """
    if not isinstance(details, dict):
        return []
    errors = details.get("errors")
    if not isinstance(errors, list):
        return []

    parsed: list[tuple[str, str]] = []
    for entry in errors:
        if not isinstance(entry, dict):
            continue
        message = entry.get("message")
        if not isinstance(message, str) or not message.strip():
            continue
        parsed.append((_format_error_path(entry.get("path")), message))
    return parsed


def is_uniqueness_violation(exc: ValidationError) -> bool:
    """Return True if ``exc`` is a Strapi unique-index collision.

    True when any ``exc.details["errors"]`` entry has a message containing
    ``must be unique`` (case-insensitive), or when ``exc.message`` itself
    contains that substring (details-less variants). ``str(exc)`` is not
    used: it dumps ``details`` and would false-positive on unrelated keys.

    HTTP status is not inspected beyond ``exc`` already being a
    :class:`ValidationError`. Other 400/422s (required fields, type errors)
    return False.

    Args:
        exc: Validation error raised from a Strapi 400 or 422 response.

    Returns:
        Whether the error represents a uniqueness constraint violation.
    """
    for _path, message in exc.field_errors:
        if _UNIQUENESS_SUBSTRING in message.lower():
            return True
    return _UNIQUENESS_SUBSTRING in exc.message.lower()


def format_validation_errors(exc: ValidationError) -> str | None:
    """Flatten ``details.errors`` to ``path: message`` lines.

    ``path`` may be a list (``["slug"]`` → ``slug``) or a string. Nested
    list paths are joined with ``.``. Empty messages are skipped. Entries
    with an empty path emit just the message (no leading ``: ``).

    Args:
        exc: Validation error raised from a Strapi 400 or 422 response.

    Returns:
        Newline-joined ``path: message`` lines, or ``None`` when there
        are no nested field errors (caller should keep ``str(exc)``).
    """
    lines = [f"{path}: {message}" if path else message for path, message in exc.field_errors]
    if not lines:
        return None
    return "\n".join(lines)
