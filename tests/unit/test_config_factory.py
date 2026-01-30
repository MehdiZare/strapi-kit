"""Tests for configuration factory and dependency injection."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from py_strapi import (
    ConfigFactory,
    ConfigurationError,
    RetryConfig,
    StrapiConfig,
    create_config,
    load_config,
)


class TestConfigFactory:
    """Test ConfigFactory methods."""

    def test_create_with_minimal_params(self):
        """Test creating config with minimal required parameters."""
        config = ConfigFactory.create(
            base_url="http://localhost:1337",
            api_token="test-token",
        )

        assert config.base_url == "http://localhost:1337"
        assert config.get_api_token() == "test-token"
        assert config.api_version == "auto"
        assert config.timeout == 30.0
        assert config.max_connections == 10
        assert config.verify_ssl is True

    def test_create_with_all_params(self):
        """Test creating config with all parameters."""
        retry_config = RetryConfig(max_attempts=5, initial_wait=2.0)

        config = ConfigFactory.create(
            base_url="http://strapi.example.com",
            api_token="production-token",
            api_version="v5",
            timeout=60.0,
            max_connections=50,
            retry=retry_config,
            rate_limit_per_second=10.0,
            verify_ssl=False,
        )

        assert config.base_url == "http://strapi.example.com"
        assert config.get_api_token() == "production-token"
        assert config.api_version == "v5"
        assert config.timeout == 60.0
        assert config.max_connections == 50
        assert config.retry.max_attempts == 5
        assert config.retry.initial_wait == 2.0
        assert config.rate_limit_per_second == 10.0
        assert config.verify_ssl is False

    def test_create_with_retry_dict(self):
        """Test creating config with retry as dictionary."""
        config = ConfigFactory.create(
            base_url="http://localhost:1337",
            api_token="test-token",
            retry={"max_attempts": 5, "initial_wait": 2.0},
        )

        assert config.retry.max_attempts == 5
        assert config.retry.initial_wait == 2.0

    def test_create_strips_trailing_slash(self):
        """Test that base_url trailing slash is stripped."""
        config = ConfigFactory.create(
            base_url="http://localhost:1337/",
            api_token="test-token",
        )

        assert config.base_url == "http://localhost:1337"

    def test_create_validation_error(self):
        """Test that invalid parameters raise ConfigurationError."""
        with pytest.raises(ConfigurationError, match="Invalid configuration"):
            ConfigFactory.create(
                base_url="http://localhost:1337",
                api_token="test-token",
                timeout=-10,  # Invalid: negative timeout
            )

    def test_from_dict(self):
        """Test creating config from dictionary."""
        config_dict = {
            "base_url": "http://localhost:1337",
            "api_token": "test-token",
            "timeout": 45.0,
            "retry": {
                "max_attempts": 5,
            },
        }

        config = ConfigFactory.from_dict(config_dict)

        assert config.base_url == "http://localhost:1337"
        assert config.get_api_token() == "test-token"
        assert config.timeout == 45.0
        assert config.retry.max_attempts == 5

    def test_from_dict_validation_error(self):
        """Test that invalid dict raises ConfigurationError."""
        with pytest.raises(ConfigurationError, match="Invalid configuration"):
            ConfigFactory.from_dict(
                {
                    "base_url": "http://localhost:1337",
                    "api_token": "test",
                    "timeout": -10,  # Invalid: negative timeout
                }
            )

    def test_from_environment_only(self, monkeypatch):
        """Test loading config from environment variables only."""
        monkeypatch.setenv("STRAPI_BASE_URL", "http://env.example.com")
        monkeypatch.setenv("STRAPI_API_TOKEN", "env-token")
        monkeypatch.setenv("STRAPI_TIMEOUT", "45.0")
        monkeypatch.setenv("STRAPI_RETRY_MAX_ATTEMPTS", "5")

        config = ConfigFactory.from_environment_only()

        assert config.base_url == "http://env.example.com"
        assert config.get_api_token() == "env-token"
        assert config.timeout == 45.0
        assert config.retry.max_attempts == 5

    def test_from_environment_only_missing_required(self, monkeypatch):
        """Test that missing required env vars raise ConfigurationError."""
        # Clear any existing STRAPI_ env vars
        for key in list(os.environ.keys()):
            if key.startswith("STRAPI_"):
                monkeypatch.delenv(key, raising=False)

        with pytest.raises(ConfigurationError, match="Invalid configuration"):
            ConfigFactory.from_environment_only()

    def test_from_env_file(self, tmp_path):
        """Test loading config from specific .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "STRAPI_BASE_URL=http://file.example.com\n"
            "STRAPI_API_TOKEN=file-token\n"
            "STRAPI_TIMEOUT=50.0\n"
        )

        config = ConfigFactory.from_env_file(env_file)

        assert config.base_url == "http://file.example.com"
        assert config.get_api_token() == "file-token"
        assert config.timeout == 50.0

    def test_from_env_file_not_found_required(self):
        """Test that missing required .env file raises ConfigurationError."""
        with pytest.raises(ConfigurationError, match=".env file not found"):
            ConfigFactory.from_env_file("/nonexistent/.env", required=True)

    def test_from_env_file_not_found_optional(self, monkeypatch):
        """Test that missing optional .env file falls back to env vars."""
        monkeypatch.setenv("STRAPI_BASE_URL", "http://env.example.com")
        monkeypatch.setenv("STRAPI_API_TOKEN", "env-token")

        config = ConfigFactory.from_env_file("/nonexistent/.env", required=False)

        assert config.base_url == "http://env.example.com"
        assert config.get_api_token() == "env-token"

    def test_from_env_with_search_paths(self, tmp_path, monkeypatch):
        """Test searching multiple paths for .env file."""
        # Create .env file in second search path
        env_dir = tmp_path / "config"
        env_dir.mkdir()
        env_file = env_dir / ".env"
        env_file.write_text(
            "STRAPI_BASE_URL=http://search.example.com\n"
            "STRAPI_API_TOKEN=search-token\n"
        )

        # First path doesn't exist, second does
        search_paths = [
            str(tmp_path / "nonexistent" / ".env"),
            str(env_file),
        ]

        config = ConfigFactory.from_env(search_paths=search_paths)

        assert config.base_url == "http://search.example.com"
        assert config.get_api_token() == "search-token"

    def test_from_env_no_file_found_optional(self, monkeypatch):
        """Test from_env without finding file falls back to env vars."""
        monkeypatch.setenv("STRAPI_BASE_URL", "http://env.example.com")
        monkeypatch.setenv("STRAPI_API_TOKEN", "env-token")

        search_paths = ["/nonexistent1/.env", "/nonexistent2/.env"]

        config = ConfigFactory.from_env(search_paths=search_paths, required=False)

        assert config.base_url == "http://env.example.com"
        assert config.get_api_token() == "env-token"

    def test_from_env_no_file_found_required(self):
        """Test from_env raises error when no file found and required=True."""
        search_paths = ["/nonexistent1/.env", "/nonexistent2/.env"]

        with pytest.raises(ConfigurationError, match="No .env file found"):
            ConfigFactory.from_env(search_paths=search_paths, required=True)

    def test_from_env_default_search_paths(self, tmp_path, monkeypatch):
        """Test from_env with default search paths."""
        # Change to temp directory
        monkeypatch.chdir(tmp_path)

        # Create .env in current directory
        env_file = tmp_path / ".env"
        env_file.write_text(
            "STRAPI_BASE_URL=http://default.example.com\n"
            "STRAPI_API_TOKEN=default-token\n"
        )

        config = ConfigFactory.from_env()

        assert config.base_url == "http://default.example.com"
        assert config.get_api_token() == "default-token"

    def test_merge_two_configs(self):
        """Test merging two configurations."""
        base_config = ConfigFactory.create(
            base_url="http://localhost:1337",
            api_token="base-token",
            timeout=30.0,
        )

        override_config = ConfigFactory.from_dict(
            {
                "base_url": "http://localhost:1337",  # Same
                "api_token": "override-token",  # Override
                "timeout": 60.0,  # Override
                "max_connections": 50,  # New
            }
        )

        merged = ConfigFactory.merge(base_config, override_config)

        assert merged.base_url == "http://localhost:1337"
        assert merged.get_api_token() == "override-token"
        assert merged.timeout == 60.0
        assert merged.max_connections == 50

    def test_merge_with_base(self):
        """Test merging with explicit base parameter."""
        base = ConfigFactory.create(
            base_url="http://localhost:1337",
            api_token="base-token",
        )

        override1 = ConfigFactory.from_dict(
            {"base_url": "http://localhost:1337", "api_token": "token1", "timeout": 45.0}
        )

        override2 = ConfigFactory.from_dict(
            {"base_url": "http://localhost:1337", "api_token": "token2", "timeout": 60.0}
        )

        merged = ConfigFactory.merge(override1, override2, base=base)

        # override2 should win
        assert merged.get_api_token() == "token2"
        assert merged.timeout == 60.0

    def test_merge_no_configs_raises(self):
        """Test that merge with no configs raises ValueError."""
        with pytest.raises(ValueError, match="At least one config"):
            ConfigFactory.merge()


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_load_config_with_file(self, tmp_path):
        """Test load_config with specific file."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "STRAPI_BASE_URL=http://convenience.example.com\n"
            "STRAPI_API_TOKEN=convenience-token\n"
        )

        config = load_config(env_file)

        assert config.base_url == "http://convenience.example.com"
        assert config.get_api_token() == "convenience-token"

    def test_load_config_without_file(self, tmp_path, monkeypatch):
        """Test load_config without file uses default search."""
        monkeypatch.chdir(tmp_path)

        env_file = tmp_path / ".env"
        env_file.write_text(
            "STRAPI_BASE_URL=http://default.example.com\n"
            "STRAPI_API_TOKEN=default-token\n"
        )

        config = load_config()

        assert config.base_url == "http://default.example.com"
        assert config.get_api_token() == "default-token"

    def test_load_config_required(self):
        """Test load_config with required=True raises when file missing."""
        with pytest.raises(ConfigurationError):
            load_config("/nonexistent/.env", required=True)

    def test_create_config(self):
        """Test create_config convenience function."""
        config = create_config(
            base_url="http://localhost:1337",
            api_token="test-token",
            timeout=45.0,
        )

        assert config.base_url == "http://localhost:1337"
        assert config.get_api_token() == "test-token"
        assert config.timeout == 45.0


class TestRealWorldScenarios:
    """Test real-world usage scenarios."""

    def test_development_environment(self, tmp_path, monkeypatch):
        """Test typical development setup with .env.local override."""
        monkeypatch.chdir(tmp_path)

        # Base .env file
        base_env = tmp_path / ".env"
        base_env.write_text(
            "STRAPI_BASE_URL=http://localhost:1337\n"
            "STRAPI_API_TOKEN=dev-token\n"
            "STRAPI_TIMEOUT=30.0\n"
        )

        # Local override (must include base_url for Pydantic to accept it)
        local_env = tmp_path / ".env.local"
        local_env.write_text(
            "STRAPI_BASE_URL=http://localhost:1337\n"
            "STRAPI_API_TOKEN=my-local-token\n"
            "STRAPI_TIMEOUT=60.0\n"
        )

        # Load with .env.local taking precedence
        config = ConfigFactory.from_env(
            search_paths=[str(local_env), str(base_env)]
        )

        assert config.base_url == "http://localhost:1337"
        assert config.get_api_token() == "my-local-token"  # Overridden
        assert config.timeout == 60.0  # Overridden

    def test_production_environment_vars(self, monkeypatch):
        """Test production setup with environment variables only."""
        monkeypatch.setenv("STRAPI_BASE_URL", "https://api.production.com")
        monkeypatch.setenv("STRAPI_API_TOKEN", "production-secret-token")
        monkeypatch.setenv("STRAPI_TIMEOUT", "120.0")
        monkeypatch.setenv("STRAPI_MAX_CONNECTIONS", "100")
        monkeypatch.setenv("STRAPI_RETRY_MAX_ATTEMPTS", "10")

        config = ConfigFactory.from_environment_only()

        assert config.base_url == "https://api.production.com"
        assert config.get_api_token() == "production-secret-token"
        assert config.timeout == 120.0
        assert config.max_connections == 100
        assert config.retry.max_attempts == 10

    def test_layered_configuration(self, tmp_path, monkeypatch):
        """Test layered config: defaults → file → env vars → explicit."""
        monkeypatch.chdir(tmp_path)

        # 1. File config
        env_file = tmp_path / ".env"
        env_file.write_text(
            "STRAPI_BASE_URL=http://localhost:1337\n"
            "STRAPI_API_TOKEN=file-token\n"
            "STRAPI_TIMEOUT=40.0\n"
        )

        # 2. Environment variable override
        monkeypatch.setenv("STRAPI_TIMEOUT", "50.0")

        # 3. Load base config (file + env vars)
        base_config = ConfigFactory.from_env_file(env_file, required=True)

        # 4. Explicit override (must include required fields for from_dict)
        final_config = ConfigFactory.merge(
            base_config,
            ConfigFactory.from_dict({
                "base_url": "http://localhost:1337",
                "api_token": "file-token",
                "timeout": 60.0,
                "max_connections": 50
            }),
        )

        assert final_config.base_url == "http://localhost:1337"
        assert final_config.get_api_token() == "file-token"
        assert final_config.timeout == 60.0  # Explicit override wins
        assert final_config.max_connections == 50  # New value

    def test_testing_environment(self):
        """Test creating config for testing without any .env files."""
        config = ConfigFactory.create(
            base_url="http://test.example.com",
            api_token="test-token",
            timeout=5.0,
            retry={"max_attempts": 1},  # No retries in tests
        )

        assert config.base_url == "http://test.example.com"
        assert config.timeout == 5.0
        assert config.retry.max_attempts == 1
