"""Version information for strapi-kit.

This file is automatically updated by hatch-vcs during build.
For development installs, it falls back to a placeholder version.
"""

try:
    # Try to import version from hatch-vcs generated file
    from strapi_kit._version import __version__
except ImportError:
    # Development mode - not built with hatch-vcs yet
    # This happens when installed with pip install -e .
    __version__ = "0.0.0.dev0+local"

__all__ = ["__version__"]
