# Installation

## Requirements

- Python 3.12 or higher
- pip or uv package manager (uv recommended for faster installs)

## Install from PyPI

=== "uv (Recommended)"

    ```bash
    uv pip install py-strapi
    ```

=== "pip"

    ```bash
    pip install py-strapi
    ```

**Why uv?** It's 10-100x faster than pip while being a drop-in replacement.

## Install with Development Dependencies

=== "uv (Recommended)"

    ```bash
    uv pip install py-strapi[dev]
    ```

=== "pip"

    ```bash
    pip install py-strapi[dev]
    ```

This includes:
- pytest and testing tools
- mypy for type checking
- ruff for linting
- code coverage tools

## Install from Source

=== "uv (Recommended)"

    ```bash
    git clone https://github.com/mehdizare/py-strapi.git
    cd py-strapi
    uv pip install -e ".[dev]"
    ```

=== "pip"

    ```bash
    git clone https://github.com/mehdizare/py-strapi.git
    cd py-strapi
    pip install -e ".[dev]"
    ```

## Verify Installation

```python
import py_strapi
print(py_strapi.__version__)
```

## Next Steps

- [Quick Start Guide](quickstart.md)
- [Configuration](configuration.md)
