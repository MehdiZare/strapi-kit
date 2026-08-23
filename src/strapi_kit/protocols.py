"""Protocol definitions for dependency injection.

This module defines interfaces for core components, enabling:
- Dependency injection
- Easy mocking in tests
- Loose coupling between components
- Custom implementations
"""

from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

import httpx

from .models.response.normalized import (
    NormalizedCollectionResponse,
    NormalizedSingleResponse,
)

if TYPE_CHECKING:
    from .models.schema import ContentTypeSchema


@runtime_checkable
class AuthProvider(Protocol):
    """Protocol for authentication providers.

    Implementations must provide methods to generate auth headers
    and validate credentials.
    """

    def get_headers(self) -> dict[str, str]:
        """Get authentication headers for HTTP requests.

        Returns:
            Dictionary with authentication headers (e.g., Authorization: Bearer ...)
        """
        ...

    def validate_token(self) -> bool:
        """Validate that authentication credentials are valid.

        Returns:
            True if credentials are valid, False otherwise
        """
        ...
