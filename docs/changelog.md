# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Media Upload MIME Type Detection** ([#13](https://github.com/MehdiZare/strapi-kit/issues/13)): Fixed `upload_file()` to properly detect and set MIME type based on file extension instead of using `application/octet-stream` for all uploads. Also now sends actual filename instead of hardcoded "file".

### Changed

- **Exception Handling Improvements**:
  - Centralized `ConfigurationError` in the exceptions module for consistent imports
  - Replaced generic `ValueError` with `ValidationError` for input validation errors (pagination, streaming, rate limiting)
  - Replaced generic `ValueError` with `ConfigurationError` for configuration errors (API token validation)
  - Replaced generic `ValueError` with `FormatError` for export path validation (path traversal prevention)
  - Replaced generic `RuntimeError` with `MediaError` for media operation errors
  - All exceptions now importable from `strapi_kit.exceptions` or `strapi_kit` directly

- **Example Scripts Improvements**:
  - `basic_crud.py` ([#10](https://github.com/MehdiZare/strapi-kit/issues/10)): Fixed uninitialized `article_id` variable that could cause NameError if POST request failed
  - `simple_migration.py` ([#11](https://github.com/MehdiZare/strapi-kit/issues/11)): Added configuration validation, connection verification, error handling, timestamped file paths, and environment variable support
  - `full_migration_v5.py` ([#12](https://github.com/MehdiZare/strapi-kit/issues/12)): Replaced hardcoded API tokens with environment variables (`SOURCE_STRAPI_TOKEN`, `TARGET_STRAPI_TOKEN`, etc.) for security

### Added

#### Core Infrastructure
- HTTP clients (sync and async) with connection pooling
- Configuration system with Pydantic and environment variable support
- API token authentication
- Complete exception hierarchy with detailed error context
- Automatic Strapi v4/v5 version detection and normalization

#### Type-Safe Query Builder
- Fluent API with 24 filter operators (eq, ne, gt, lt, contains, in, between, etc.)
- Advanced sorting with multiple fields and directions
- Flexible pagination (page-based and offset-based)
- Population (relation loading) with nested support
- Field selection for optimized queries
- Publication state and locale filtering

#### Media Operations
- Single and batch file uploads with metadata (alt text, captions)
- Streaming downloads for large files
- Media library queries with filters
- Media metadata updates
- Entity attachment for linking media to content
- Full async support for all operations

#### Export/Import System
- Content export with automatic schema caching
- Schema-based relation resolution
- ID mapping between source and target instances
- Media export/import support
- Progress tracking with callbacks
- Dry-run mode for validation
- Conflict resolution strategies

#### Developer Experience
- Protocol-based dependency injection for testability
- Automatic retry with exponential backoff
- Comprehensive type hints and mypy strict compliance
- 85% test coverage with 460 passing tests
- Extensive documentation and examples

### Features in Development
- Bulk operations with streaming
- Content type introspection
- Advanced rate limiting
- Webhook support
