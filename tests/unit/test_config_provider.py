"""Tests for ConfigProvider protocol and configuration DI."""

from py_strapi import ConfigProvider, StrapiConfig, SyncClient


class TestConfigProviderProtocol:
    """Tests for ConfigProvider protocol compliance."""

    def test_strapi_config_satisfies_config_provider(self):
        """Test that StrapiConfig satisfies ConfigProvider protocol."""
        config = StrapiConfig(base_url="http://localhost:1337", api_token="test-token")

        # Should satisfy protocol (runtime check)
        assert isinstance(config, ConfigProvider)

        # Test required methods
        assert callable(config.get_base_url)
        assert callable(config.get_api_token)

        # Test required properties
        assert hasattr(config, "api_version")
        assert hasattr(config, "timeout")
        assert hasattr(config, "max_connections")
        assert hasattr(config, "verify_ssl")
        assert hasattr(config, "retry")

        # Test behavior
        assert config.get_base_url() == "http://localhost:1337"
        assert config.get_api_token() == "test-token"
        assert config.api_version == "auto"
        assert config.timeout == 30.0
        assert config.max_connections == 10
        assert config.verify_ssl is True


class TestCustomConfigProvider:
    """Tests for custom configuration providers."""

    def test_custom_config_provider(self):
        """Test using a custom config provider implementation."""

        class TestConfig:
            """Minimal config provider for testing."""

            def get_base_url(self) -> str:
                return "http://test.example.com"

            def get_api_token(self) -> str:
                return "test-token"

            @property
            def api_version(self):
                return "v5"

            @property
            def timeout(self) -> float:
                return 10.0

            @property
            def max_connections(self) -> int:
                return 5

            @property
            def verify_ssl(self) -> bool:
                return False

            @property
            def retry(self):
                # Return minimal retry config
                class MockRetry:
                    max_attempts = 1
                    initial_wait = 1.0
                    max_wait = 1.0
                    exponential_base = 2.0
                    retry_on_status = {500}

                return MockRetry()

        # Custom config satisfies protocol
        custom_config = TestConfig()
        assert isinstance(custom_config, ConfigProvider)

        # Can use with client
        client = SyncClient(custom_config)

        # Verify custom config values are used
        assert client.base_url == "http://test.example.com"
        assert client.config.timeout == 10.0
        assert client.config.max_connections == 5
        assert client.config.verify_ssl is False

        client.close()

    def test_dict_based_config_provider(self):
        """Test config provider backed by a dictionary."""

        class DictConfig:
            """Config provider that reads from a dictionary."""

            def __init__(self, data: dict):
                self._data = data

            def get_base_url(self) -> str:
                return self._data["base_url"]

            def get_api_token(self) -> str:
                return self._data["api_token"]

            @property
            def api_version(self):
                return self._data.get("api_version", "auto")

            @property
            def timeout(self) -> float:
                return self._data.get("timeout", 30.0)

            @property
            def max_connections(self) -> int:
                return self._data.get("max_connections", 10)

            @property
            def verify_ssl(self) -> bool:
                return self._data.get("verify_ssl", True)

            @property
            def retry(self):
                class MockRetry:
                    max_attempts = 1

                return MockRetry()

        # Create config from dict
        config_data = {
            "base_url": "http://dict.example.com",
            "api_token": "dict-token",
            "timeout": 15.0,
        }

        dict_config = DictConfig(config_data)
        assert isinstance(dict_config, ConfigProvider)

        # Use with client
        client = SyncClient(dict_config)
        assert client.base_url == "http://dict.example.com"
        assert client.config.timeout == 15.0

        client.close()


class TestConfigProviderBenefits:
    """Tests demonstrating benefits of ConfigProvider protocol."""

    def test_mock_config_for_testing(self):
        """Test using mock config to avoid environment dependencies."""

        class MockConfig:
            """Simple mock config for unit tests."""

            def get_base_url(self) -> str:
                return "http://mock.test"

            def get_api_token(self) -> str:
                return "mock-token"

            @property
            def api_version(self):
                return "v4"

            @property
            def timeout(self) -> float:
                return 1.0  # Fast timeout for tests

            @property
            def max_connections(self) -> int:
                return 1  # Single connection for tests

            @property
            def verify_ssl(self) -> bool:
                return False  # No SSL in tests

            @property
            def retry(self):
                class NoRetry:
                    max_attempts = 1  # No retries in tests

                return NoRetry()

        # Use mock config in tests
        mock_config = MockConfig()
        client = SyncClient(mock_config)

        # Fast, isolated test configuration
        assert client.config.timeout == 1.0
        assert client.config.max_connections == 1
        assert not client.config.verify_ssl

        client.close()

    def test_environment_specific_configs(self):
        """Test different configs for different environments."""

        class EnvironmentConfig:
            """Config that adapts based on environment."""

            def __init__(self, env: str):
                self.env = env
                self._urls = {
                    "dev": "http://localhost:1337",
                    "staging": "https://staging.example.com",
                    "prod": "https://api.example.com",
                }
                self._tokens = {
                    "dev": "dev-token",
                    "staging": "staging-token",
                    "prod": "prod-token",
                }

            def get_base_url(self) -> str:
                return self._urls[self.env]

            def get_api_token(self) -> str:
                return self._tokens[self.env]

            @property
            def api_version(self):
                return "auto"

            @property
            def timeout(self) -> float:
                # Longer timeout for prod
                return 60.0 if self.env == "prod" else 30.0

            @property
            def max_connections(self) -> int:
                # More connections for prod
                return 20 if self.env == "prod" else 10

            @property
            def verify_ssl(self) -> bool:
                # Only verify in prod
                return self.env == "prod"

            @property
            def retry(self):
                class MockRetry:
                    max_attempts = 1

                return MockRetry()

        # Different configs for different environments
        dev_config = EnvironmentConfig("dev")
        prod_config = EnvironmentConfig("prod")

        assert dev_config.get_base_url() == "http://localhost:1337"
        assert prod_config.get_base_url() == "https://api.example.com"

        assert dev_config.timeout == 30.0
        assert prod_config.timeout == 60.0

        assert dev_config.verify_ssl is False
        assert prod_config.verify_ssl is True
