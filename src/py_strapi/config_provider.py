"""Configuration provider and factory for dependency injection.

This module provides a flexible way to create StrapiConfig instances from
various sources (environment variables, .env files, dictionaries, etc.).
"""

from pathlib import Path
from typing import Any

from pydantic import SecretStr, ValidationError

from .exceptions import StrapiError
from .models.config import RetryConfig, StrapiConfig


class ConfigurationError(StrapiError):
    """Raised when configuration cannot be loaded or is invalid.

    Inherits from StrapiError for consistent exception handling.
    """

    def __init__(self, message: str) -> None:
        """Initialize ConfigurationError.

        Args:
            message: Human-readable error message
        """
        super().__init__(message, details=None)


class ConfigFactory:
    """Factory for creating StrapiConfig instances from various sources.

    This class provides a flexible dependency injection pattern for configuration,
    allowing configs to be loaded from:
    - Environment variables
    - .env files (with custom paths)
    - Dictionaries
    - Default values

    Examples:
        >>> # Load from .env file in current directory
        >>> config = ConfigFactory.from_env()

        >>> # Load from custom .env file
        >>> config = ConfigFactory.from_env_file("/path/to/.env")

        >>> # Load from dictionary
        >>> config = ConfigFactory.from_dict({
        ...     "base_url": "http://localhost:1337",
        ...     "api_token": "secret-token"
        ... })

        >>> # Load with custom search paths
        >>> config = ConfigFactory.from_env(
        ...     search_paths=[".env", ".env.local", "~/.strapi/.env"]
        ... )

        >>> # Create with explicit values (no .env loading)
        >>> config = ConfigFactory.create(
        ...     base_url="http://localhost:1337",
        ...     api_token="secret-token"
        ... )
    """

    @staticmethod
    def from_env(
        *,
        search_paths: list[str | Path] | None = None,
        required: bool = False,
    ) -> StrapiConfig:
        """Load configuration from environment variables and .env files.

        Searches for .env files in the specified paths and loads the first one found.
        Environment variables always take precedence over .env file values.

        Args:
            search_paths: List of paths to search for .env files
                         (default: [".env", ".env.local", "~/.config/strapi/.env"])
            required: If True, raises ConfigurationError if no .env file is found

        Returns:
            Configured StrapiConfig instance

        Raises:
            ConfigurationError: If required=True and no .env file found, or validation fails
            ValidationError: If configuration values are invalid

        Example:
            >>> config = ConfigFactory.from_env(
            ...     search_paths=[".env", ".env.production"],
            ...     required=True
            ... )
        """
        if search_paths is None:
            search_paths = [
                ".env",
                ".env.local",
                Path.home() / ".config" / "strapi" / ".env",
            ]

        # Find first existing .env file
        env_file = None
        for path in search_paths:
            resolved_path = Path(path).expanduser().resolve()
            if resolved_path.exists():
                env_file = resolved_path
                break

        if required and env_file is None:
            searched = [str(Path(p).expanduser().resolve()) for p in search_paths]
            raise ConfigurationError(f"No .env file found. Searched: {', '.join(searched)}")

        try:
            # Load with custom env_file path
            if env_file:
                return StrapiConfig(_env_file=str(env_file))  # type: ignore[call-arg]
            else:
                # Load from environment variables only
                return StrapiConfig(_env_file=None)  # type: ignore[call-arg]

        except ValidationError as e:
            raise ConfigurationError(f"Invalid configuration: {e.error_count()} errors\n{e}") from e

    @staticmethod
    def from_env_file(
        env_file: str | Path,
        *,
        required: bool = True,
    ) -> StrapiConfig:
        """Load configuration from a specific .env file.

        Args:
            env_file: Path to the .env file
            required: If True, raises error if file doesn't exist

        Returns:
            Configured StrapiConfig instance

        Raises:
            ConfigurationError: If file doesn't exist (when required=True) or validation fails
            ValidationError: If configuration values are invalid

        Example:
            >>> config = ConfigFactory.from_env_file("/etc/strapi/.env")
        """
        resolved_path = Path(env_file).expanduser().resolve()

        if required and not resolved_path.exists():
            raise ConfigurationError(f".env file not found: {resolved_path}")

        try:
            return StrapiConfig(  # type: ignore[call-arg]
                _env_file=str(resolved_path) if resolved_path.exists() else None
            )
        except ValidationError as e:
            raise ConfigurationError(
                f"Invalid configuration in {resolved_path}: {e.error_count()} errors\n{e}"
            ) from e

    @staticmethod
    def from_dict(config_dict: dict[str, Any]) -> StrapiConfig:
        """Create configuration from a dictionary.

        Args:
            config_dict: Dictionary with configuration values

        Returns:
            Configured StrapiConfig instance

        Raises:
            ConfigurationError: If validation fails
            ValidationError: If configuration values are invalid

        Example:
            >>> config = ConfigFactory.from_dict({
            ...     "base_url": "http://localhost:1337",
            ...     "api_token": "secret-token",
            ...     "timeout": 60.0,
            ...     "retry": {
            ...         "max_attempts": 5,
            ...         "initial_wait": 2.0
            ...     }
            ... })
        """
        try:
            # Disable .env loading when creating from dict
            return StrapiConfig(_env_file=None, **config_dict)  # type: ignore[call-arg]
        except ValidationError as e:
            raise ConfigurationError(f"Invalid configuration: {e.error_count()} errors\n{e}") from e

    @staticmethod
    def create(
        *,
        base_url: str,
        api_token: str,
        api_version: str = "auto",
        timeout: float = 30.0,
        max_connections: int = 10,
        retry: RetryConfig | dict[str, Any] | None = None,
        rate_limit_per_second: float | None = None,
        verify_ssl: bool = True,
    ) -> StrapiConfig:
        """Create configuration with explicit values (no .env loading).

        Args:
            base_url: Base URL of Strapi instance
            api_token: API authentication token
            api_version: API version (v4, v5, or auto)
            timeout: Request timeout in seconds
            max_connections: Maximum concurrent connections
            retry: Retry configuration (RetryConfig instance or dict)
            rate_limit_per_second: Maximum requests per second
            verify_ssl: Whether to verify SSL certificates

        Returns:
            Configured StrapiConfig instance

        Raises:
            ConfigurationError: If validation fails

        Example:
            >>> config = ConfigFactory.create(
            ...     base_url="http://localhost:1337",
            ...     api_token="secret-token",
            ...     timeout=60.0
            ... )
        """
        try:
            # Convert retry dict to RetryConfig if needed
            retry_config: RetryConfig
            if retry is None:
                retry_config = RetryConfig()
            elif isinstance(retry, dict):
                retry_config = RetryConfig(**retry)
            else:
                retry_config = retry

            return StrapiConfig(  # type: ignore[call-arg]
                _env_file=None,  # Disable .env loading
                base_url=base_url,
                api_token=SecretStr(api_token),
                api_version=api_version,  # type: ignore[arg-type]
                timeout=timeout,
                max_connections=max_connections,
                retry=retry_config,
                rate_limit_per_second=rate_limit_per_second,
                verify_ssl=verify_ssl,
            )
        except ValidationError as e:
            raise ConfigurationError(f"Invalid configuration: {e.error_count()} errors\n{e}") from e

    @staticmethod
    def from_environment_only() -> StrapiConfig:
        """Load configuration from environment variables only (no .env files).

        This is useful in containerized environments where configuration
        is injected via environment variables.

        Returns:
            Configured StrapiConfig instance

        Raises:
            ConfigurationError: If validation fails

        Example:
            >>> # Set env vars first:
            >>> # export STRAPI_BASE_URL=http://localhost:1337
            >>> # export STRAPI_API_TOKEN=secret-token
            >>> config = ConfigFactory.from_environment_only()
        """
        try:
            return StrapiConfig(_env_file=None)  # type: ignore[call-arg]
        except ValidationError as e:
            raise ConfigurationError(
                f"Invalid configuration from environment: {e.error_count()} errors\n{e}"
            ) from e

    @staticmethod
    def merge(
        *configs: StrapiConfig,
        base: StrapiConfig | None = None,
    ) -> StrapiConfig:
        """Merge multiple configurations with later configs overriding earlier ones.

        Args:
            *configs: Configuration instances to merge
            base: Optional base configuration (merged first)

        Returns:
            Merged StrapiConfig instance

        Example:
            >>> base_config = ConfigFactory.from_env_file("base.env")
            >>> override_config = ConfigFactory.from_dict({"timeout": 60.0})
            >>> final_config = ConfigFactory.merge(base_config, override_config)
        """
        if not configs and base is None:
            raise ValueError("At least one config must be provided")

        all_configs = [base] if base else []
        all_configs.extend(configs)

        # Start with first config's dict
        merged_dict: dict[str, Any] = all_configs[0].model_dump(exclude_unset=False)

        # Merge each subsequent config
        for config in all_configs[1:]:
            config_dict = config.model_dump(exclude_unset=True)
            merged_dict.update(config_dict)

        return ConfigFactory.from_dict(merged_dict)


# Convenience functions for common patterns


def load_config(
    env_file: str | Path | None = None,
    *,
    required: bool = False,
) -> StrapiConfig:
    """Convenience function to load configuration.

    Args:
        env_file: Optional path to .env file (searches defaults if None)
        required: If True, raises error if no .env file found

    Returns:
        Configured StrapiConfig instance

    Example:
        >>> # Load from default locations
        >>> config = load_config()

        >>> # Load from specific file
        >>> config = load_config("/path/to/.env")

        >>> # Require .env file
        >>> config = load_config(required=True)
    """
    if env_file:
        return ConfigFactory.from_env_file(env_file, required=required)
    return ConfigFactory.from_env(required=required)


def create_config(
    base_url: str,
    api_token: str,
    **kwargs: Any,
) -> StrapiConfig:
    """Convenience function to create configuration with explicit values.

    Args:
        base_url: Base URL of Strapi instance
        api_token: API authentication token
        **kwargs: Additional configuration options

    Returns:
        Configured StrapiConfig instance

    Example:
        >>> config = create_config(
        ...     base_url="http://localhost:1337",
        ...     api_token="secret-token",
        ...     timeout=60.0
        ... )
    """
    return ConfigFactory.create(base_url=base_url, api_token=api_token, **kwargs)
