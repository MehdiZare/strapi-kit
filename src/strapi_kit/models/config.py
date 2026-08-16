"""Configuration models for strapi-kit.

This module defines the configuration structure using Pydantic for
type safety and validation with support for environment variables.
"""

from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RetryConfig(BaseSettings):
    """Configuration for retry behavior.

    Controls how the client handles failed requests with exponential backoff.
    """

    model_config = SettingsConfigDict(
        env_prefix="STRAPI_RETRY_",
        extra="ignore",
    )

    max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of retry attempts for failed requests",
    )

    initial_wait: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="Initial wait time in seconds before first retry",
    )

    max_wait: float = Field(
        default=60.0,
        ge=1.0,
        le=300.0,
        description="Maximum wait time in seconds between retries",
    )

    exponential_base: float = Field(
        default=2.0,
        ge=1.1,
        le=10.0,
        description="Exponential backoff multiplier",
    )

    retry_on_status: set[int] = Field(
        default_factory=lambda: {500, 502, 503, 504},
        description="HTTP status codes that should trigger a retry",
    )


class StrapiConfig(BaseSettings):
    """Main configuration for the Strapi client.

    This configuration can be loaded from environment variables with
    the STRAPI_ prefix or passed directly as arguments.

    Example:
        ```python
        # From environment variables
        config = StrapiConfig()

        # From arguments
        config = StrapiConfig(
            base_url="http://localhost:1337",
            api_token="your-token-here"
        )
        ```
    """

    model_config = SettingsConfigDict(
        env_prefix="STRAPI_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    base_url: str = Field(
        ...,
        description=(
            "Base URL of the Strapi instance (e.g., http://localhost:1337). "
            "A trailing /api segment is stripped."
        ),
    )

    api_token: SecretStr = Field(
        ...,
        description="API token for authentication",
    )

    api_version: Literal["v4", "v5", "auto"] = Field(
        default="auto",
        description="Strapi API version to use (v4, v5, or auto-detect)",
    )

    timeout: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
        description="Request timeout in seconds",
    )

    max_connections: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of concurrent connections",
    )

    retry: RetryConfig = Field(
        default_factory=RetryConfig,
        description="Retry configuration",
    )

    rate_limit_per_second: float | None = Field(
        default=None,
        ge=0.1,
        description="Maximum requests per second (None for unlimited)",
    )

    verify_ssl: bool = Field(
        default=True,
        description="Whether to verify SSL certificates",
    )

    @field_validator("base_url", mode="before")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Validate URL format and strip a trailing ``/api`` segment.

        Operators often paste the REST root shown in Strapi docs
        (``https://cms.example.com/api``). The client always prefixes
        content endpoints with ``api/``, so a trailing ``/api`` on
        ``base_url`` would produce ``/api/api/...``. Only the final
        path segment is removed; ``/api`` in the middle of a path
        (``https://host/api/v1``) and ``/admin`` are left intact.

        Args:
            v: URL string to validate.

        Returns:
            Validated URL without a trailing slash or trailing ``/api``.

        Raises:
            ValueError: If URL is not a valid HTTP(S) URL.
        """
        if not isinstance(v, str):
            raise ValueError("base_url must be a string")

        url_str = v.strip().rstrip("/")

        # Validate URL format
        if not url_str:
            raise ValueError("base_url cannot be empty")

        if not url_str.startswith(("http://", "https://")):
            raise ValueError(f"base_url must start with http:// or https://, got: {url_str[:50]}")

        # Use urlsplit for robust URL validation
        parsed = urlsplit(url_str)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid URL format (missing host): {url_str[:50]}")

        # Drop a final "api" path segment only (not /api/v1, not /admin).
        # Path-level rstrip so "/api/" still matches when a query/fragment
        # prevented the whole-string rstrip above from seeing the slash.
        path = parsed.path.rstrip("/")
        if path.rsplit("/", 1)[-1] == "api":
            trimmed_path = path[: -len("/api")].rstrip("/")
            url_str = urlunsplit(
                (parsed.scheme, parsed.netloc, trimmed_path, parsed.query, parsed.fragment)
            ).rstrip("/")

        return url_str

    def get_api_token(self) -> str:
        """Get the API token as a plain string.

        Returns:
            The API token value
        """
        return self.api_token.get_secret_value()

    def get_base_url(self) -> str:
        """Get the base URL as a plain string.

        Returns:
            The base URL value
        """
        return self.base_url
