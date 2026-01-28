# Testing Guide

This guide covers testing practices and patterns for py-strapi.

## Running Tests

### Quick Start

```bash
# Run all tests
make test

# Run with coverage
make coverage

# Run specific test file
pytest tests/unit/test_client.py -v

# Run specific test
pytest tests/unit/test_client.py::TestSyncClient::test_get_request_success -v
```

### Test Commands

```bash
# Verbose output
pytest -v

# Show local variables on failure
pytest --showlocals

# Stop on first failure
pytest -x

# Run only failed tests from last run
pytest --lf

# Watch mode (requires pytest-watch)
pytest-watch
```

## Test Organization

```
tests/
├── unit/               # Fast, isolated unit tests
│   ├── test_client.py
│   ├── test_config.py
│   └── test_auth.py
├── integration/        # Tests against real Strapi (future)
│   └── test_e2e.py
└── conftest.py         # Shared fixtures
```

### Test Categories

**Unit Tests:**
- Test single components in isolation
- Mock external dependencies
- Fast (<1 second each)
- No network calls

**Integration Tests (Planned):**
- Test against real Strapi instance
- Use Docker for Strapi setup
- Slower but verify real behavior

## Writing Tests

### Test Naming

```python
# Pattern: test_<action>_<expected_result>
def test_get_articles_success():
    """Test successful retrieval of articles."""
    pass

def test_get_articles_not_found():
    """Test handling of 404 when articles don't exist."""
    pass

def test_authentication_with_invalid_token():
    """Test that invalid token raises AuthenticationError."""
    pass
```

### Test Structure (AAA Pattern)

```python
def test_example():
    # Arrange - Set up test data and mocks
    config = StrapiConfig(base_url="http://test", api_token="token")
    expected_data = {"id": 1, "title": "Test"}

    # Act - Execute the code being tested
    with SyncClient(config) as client:
        response = client.get("articles")

    # Assert - Verify the results
    assert response["data"][0]["id"] == expected_data["id"]
```

## HTTP Mocking with respx

### Basic Mocking

```python
import pytest
import httpx
import respx

@pytest.mark.respx
def test_get_request(respx_mock):
    """Test basic GET request."""
    # Mock the response
    respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    # Make request (will use mock)
    config = StrapiConfig(base_url="http://localhost:1337", api_token="test")
    with SyncClient(config) as client:
        response = client.get("articles")

    assert response["data"] == []
```

### Mocking Errors

```python
@pytest.mark.respx
def test_authentication_error(respx_mock):
    """Test handling of authentication errors."""
    # Mock 401 response
    respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(401, json={
            "error": {"message": "Invalid token"}
        })
    )

    config = StrapiConfig(base_url="http://localhost:1337", api_token="invalid")
    with SyncClient(config) as client:
        with pytest.raises(AuthenticationError) as exc_info:
            client.get("articles")

    assert "Invalid token" in str(exc_info.value)
```

### Multiple Requests

```python
@pytest.mark.respx
def test_multiple_requests(respx_mock):
    """Test making multiple requests."""
    # Mock multiple endpoints
    respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(200, json={"data": [{"id": 1}]})
    )
    respx_mock.get("http://localhost:1337/api/users").mock(
        return_value=httpx.Response(200, json={"data": [{"id": 2}]})
    )

    config = StrapiConfig(base_url="http://localhost:1337", api_token="test")
    with SyncClient(config) as client:
        articles = client.get("articles")
        users = client.get("users")

    assert len(articles["data"]) == 1
    assert len(users["data"]) == 1
```

## Testing Async Code

### Async Test Pattern

```python
import pytest

@pytest.mark.asyncio
@pytest.mark.respx
async def test_async_get_request(respx_mock):
    """Test async GET request."""
    respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(200, json={"data": []})
    )

    config = StrapiConfig(base_url="http://localhost:1337", api_token="test")
    async with AsyncClient(config) as client:
        response = await client.get("articles")

    assert response["data"] == []
```

**Note:** pytest-asyncio is configured in auto mode, so `@pytest.mark.asyncio` is optional but recommended for clarity.

## Fixtures

### Using Shared Fixtures

```python
# Defined in conftest.py
def test_with_config(strapi_config):
    """Test using shared config fixture."""
    with SyncClient(strapi_config) as client:
        assert client.config.base_url == "http://localhost:1337"

def test_with_mock_response(mock_v4_response):
    """Test using shared v4 response fixture."""
    assert "attributes" in mock_v4_response["data"]
```

