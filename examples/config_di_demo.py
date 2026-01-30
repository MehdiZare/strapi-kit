#!/usr/bin/env python3
"""Demo script showing configuration dependency injection patterns.

This script demonstrates various ways to configure py-strapi using the
new ConfigFactory system.
"""

from pydantic import SecretStr

from py_strapi import (
    ConfigFactory,
    create_config,
    load_config,
)


def demo_load_from_env():
    """Demo 1: Load configuration from .env file."""
    print("=" * 60)
    print("Demo 1: Loading from .env file")
    print("=" * 60)

    try:
        # Automatically searches for .env, .env.local, or ~/.config/strapi/.env
        config = load_config()
        print("✅ Loaded config from .env")
        print(f"   Base URL: {config.base_url}")
        print(f"   Timeout: {config.timeout}s")
        print(f"   Max connections: {config.max_connections}")
    except Exception as e:
        print(f"❌ No .env file found: {e}")
        print("   Create a .env file with STRAPI_BASE_URL and STRAPI_API_TOKEN")

    print()


def demo_explicit_config():
    """Demo 2: Create configuration explicitly (no .env needed)."""
    print("=" * 60)
    print("Demo 2: Explicit configuration (for testing)")
    print("=" * 60)

    config = create_config(
        base_url="http://test.example.com",
        api_token=SecretStr("test-token-12345"),
        timeout=5.0,
        max_connections=5,
        verify_ssl=False,
        retry={
            "max_attempts": 1,  # No retries in tests
            "initial_wait": 0.1,
        },
    )

    print("✅ Created explicit config")
    print(f"   Base URL: {config.base_url}")
    print(f"   Timeout: {config.timeout}s")
    print(f"   Retry attempts: {config.retry.max_attempts}")
    print(f"   Verify SSL: {config.verify_ssl}")
    print()


def demo_environment_only():
    """Demo 3: Load from environment variables only."""
    print("=" * 60)
    print("Demo 3: Environment variables only (production pattern)")
    print("=" * 60)

    try:
        # This requires STRAPI_BASE_URL and STRAPI_API_TOKEN to be set
        config = ConfigFactory.from_environment_only()
        print("✅ Loaded from environment variables")
        print(f"   Base URL: {config.base_url}")
    except Exception as e:
        print(f"❌ Missing environment variables: {e}")
        print("   Set STRAPI_BASE_URL and STRAPI_API_TOKEN")

    print()


def demo_config_merging():
    """Demo 4: Merge multiple configurations."""
    print("=" * 60)
    print("Demo 4: Configuration layering/merging")
    print("=" * 60)

    # Base configuration
    base_config = create_config(
        base_url="http://localhost:1337",
        api_token=SecretStr("dev-token"),
        timeout=30.0,
        max_connections=10,
    )

    # Production overrides
    prod_overrides = ConfigFactory.from_dict(
        {
            "base_url": "https://api.production.com",
            "api_token": "prod-token-secret",
            "timeout": 120.0,
            "max_connections": 100,
        }
    )

    # Merge (prod overrides win)
    final_config = ConfigFactory.merge(base_config, prod_overrides)

    print("✅ Merged configurations")
    print("   Base config:")
    print(f"     - URL: {base_config.base_url}")
    print(f"     - Timeout: {base_config.timeout}s")
    print("   Production overrides:")
    print(f"     - URL: {prod_overrides.base_url}")
    print(f"     - Timeout: {prod_overrides.timeout}s")
    print("   Final merged config:")
    print(f"     - URL: {final_config.base_url}")
    print(f"     - Timeout: {final_config.timeout}s")
    print()


def demo_custom_search_paths():
    """Demo 5: Custom search paths for .env files."""
    print("=" * 60)
    print("Demo 5: Custom search paths")
    print("=" * 60)

    try:
        config = ConfigFactory.from_env(
            search_paths=[
                ".env.local",  # Highest priority (local overrides)
                ".env",  # Base configuration
                "~/.config/strapi/.env",  # User configuration
                "/etc/strapi/.env",  # System configuration (lowest priority)
            ],
            required=False,  # Don't fail if no file found
        )
        print("✅ Loaded config with custom search paths")
        print("   Searched: .env.local, .env, ~/.config/strapi/.env, /etc/strapi/.env")
        print(f"   Base URL: {config.base_url}")
    except Exception as e:
        print("❌ No .env file found in search paths")
        print(f"   Error: {e}")

    print()


def demo_usage_with_client():
    """Demo 6: Using config with SyncClient."""
    print("=" * 60)
    print("Demo 6: Using config with SyncClient")
    print("=" * 60)

    # Create config for demo purposes
    config = create_config(
        base_url="http://localhost:1337",
        api_token=SecretStr("demo-token"),
    )

    print("✅ Created config and initialized client")
    print(f"   Base URL: {config.base_url}")
    print(f"   Would connect to Strapi at {config.base_url}")
    print()

    # In real usage:
    # with SyncClient(config) as client:
    #     response = client.get("articles")
    #     print(f"Got {len(response['data'])} articles")


def main():
    """Run all demos."""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 8 + "py-strapi Configuration DI Demo" + " " * 18 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    demos = [
        demo_load_from_env,
        demo_explicit_config,
        demo_environment_only,
        demo_config_merging,
        demo_custom_search_paths,
        demo_usage_with_client,
    ]

    for demo in demos:
        demo()

    print("=" * 60)
    print("✅ All demos completed!")
    print("=" * 60)
    print()
    print("Key Takeaways:")
    print("  1. Multiple config sources: .env, env vars, code, dicts")
    print("  2. Flexible search paths for .env files")
    print("  3. Configuration merging for layered setups")
    print("  4. Type-safe with Pydantic validation")
    print("  5. Works seamlessly with SyncClient and AsyncClient")
    print()


if __name__ == "__main__":
    main()
