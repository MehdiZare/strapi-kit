# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-02-04

### Fixed

- **Race conditions in async bulk operations** ([#30](https://github.com/MehdiZare/strapi-kit/pull/30))
  - Added `asyncio.Lock()` to protect shared state mutations in `bulk_create()`, `bulk_update()`, `bulk_delete()`
  - Ensures thread-safe updates to `completed`, `successes`, `failures` counters

- **JSONL media manifest stream consumption** ([#30](https://github.com/MehdiZare/strapi-kit/pull/30))
  - Fixed critical bug where `read_media_manifest()` consumed entity stream
  - Now uses separate reader for media manifest to preserve entity iteration

- **V5 string relation ID support** ([#30](https://github.com/MehdiZare/strapi-kit/pull/30))
  - Updated `_extract_ids_from_field()` to accept both `int` and `str` for v5 documentId relations
  - Added `doc_id_to_new_id` mapping to `ImportResult` for v5 string relation resolution
  - `_validate_relations()` now tracks both numeric IDs and documentIds

- **JSONL media import metadata preservation** ([#30](https://github.com/MehdiZare/strapi-kit/pull/30))
  - Use `MediaHandler.upload_media_file()` instead of `client.upload_file()` to preserve alt text and captions

- **Strict mypy compliance** ([#30](https://github.com/MehdiZare/strapi-kit/pull/30))
  - Changed `self._file: Any` to `IO[str] | None` in `JSONLImportReader` and `JSONLExportWriter`
  - Added type guard for non-dict `info` payloads in `extract_info_from_schema()`
  - Narrowed broad `except Exception` catches to `except StrapiError` in JSONL loops

- **Code quality improvements** ([#30](https://github.com/MehdiZare/strapi-kit/pull/30))
  - Created shared `extract_info_from_schema()` utility in `utils/schema.py`
  - Added parent directory creation in `JSONLExportWriter.__enter__()`
  - Use explicit `is not None` checks instead of truthy checks for ID lookups
  - Replaced Unicode multiplication symbol with plain `x` in docstrings

- **JSONL import path traversal protection** ([#29](https://github.com/MehdiZare/strapi-kit/pull/29))
  - Added path traversal validation to JSONL media import matching standard import security pattern
  - Uses `resolve()` and `is_relative_to()` to prevent directory traversal attacks

- **JSONL import two-pass streaming** ([#29](https://github.com/MehdiZare/strapi-kit/pull/29))
  - Refactored `import_from_jsonl()` to use true O(1) memory with two-pass streaming
  - Pass 1: Create entities, store only ID mappings (old_id → new_id)
  - Pass 2: Re-read file to resolve relations using ID mappings
  - Memory profile reduced from O(entities) to O(entity_count x 2 ints)
  - Fixed: ID mappings now properly copied to `ImportResult` for caller access

- **Strapi v5 update endpoint consistency** ([#29](https://github.com/MehdiZare/strapi-kit/pull/29))
  - Fixed UPDATE conflict resolution to use `document_id` instead of numeric ID for endpoint path
  - Added `doc_id_mapping` field to `ImportResult` to track document_ids for v5 endpoints
  - Relation updates now use `document_id` when available (v5) with fallback to numeric ID (v4)
  - Applies to both standard import and JSONL streaming import

- **Removed unused test fixtures** ([#29](https://github.com/MehdiZare/strapi-kit/pull/29))
  - Removed unused `mock_media_response` parameter from `test_update_media_not_found` in sync and async tests

- **`update_media` version detection** ([#28](https://github.com/MehdiZare/strapi-kit/issues/28))
  - Fixed bug where `update_media()` used wrong endpoint when `api_version="auto"` and no prior API calls
  - Now calls `get_media()` first to trigger version detection before choosing v4 vs v5 endpoint

- **Media download streaming** ([#28](https://github.com/MehdiZare/strapi-kit/issues/28))
  - Fixed `download_file()` to stream directly to disk when `save_path` is provided
  - Previously buffered entire file in memory before writing, causing issues with large files

- **Async bulk `batch_size` parameter** ([#28](https://github.com/MehdiZare/strapi-kit/issues/28))
  - Fixed `batch_size` parameter in async `bulk_create()`, `bulk_update()`, `bulk_delete()`
  - Now properly processes items in batches to control memory usage
  - `batch_size` controls items per processing wave, `max_concurrency` controls parallel requests within each wave

### Added

- **Schema-driven relation extraction** ([#28](https://github.com/MehdiZare/strapi-kit/issues/28))
  - `extract_relations_with_schema()` - Extract relations using content type schema for accuracy
  - `strip_relations_with_schema()` - Remove only actual relation fields, preserving non-relation fields
  - Recursive extraction from components and dynamic zones
  - Extended `FieldSchema` with `component`, `components`, and `repeatable` fields
  - Added `get_component_schema()` to schema cache for component schema lookups
  - Exporter now uses schema-aware extraction to avoid false positives

- **JSONL streaming export/import** ([#28](https://github.com/MehdiZare/strapi-kit/issues/28))
  - `ExportFormat.JSONL` enum for selecting export format
  - `JSONLExportWriter` - O(1) memory streaming export writer
  - `JSONLImportReader` - O(1) memory streaming import reader
  - `exporter.export_to_jsonl()` - Stream entities to JSONL file as they're fetched
  - `importer.import_from_jsonl()` - Stream import from JSONL file
  - Enables processing exports larger than available RAM

- **Import options implementation** ([#28](https://github.com/MehdiZare/strapi-kit/issues/28))
  - `validate_relations` - Pre-import validation that all relation targets exist in export data
  - `overwrite_media` - Check for existing media by hash before uploading (skip duplicates)
  - `batch_size` - Batch-based progress reporting during entity import
  - Added `relations_imported` field to `ImportResult`

### Changed

- Removed empty leftover directories (`import_export/`, `importexport/`)
- **Consolidated linting tools into ruff**
  - Replaced bandit with ruff's `S` (flake8-bandit) rules for security checks
  - Removed bandit dependency from dev requirements
  - Updated pre-commit hooks, CI workflow, and Makefile

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

[Unreleased]: https://github.com/MehdiZare/strapi-kit/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.6...v0.1.0
[0.0.6]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.5...v0.0.6
[0.0.5]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.4...v0.0.5
[0.0.4]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.3...v0.0.4
[0.0.3]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/MehdiZare/strapi-kit/releases/tag/v0.0.1
