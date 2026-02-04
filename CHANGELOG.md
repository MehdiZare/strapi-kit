# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.6] - 2026-02-03

### Fixed

- **StrapiConfig extra env vars** ([#25](https://github.com/MehdiZare/strapi-kit/issues/25), [#26](https://github.com/MehdiZare/strapi-kit/pull/26))
  - Added `extra="ignore"` to `StrapiConfig` and `RetryConfig` model_config
  - Prevents `ValidationError: Extra inputs are not permitted` when unrelated `STRAPI_*` environment variables exist

- **Content type v5 parsing** ([#25](https://github.com/MehdiZare/strapi-kit/issues/25), [#26](https://github.com/MehdiZare/strapi-kit/pull/26))
  - Added `_normalize_content_type_item()` and `_normalize_content_types_list()` helpers
  - Flattens nested `schema` structure returned by Strapi v5 Content-Type Builder API
  - `get_content_types()`, `get_components()`, and `get_content_type_schema()` now work with both v4 and v5

- **Exception handling improvements** ([#23](https://github.com/MehdiZare/strapi-kit/pull/23), [#24](https://github.com/MehdiZare/strapi-kit/pull/24))
  - Use `StrapiError` instead of bare `Exception` in examples for precise error handling
  - Catch `PydanticValidationError` specifically in Content-Type Builder parsing
  - Add proper exception chaining when re-raising validation errors
  - Fix docstring to document `ConfigurationError` instead of `ValueError`

- **Singularization bug fix** ([#23](https://github.com/MehdiZare/strapi-kit/pull/23), [#24](https://github.com/MehdiZare/strapi-kit/pull/24))
  - Fix `api_id_to_singular()` for `-zzes` endings: `quizzes` → `quiz`, `buzzes` → `buzz`
  - Use length-based heuristic to distinguish single-z doubled vs double-z base words

### Changed

- **StrEnum migration** ([#26](https://github.com/MehdiZare/strapi-kit/pull/26))
  - Refactored 6 enum classes from `(str, Enum)` to `StrEnum` (Python 3.11+)
  - Affected: `FilterOperator`, `SortDirection`, `PublicationState`, `ConflictResolution`, `FieldType`, `RelationType`
  - Fixes UP042 linting errors in ruff preview mode

- Test coverage maintained at 86% (542 passing tests)
- Added 14 new tests for config extra env vars and v5 content type parsing

### Added

- **Content-Type Builder API** ([#15](https://github.com/MehdiZare/strapi-kit/issues/15))
  - `get_content_types(include_plugins=False)` - List all content types from Strapi
  - `get_components()` - List all components
  - `get_content_type_schema(uid)` - Get full schema for a content type
  - New models: `ContentTypeListItem`, `ComponentListItem`, `CTBContentTypeSchema`, `CTBContentTypeInfo`
  - Schema helper methods: `get_field_type()`, `is_relation_field()`, `is_component_field()`, `get_relation_target()`, `get_component_uid()`
  - Full async support for all methods

- **UID Conversion Utilities** ([#16](https://github.com/MehdiZare/strapi-kit/issues/16))
  - `api_id_to_singular()` - Convert plural API IDs to singular form (handles irregular plurals like people→person, children→child)
  - `uid_to_admin_url()` - Build Strapi admin panel URLs from content type UIDs
  - `uid_to_api_id` - Alias for `uid_to_endpoint` for clarity
  - Export of existing utilities: `extract_model_name()`, `is_api_content_type()`

- **SEO Configuration Detection** ([#17](https://github.com/MehdiZare/strapi-kit/issues/17))
  - `detect_seo_configuration()` - Detect SEO setup in content type schemas
  - `SEOConfiguration` dataclass for structured detection results
  - Support for component-based SEO (shared.seo, meta, metadata)
  - Support for flat SEO fields (metaTitle, meta_description, ogTitle, etc.)
  - Case-insensitive matching for field names and component UIDs

## [0.0.5] - 2025-01-XX

### Added

- Retry logic with exponential backoff
- Rate limit handling with Retry-After support
- Bulk operations (create, update, delete)
- Progress callbacks for long operations

## [0.0.4] - 2025-01-XX

### Added

- Media upload/download operations
- Streaming support for large files

## [0.0.3] - 2025-01-XX

### Added

- Type-safe query builder
- Response normalization for v4/v5

## [0.0.2] - 2025-01-XX

### Added

- Export/Import functionality with automatic relation resolution
- Schema caching for efficient content type metadata handling
- Media file export/download support
- Full migration examples (simple and production-ready)

### Changed

- Improved test coverage to 85%

## [0.0.1] - 2025-01-XX

### Added

- Initial release
- HTTP clients (sync and async)
- Configuration with Pydantic and environment variable support
- Authentication (API tokens)
- Exception hierarchy with semantic error types
- API version detection (v4/v5)
- Type-safe query builder with 24 filter operators
- Response normalization for both Strapi v4 and v5
- Media upload/download operations
- Dependency injection support with protocols
- Full type hints and mypy strict mode compliance

[Unreleased]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.6...HEAD
[0.0.6]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.5...v0.0.6
[0.0.5]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.4...v0.0.5
[0.0.4]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.3...v0.0.4
[0.0.3]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/MehdiZare/strapi-kit/releases/tag/v0.0.1
