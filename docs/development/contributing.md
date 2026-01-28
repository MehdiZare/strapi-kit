# Contributing to strapi-kit

Thank you for your interest in contributing to strapi-kit! This guide will help you get started.

## Development Setup

### Prerequisites

- Python 3.12 or higher
- uv (recommended) or pip
- git

### Setup Steps

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/strapi-kit.git
cd strapi-kit

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -e ".[dev]"

# Or with pip
pip install -e ".[dev]"
```

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

### 2. Make Changes

- Write your code following the project style
- Add type hints to all functions
- Write or update tests (both sync and async if applicable)
- Update documentation if needed

### 3. Run Tests

```bash
# Run all tests
make test

# Run with coverage
make coverage

# Run specific test
pytest tests/unit/test_client.py -v
```

### 4. Code Quality Checks

```bash
# Run all checks at once
make pre-commit

# Or individually:
make format      # Format code with ruff
make lint        # Check linting
make type-check  # Run mypy
```

### 5. Commit Changes

We use [Conventional Commits](https://www.conventionalcommits.org/):

```bash
# Format: type(scope): description

git commit -m "feat(client): add retry logic for failed requests"
git commit -m "fix(auth): handle expired tokens correctly"
git commit -m "docs: update installation guide"
git commit -m "test: add async client tests"
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style/formatting
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks
- `perf`: Performance improvements
- `ci`: CI/CD changes

### 6. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub.

## Pull Request Guidelines

### PR Title

Use conventional commit format:

```
feat(client): add pagination support
fix(config): handle missing environment variables
docs: improve quickstart guide
```

### PR Description

- Clearly describe what changes you made and why
- Reference any related issues
- Include screenshots for UI changes (if applicable)
- List any breaking changes

### Automated Review

All PRs are automatically reviewed by **CodeRabbit AI**:
- Checks code quality and security
- Verifies type hints and documentation
- Suggests improvements
- Ensures tests are included

Address CodeRabbit's feedback before requesting human review.

## Code Style

### Python Style

- Follow PEP 8 (enforced by ruff)
- Use type hints for all functions
- Maximum line length: 100 characters
- Use f-strings for string formatting

### Type Hints

```python
# Good
def get_articles(client: SyncClient, limit: int = 10) -> dict[str, Any]:
    return client.get("articles", params={"limit": limit})

# Bad
def get_articles(client, limit=10):
    return client.get("articles", params={"limit": limit})
```

### Docstrings

Use Google-style docstrings:

```python
def create_entry(collection: str, data: dict[str, Any]) -> dict[str, Any]:
    """Create a new entry in a Strapi collection.

    Args:
        collection: Name of the collection (e.g., "articles")
        data: Entry data to create

    Returns:
        Created entry with id and metadata

    Raises:
        ValidationError: If data is invalid
        AuthenticationError: If API token is missing or invalid
    """
    ...
```

### Exception Handling

- Use specific exception types from the project's hierarchy
- Always chain exceptions: `raise NewError(...) from e`
- Include context in exception details

```python
from py_strapi.exceptions import ConnectionError

# Good
try:
    response = client.post("articles", json=data)
except httpx.HTTPError as e:
    raise ConnectionError(
        "Failed to create article",
        details={"collection": "articles", "error": str(e)}
    ) from e

# Bad
try:
    response = client.post("articles", json=data)
except Exception:
    raise Exception("Error")
```

## Testing

### Test Organization

- `tests/unit/`: Unit tests (fast, isolated)
- `tests/integration/`: Integration tests (requires real Strapi instance)

### Test Requirements

- Test both sync and async variants
- Test success and error cases
- Use respx for HTTP mocking
- Aim for 85%+ coverage
- Tests should be fast (<1 second each)

### Example Test

```python
import pytest
import httpx
import respx
from py_strapi import SyncClient, StrapiConfig

@pytest.mark.respx
def test_get_articles_success(respx_mock, strapi_config):
    """Test successful article retrieval."""
    # Mock HTTP response
    respx_mock.get("http://localhost:1337/api/articles").mock(
        return_value=httpx.Response(200, json={
            "data": [{"id": 1, "attributes": {"title": "Test"}}]
        })
    )

    # Test
    with SyncClient(strapi_config) as client:
        response = client.get("articles")
        assert len(response["data"]) == 1
        assert response["data"][0]["attributes"]["title"] == "Test"
```

## Architecture Guidelines

### Dual Client Pattern

The project uses a shared base with specialized implementations:

```
BaseClient (shared logic)
├── SyncClient (blocking operations)
└── AsyncClient (async operations)
```

**When adding features:**
1. Implement shared logic in `BaseClient`
2. Only override in sync/async clients if behavior differs
3. Keep both clients' APIs identical

### No Over-Engineering

- Write simple, focused code
- Avoid premature abstractions
- Three similar lines of code is better than a premature abstraction
- Only add complexity when there's a clear need

## Documentation

### When to Update Docs

Update documentation when:
- Adding new public APIs
- Changing behavior of existing features
- Adding new dependencies
- Changing configuration options

### Documentation Files

- `README.md`: Overview, quick start, basic examples
- `docs/`: Detailed documentation (MkDocs)
- `CLAUDE.md`: Technical architecture for AI assistants
- Docstrings: API reference (auto-generated)

## Getting Help

- Check existing issues and discussions
- Read [CLAUDE.md](../../CLAUDE.md) for architecture details
- Ask questions in PR comments
- Join community discussions

## Code of Conduct

- Be respectful and constructive
- Focus on the code, not the person
- Welcome newcomers
- Assume good intentions

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
