# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- 89% test coverage with 355 passing tests
- Extensive documentation and examples

### Features in Development
- Bulk operations with streaming
- Content type introspection
- Advanced rate limiting
- Webhook support
