"""E2E test configuration and fixtures.

This module provides fixtures for running end-to-end tests against a real Strapi instance.
By default, e2e tests are skipped unless explicitly enabled.

Enable e2e tests:
    - Pass --e2e flag: pytest --e2e
    - Set environment variable: RUN_E2E_TESTS=true

Control Strapi lifecycle:
    - Default: Start Strapi before tests, stop after
    - --keep-strapi: Keep Strapi running after tests complete
    - STRAPI_E2E_EXTERNAL=true: Use existing external Strapi instance
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest
from pydantic import SecretStr

from strapi_kit import AsyncClient, StrapiConfig, SyncClient

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

# Default configuration
DEFAULT_STRAPI_URL = "http://localhost:1337"

# TEST_ONLY: This is an intentionally invalid placeholder token for tests.
# It will fail authentication - real tokens must be provided via STRAPI_E2E_TOKEN
# environment variable or extracted from Strapi container logs at runtime.
_TEST_PLACEHOLDER_TOKEN = "test-placeholder-not-a-real-token"  # nosec B105
E2E_DIR = Path(__file__).parent
DOCKER_COMPOSE_FILE = E2E_DIR / "docker-compose.yml"


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add E2E-specific command line options."""
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="Run end-to-end tests against a Strapi instance",
    )
    parser.addoption(
        "--keep-strapi",
        action="store_true",
        default=False,
        help="Keep Strapi running after tests complete",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register the e2e marker."""
    config.addinivalue_line("markers", "e2e: marks test as e2e (requires Strapi via Docker)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip e2e tests unless explicitly enabled."""
    run_e2e = config.getoption("--e2e") or os.environ.get("RUN_E2E_TESTS", "").lower() == "true"

    if not run_e2e:
        skip_e2e = pytest.mark.skip(
            reason="E2E tests disabled. Use --e2e flag or RUN_E2E_TESTS=true"
        )
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip_e2e)


def _is_external_strapi() -> bool:
    """Check if using an external Strapi instance."""
    return os.environ.get("STRAPI_E2E_EXTERNAL", "").lower() == "true"


def _get_strapi_url() -> str:
    """Get the Strapi URL from environment or default."""
    return os.environ.get("STRAPI_E2E_URL", DEFAULT_STRAPI_URL)


def _get_api_token() -> str:
    """Get the API token from environment or placeholder fallback."""
    return os.environ.get("STRAPI_E2E_TOKEN", _TEST_PLACEHOLDER_TOKEN)


def _docker_compose_cmd() -> list[str]:
    """Get the docker compose command (supports both old and new syntax)."""
    # Try new docker compose syntax first
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return ["docker", "compose"]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fall back to docker-compose
    return ["docker-compose"]


def _start_strapi() -> None:
    """Start Strapi using Docker Compose."""
    print("\n🚀 Starting Strapi via Docker Compose...")
    cmd = _docker_compose_cmd()

    # Build and start
    subprocess.run(
        [*cmd, "-f", str(DOCKER_COMPOSE_FILE), "up", "-d", "--build"],
        check=True,
        cwd=E2E_DIR,
    )


def _stop_strapi() -> None:
    """Stop Strapi and clean up Docker resources."""
    print("\n🛑 Stopping Strapi...")
    cmd = _docker_compose_cmd()

    subprocess.run(
        [*cmd, "-f", str(DOCKER_COMPOSE_FILE), "down", "-v"],
        check=True,
        cwd=E2E_DIR,
    )


def _wait_for_strapi(url: str, timeout: int = 180) -> bool:
    """Wait for Strapi to become healthy.

    Args:
        url: Strapi base URL
        timeout: Maximum seconds to wait

    Returns:
        True if Strapi is healthy, False if timeout reached
    """
    health_url = f"{url}/_health"
    start_time = time.time()

    print(f"⏳ Waiting for Strapi at {health_url}...")

    while time.time() - start_time < timeout:
        try:
            response = httpx.get(health_url, timeout=5)
            if response.status_code == 204:
                print("✅ Strapi is ready!")
                return True
        except httpx.RequestError:
            pass

        # Show progress
        elapsed = int(time.time() - start_time)
        if elapsed % 10 == 0:
            print(f"   Still waiting... ({elapsed}s elapsed)")

        time.sleep(2)

    print(f"❌ Strapi failed to start within {timeout} seconds")
    return False


