"""Verify py-strapi installation and basic functionality.

This script verifies that the package is properly installed and
can be imported without errors.
"""

from py_strapi import (
    AsyncClient,
    AuthenticationError,
    StrapiConfig,
    StrapiError,
    SyncClient,
    __version__,
)


def verify_imports() -> None:
    """Verify all imports work correctly."""
    print("Verifying imports...")

    # Check version
    print(f"  py-strapi version: {__version__}")

    # Check clients
    assert SyncClient is not None
    assert AsyncClient is not None
    print("  Clients: OK")

    # Check config
    assert StrapiConfig is not None
    print("  Configuration: OK")

    # Check exceptions
    assert StrapiError is not None
    assert AuthenticationError is not None
    print("  Exceptions: OK")


def verify_config() -> None:
    """Verify configuration creation."""
    print("\nVerifying configuration...")

    # Create config
    config = StrapiConfig(
        base_url="http://localhost:1337",
        api_token="test-token-12345678",
    )

    assert config.base_url == "http://localhost:1337"
    assert config.get_api_token() == "test-token-12345678"
    assert config.api_version == "auto"
    print("  Configuration creation: OK")


def verify_client_creation() -> None:
    """Verify client instantiation."""
    print("\nVerifying client creation...")

    config = StrapiConfig(
        base_url="http://localhost:1337",
        api_token="test-token-12345678",
    )

    # Sync client
    client = SyncClient(config)
    assert client.base_url == "http://localhost:1337"
    client.close()
    print("  SyncClient: OK")

    # Async client
    async_client = AsyncClient(config)
    assert async_client.base_url == "http://localhost:1337"
    print("  AsyncClient: OK")


def main() -> None:
    """Run all verification checks."""
    print("=" * 60)
    print("py-strapi Installation Verification")
    print("=" * 60)

    try:
        verify_imports()
        verify_config()
        verify_client_creation()

        print("\n" + "=" * 60)
        print("All checks passed!")
        print("=" * 60)
        print("\nNext steps:")
        print("  1. Set up your Strapi instance")
        print("  2. Generate an API token in Strapi admin")
        print("  3. Set environment variables:")
        print("     export STRAPI_BASE_URL='http://localhost:1337'")
        print("     export STRAPI_API_TOKEN='your-token'")
        print("  4. Run examples:")
        print("     python examples/basic_crud.py")
        print("     python examples/async_operations.py")

    except Exception as e:
        print(f"\nVerification failed: {e}")
        raise


if __name__ == "__main__":
    main()