### Creating Custom Fixtures

```python
# In conftest.py or test file
import pytest

@pytest.fixture
def article_data():
    """Sample article data for testing."""
    return {
        "id": 1,
        "attributes": {
            "title": "Test Article",
            "content": "Test content"
        }
    }

# Use in tests
def test_article_parsing(article_data):
    assert article_data["attributes"]["title"] == "Test Article"
```

## Parametrized Tests

### Testing Multiple Cases

```python
import pytest

@pytest.mark.parametrize("status_code,exception_type", [
    (401, AuthenticationError),
    (403, AuthorizationError),
    (404, NotFoundError),
    (400, ValidationError),
    (500, ServerError),
])
@pytest.mark.respx
def test_error_handling(status_code, exception_type, respx_mock):
    """Test that different status codes raise correct exceptions."""
    respx_mock.get("http://localhost:1337/api/test").mock(
        return_value=httpx.Response(status_code, json={"error": "Test error"})
    )

    config = StrapiConfig(base_url="http://localhost:1337", api_token="test")
    with SyncClient(config) as client:
        with pytest.raises(exception_type):
            client.get("test")
```

## Coverage Guidelines

### Target Coverage

- **Overall:** 85%+
- **New features:** 100%
- **Critical paths:** 100% (auth, error handling)
- **Edge cases:** As needed

### Running Coverage

```bash
# Generate HTML report
make coverage

# View report
open htmlcov/index.html

# Generate XML for CI
pytest --cov=py_strapi --cov-report=xml
```

### Coverage Configuration

Exclude lines from coverage:

```python
def example():
    if TYPE_CHECKING:  # pragma: no cover
        from typing import Protocol

    if __name__ == "__main__":  # pragma: no cover
        main()

    raise NotImplementedError  # pragma: no cover
```

## Testing Best Practices

### Do's ✅

- **Test both success and error paths**
- **Test both sync and async variants**
- **Use descriptive test names**
- **Keep tests fast (<1 second each)**
- **Mock external dependencies**
- **Test edge cases**
- **Use fixtures for common setup**

### Don'ts ❌

- **Don't test implementation details**
- **Don't make tests dependent on each other**
- **Don't use real network calls in unit tests**
- **Don't test framework code (httpx, pydantic)**
- **Don't skip tests without good reason**
- **Don't use sleep() in tests**

### Example: Good Test

```python
@pytest.mark.respx
def test_get_articles_with_filters(respx_mock, strapi_config):
    """Test GET request with query parameters."""
    # Arrange
    respx_mock.get(
        "http://localhost:1337/api/articles",
        params={"filters[title][$eq]": "Test"}
    ).mock(
        return_value=httpx.Response(200, json={
            "data": [{"id": 1, "attributes": {"title": "Test"}}]
        })
    )

    # Act
    with SyncClient(strapi_config) as client:
        response = client.get("articles", params={
            "filters[title][$eq]": "Test"
        })

    # Assert
    assert len(response["data"]) == 1
    assert response["data"][0]["attributes"]["title"] == "Test"
```

## Debugging Tests

### Using pdb

```python
def test_something():
    config = StrapiConfig(base_url="http://test", api_token="token")

    # Drop into debugger
    import pdb; pdb.set_trace()

    with SyncClient(config) as client:
        response = client.get("articles")
```

### Print Debugging

```python
def test_with_output(capsys):
    """Test that captures print output."""
    print("Debug info")
    result = some_function()

    # Capture and check output
    captured = capsys.readouterr()
    assert "Debug info" in captured.out
```

### Verbose Errors

```bash
# Show full diff for assertion errors
pytest --tb=long

# Show local variables on failure
pytest --showlocals

# Show captured output
pytest -s
```

## Continuous Integration

Tests run automatically on:
- Every pull request
- Every push to main/dev
- Scheduled nightly builds

**Required Checks:**
- All tests pass
- Coverage > 85%
- No type errors (mypy)
- No linting errors (ruff)

## Further Reading

- [pytest documentation](https://docs.pytest.org/)
- [respx documentation](https://lundberg.github.io/respx/)
- [pytest-asyncio documentation](https://pytest-asyncio.readthedocs.io/)
- [Contributing Guide](contributing.md)