def _extract_token_from_logs() -> str | None:
    """Extract the API token from Strapi container logs.

    The bootstrap script outputs the token when it creates it.
    Retries a few times since the token might not be immediately available.

    Returns:
        The API token if found, None otherwise
    """
    cmd = _docker_compose_cmd()

    # Retry a few times since logs might not be immediately available
    for attempt in range(10):
        try:
            result = subprocess.run(
                [*cmd, "-f", str(DOCKER_COMPOSE_FILE), "logs", "strapi"],
                capture_output=True,
                text=True,
                cwd=E2E_DIR,
                timeout=10,
            )

            # Combine stdout and stderr as logs might be in either
            log_output = result.stdout + result.stderr

            # Look for the token in the logs
            # Strapi tokens can be hex (v4) or base64 (v5), so match alphanumeric + base64 chars
            # Pattern matches: [E2E] Token: <token_string>
            match = re.search(r"\[E2E\] Token: ([a-zA-Z0-9+/=_-]{32,})", log_output)
            if match:
                token = match.group(1)
                print(f"📝 Extracted API token from logs: {token[:8]}...{token[-8:]}")
                return token

            # Wait before retry (longer wait to give Strapi time to bootstrap)
            if attempt < 9:
                time.sleep(3)
        except Exception as e:
            print(f"⚠️  Token extraction attempt {attempt + 1} failed: {e}")
            if attempt < 9:
                time.sleep(3)

    return None


def _setup_api_token(url: str) -> str | None:
    """Get the API token for E2E tests.

    First checks environment variable, then tries to extract from logs.

    Args:
        url: Strapi base URL (used for potential admin API calls)

    Returns:
        The API token string, or None if setup failed
    """
    # First, check environment variable
    env_token = os.environ.get("STRAPI_E2E_TOKEN")
    if env_token:
        print("📝 Using API token from STRAPI_E2E_TOKEN env var")
        return env_token

    # Try to extract from logs (bootstrap creates it)
    print("🔍 Attempting to extract API token from Strapi logs...")
    log_token = _extract_token_from_logs()
    if log_token:
        return log_token

    # Fall back to default (will likely fail authentication)
    print("⚠️  No API token found in logs. Set STRAPI_E2E_TOKEN environment variable.")
    print("⚠️  Falling back to default token (likely to fail authentication).")
    return _get_api_token()


@pytest.fixture(scope="session")
def strapi_instance(request: pytest.FixtureRequest) -> Generator[str, None, None]:
    """Session-scoped fixture that manages the Strapi lifecycle.

    Starts Strapi via Docker Compose before tests and optionally
    stops it after tests complete.

    Yields:
        The Strapi base URL

    Environment variables:
        STRAPI_E2E_EXTERNAL: If "true", skip Docker management and use external instance
        STRAPI_E2E_URL: Override the Strapi URL (default: http://localhost:1337)
        STRAPI_PORT: Override the Strapi port in docker-compose
    """
    url = _get_strapi_url()
    keep_running = request.config.getoption("--keep-strapi")

    if _is_external_strapi():
        print(f"\n📡 Using external Strapi at {url}")
        if not _wait_for_strapi(url, timeout=30):
            pytest.fail(f"External Strapi at {url} is not responding")
        yield url
        return

    # Start Strapi via Docker
    try:
        _start_strapi()

        if not _wait_for_strapi(url):
            # Get logs on failure
            cmd = _docker_compose_cmd()
            subprocess.run(
                [*cmd, "-f", str(DOCKER_COMPOSE_FILE), "logs", "--tail=100"],
                cwd=E2E_DIR,
            )
            pytest.fail("Strapi failed to start. Check logs above.")

        yield url

    finally:
        if keep_running:
            print("\n📌 Keeping Strapi running (--keep-strapi flag)")
        else:
            _stop_strapi()


@pytest.fixture(scope="session")
def e2e_api_token(strapi_instance: str) -> str:
    """Get or create an API token for E2E tests.

    Args:
        strapi_instance: The Strapi base URL (ensures Strapi is running)

    Returns:
        A valid API token string
    """
    token = _setup_api_token(strapi_instance)
    if not token:
        pytest.fail("Failed to obtain API token for E2E tests")
    return token


@pytest.fixture(scope="session")
def e2e_strapi_config(strapi_instance: str, e2e_api_token: str) -> StrapiConfig:
    """Create a StrapiConfig for E2E tests.

    Args:
        strapi_instance: The Strapi base URL
        e2e_api_token: The API token

    Returns:
        A configured StrapiConfig instance
    """
    return StrapiConfig(
        base_url=strapi_instance,
        api_token=SecretStr(e2e_api_token),
        timeout=30.0,
    )


@pytest.fixture
def sync_client(e2e_strapi_config: StrapiConfig) -> Generator[SyncClient, None, None]:
    """Provide a sync client for E2E tests.

    Args:
        e2e_strapi_config: The Strapi configuration

    Yields:
        A SyncClient instance
    """
    with SyncClient(e2e_strapi_config) as client:
        yield client


@pytest.fixture
async def async_client(
    e2e_strapi_config: StrapiConfig,
) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async client for E2E tests.

    Args:
        e2e_strapi_config: The Strapi configuration

    Yields:
        An AsyncClient instance
    """
    async with AsyncClient(e2e_strapi_config) as client:
        yield client
