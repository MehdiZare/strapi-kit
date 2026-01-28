# Installation

## Requirements

- Python 3.12 or higher
- pip or uv package manager

## Install from PyPI

```bash
pip install py-strapi
```

## Install with Development Dependencies

```bash
pip install py-strapi[dev]
```

This includes:
- pytest and testing tools
- mypy for type checking
- ruff for linting
- code coverage tools

## Install from Source

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
