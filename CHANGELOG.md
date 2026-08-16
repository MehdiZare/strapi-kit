# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-08-16

Strapi 5 connector surface: Draft & Publish, Content-Type Builder discovery,
origin-path probe, relation writes, blocks ↔ markdown, and complete
stream/export. Tracker: [#55](https://github.com/MehdiZare/strapi-kit/issues/55).

### Upgrade notes

- `stream_entities` / `StrapiExporter` default to
  `document_status=DocumentStatus.DRAFT` (v5 `status=draft`, confirmed v4
  `publicationState=preview`). Pass `document_status=None` for
  published-only (the previous implicit default).
- `publish()` is stock REST `PUT ?status=published`. `unpublish()` and
  `discard_draft()` still need custom `/actions/*` routes (not stock REST).
- Non-JSON 2xx responses raise `UnstructuredResponseError` (not `FormatError`).
- `get_components()` and `get_content_types()` raise on unparsable items
  unless `skip_unparsable=True`.
- `StrapiQuery.filter()` / `.populate()` fail immediately on the wrong type.

### Added

- **Typed Blocks JSON nodes** ([#87](https://github.com/MehdiZare/strapi-kit/issues/87))
  - `BlockNode` / `TextNode` / … TypedDicts. `markdown_to_blocks()` returns `list[BlockNode]`
  - `blocks_to_markdown` still accepts `Sequence[object]` so unknown/malformed nodes stay lossy, not validation errors
- **`ContentTypeOptions`** ([#88](https://github.com/MehdiZare/strapi-kit/issues/88))
  - Known fields + `extra="allow"`. `draftAndPublish` is stripped from `options`; use first-class `draft_and_publish`
- **Stream/export `document_status`** ([#84](https://github.com/MehdiZare/strapi-kit/issues/84), [#85](https://github.com/MehdiZare/strapi-kit/issues/85))
  - Replaces the `include_drafts` bool. Default `DocumentStatus.DRAFT` (v5 `status=draft`, confirmed v4 `publicationState=preview`)
  - `document_status=None` is published-only. `StrapiExporter.export_content_types` / `export_to_jsonl` take the same argument
- **`UnstructuredResponseError.reason`** ([#86](https://github.com/MehdiZare/strapi-kit/issues/86))
  - Closed `UnstructuredResponseReason`: `empty_body`, `non_json`, `non_object`, `missing_data`, `unparseable_entity`
- **Stock REST `publish()`** ([#65](https://github.com/MehdiZare/strapi-kit/issues/65))
  - `publish()` is `PUT /api/{collection}/{documentId}?status=published` with `{"data": {}}`
  - `unpublish()` / `discard_draft()` stay on custom `POST /actions/*` routes (not registered by stock Strapi 5 REST)
- **Stream/export completeness** ([#81](https://github.com/MehdiZare/strapi-kit/issues/81), [#67](https://github.com/MehdiZare/strapi-kit/issues/67))
  - `stream_entities` / `stream_entities_async` call `assert_pagination_echo()` and stop on `total`, not `pageCount` alone
  - Default stream/export completeness is `document_status=DocumentStatus.DRAFT`; pass `document_status=None` for published-only
  - `get_many()` remains opt-in / unchanged
- **Yup/admin `details.errors` maps** ([#76](https://github.com/MehdiZare/strapi-kit/issues/76))
  - `field_errors` / `is_uniqueness_violation()` accept `{field: message | [message, ...]}` as well as the official REST list
- **`markdown_to_blocks` inline subset** ([#77](https://github.com/MehdiZare/strapi-kit/issues/77))
  - Bold, italic, strikethrough, inline code, links, images (no upload), and indented nested lists
- **Strapi 5 relation write helper** ([#54](https://github.com/MehdiZare/strapi-kit/issues/54))
  - `RelationWriteOp` StrEnum (`set`, `connect`, `disconnect`)
  - `relation_write()` builds v5 REST relation payloads from documentId strings
  - One-side: documentId string or `None` (raises `ValidationError` on 2+ ids)
  - Many-side: `{op: [documentIds]}` for set / connect / disconnect
  - Accepts `{"documentId": "..."}` objects and normalizes to the short string form
  - v5 writes take **documentId** strings, not numeric `id`; no v4 connect shapes
- **Pagination echo / maxLimit guard** ([#48](https://github.com/MehdiZare/strapi-kit/issues/48))
  - New opt-in `assert_pagination_echo(meta, *, requested_page, requested_page_size) -> int`
  - Verifies Strapi `meta.pagination` echo so a silent server `pageSize` cap (stock `maxLimit` default 100) cannot drop a collection window
  - Accepts `ResponseMeta`, `PaginationMeta`, or a raw meta/pagination dict
  - Digit-string totals/pages (`"12"`) are accepted; `bool` is not an int
  - Signed digit-string totals (`"-1"`) parse as negative ints and raise
    `ValidationError` for non-negative `total` (not "unreadable")
  - Absent `page` / `pageSize` keys are tolerated; a present but unreadable echo raises `ValidationError`
  - `get_many()` is unchanged by default — use the helper on import/export collection reads
- **Uniqueness 400 classifier and field-error flattening** ([#53](https://github.com/MehdiZare/strapi-kit/issues/53))
  - `is_uniqueness_violation()` detects Strapi unique-index collisions on `ValidationError` (message contains `must be unique`)
  - `format_validation_errors()` flattens `details.errors` to `path: message` lines
  - `ValidationError.field_errors` exposes parsed `(path, message)` pairs
  - HTTP 400/422 still maps to `ValidationError` (not `ConflictError`)
- **Origin-path escape hatch and admin information probe** ([#46](https://github.com/MehdiZare/strapi-kit/issues/46))
  - `request()`, `get()`, `post()`, `put()`, and `delete()` accept `api_prefix=True` (default keeps today's `/api` prefix)
  - `api_prefix=False` sends the path from the origin (e.g. `{base}/admin/information`)
  - `get_admin_information()` (sync + async) probes `GET {base}/admin/information`
  - Returns `AdminInformation` with `strapi_version` parsed from `strapiVersion` or `data.strapiVersion` (missing version is still a successful probe)
  - Content, Content-Type Builder, and upload endpoints remain under `/api`; `admin/` is origin-rooted
  - Default `get("admin/information")` still prefixes `/api` (no silent behaviour change)
  - Origin-rooted responses (`api_prefix=False`) do not drive v4/v5 content-API version detection
- **Collection REST path from `pluralName` only** ([#49](https://github.com/MehdiZare/strapi-kit/issues/49))
  - `collection_endpoint(content_type)` returns the REST collection id from `pluralName` / `info.plural_name`
  - Raises `ValidationError` when `pluralName` is missing or blank — never guesses from the UID (no appending `s`, no `apiID`, no splitting the UID)
  - `document_endpoint(content_type, document_id)` joins the collection id with a percent-encoded document id (`urllib.parse.quote(..., safe="")`); blank `document_id` raises `ValidationError`
  - Pass the returned string to `get_many` / `create` / `get_one` (the UID is schema identity, not a URL path)
  - Accepts `ContentTypeListItem`, `ContentTypeSchema`, or a dict with `info.pluralName` / `info.plural_name`
- **First-class Content-Type Builder Draft & Publish** ([#45](https://github.com/MehdiZare/strapi-kit/issues/45))
  - `ContentTypeListItem.draft_and_publish` and `ContentTypeSchema.draft_and_publish` are `bool | None`
  - `True` if any boolean `draftAndPublish` / `draft_and_publish` is `True` on the item, `options`, `schema`, or `schema.options`
  - `False` only when a boolean `False` was seen and no `True` was seen
  - `None` when the flag is absent — absence is not `False` and is never inferred from `publishedAt`
  - `ContentTypeListItem.options` retains other option keys (not only D&P)
  - `get_content_types(..., skip_unparsable=False)` raises `ValidationError` on malformed items; skip-and-log is opt-in
- **Strapi v5 Blocks field type and markdown converters** ([#51](https://github.com/MehdiZare/strapi-kit/issues/51))
  - Added `FieldType.BLOCKS = "blocks"` so Content-Type Builder attributes with `type: "blocks"` no longer fall through as unknown
  - Added `blocks_to_markdown()` → `MarkdownConversion(markdown, lossy_reasons)` for the official blocks tree (`paragraph`, `heading`, `list`/`list-item`, `quote`, `code`, `image`, `link`, `text` + bold/italic/strikethrough/code marks)
  - Lossy cases (underline, missing image/link URL, unknown or malformed nodes, trees deeper than 32) are recorded in `lossy_reasons` (deduplicated; empty iff faithful). Markdown metacharacters in text leaves are escaped before marks are applied; image/link destinations with `)` or spaces are wrapped in `<>`
  - Added `markdown_to_blocks()` write path (headings, paragraphs, fenced code, lists, blockquotes). Empty input pins one empty paragraph. Inline marks, links, images, and nested lists landed in #77.
  - Exported `FieldType`, `MarkdownConversion`, `blocks_to_markdown`, and `markdown_to_blocks` from the public `strapi_kit` API
- **v5 document status query** — `DocumentStatus` (`draft` / `published`) and
  `StrapiQuery.with_document_status()`. Emits `status=`. Mixing it with
  v4 `with_publication_state()` raises `ValidationError`.
- **v5 publicationFilter** — `PublicationFilter` (all 8 official REST values,
  including diagnostic `published-without-draft` / `published-with-draft`)
  and `StrapiQuery.with_publication_filter()`. Combines with `status=`.
  Mixing with v4 `with_publication_state()` raises `ValidationError`.
- **Draft-inclusive `exists()`** — `SyncClient.exists` / `AsyncClient.exists`
  (`collection`, `document_id`). Default GET (published), then one
  `status=draft` retry on `NotFoundError` only. Draft `NotFoundError` or
  `ValidationError` (Draft & Publish off) is `False`. Auth / 5xx / network
  on either read raise. Collection must be a single path segment;
  `document_id` is percent-encoded. A 200 with no `id` / `documentId`
  is treated as absent.
- **Opt-in write-404 classification** — `update(..., classify_write_404=True)`
  and `remove(..., classify_write_404=True)`. After a write `NotFoundError`,
  one draft GET: if the document is readable, raise `AuthorizationError`
  (token likely lacks Update/Publish) with original `status_code=404` on
  the exception and in details (`classified_from=write_404`); otherwise
  re-raise the original `NotFoundError`. Default `False` keeps today's
  mapping.
- **v5 document actions** — `SyncClient.publish` / `unpublish` /
  `discard_draft` and the async equivalents. `publish()` is stock REST
  `PUT ?status=published` (see #65). `unpublish` / `discard_draft` stay
  on `POST /api/{collection}/{documentId}/actions/{unpublish|discardDraft}`.
  `documentId` is percent-encoded.
- **Wire enums** — `DocumentAction`, `QueryParam`, and `HttpMethod`
  (`StrEnum`). Document-action paths, REST query keys, and HTTP verbs in
  `src/` go through the enums.
- **Root exports** — `DocumentStatus`, `PublicationState`,
  `PublicationFilter`, `DocumentAction`, `QueryParam`, and `HttpMethod`
  are importable from `strapi_kit`.
- **E2E Draft & Publish** — `tests/e2e/test_draft_publish.py` covers live
  Strapi 5 `status=` (`with_document_status`) on list and publish-on-write.
  Live `publish()` is asserted. `unpublish` / `discard_draft` are
  live-checked and skipped if stock REST 404s/405s
  ([#65](https://github.com/MehdiZare/strapi-kit/issues/65)).
  Avoids the article `status` attribute
  ([#68](https://github.com/MehdiZare/strapi-kit/issues/68)).
  Marked `@pytest.mark.e2e`; default CI still runs `pytest tests/unit`.
- **`MethodNotAllowedError`** for HTTP 405. HTTP **422** maps to
  `ValidationError` (same as 400).
- **`UnstructuredResponseError`** for 2xx responses that are empty or not
  a JSON object (the `"Created"` / empty-201 class). Empty **DELETE**
  bodies (any 2xx, including 204) stay success with `{}`. A 204 on
  POST/PUT/GET is treated as unstructured, not a created entity.
- **Percent-encoded document IDs on typed CRUD** ([#50](https://github.com/MehdiZare/strapi-kit/issues/50))
  - `BaseClient.document_path(collection, document_id)` builds `{collection}/{quote(document_id, safe="")}`
  - `get_one()`, `update()`, and `remove()` (sync and async) accept `document_id=` so the collection name and ID are joined safely
  - Blank collection or document ID raises `ValidationError`
  - Existing single-string endpoints such as `get_one("articles/abc")` remain supported
  - Document-action helpers reuse `document_path` so CRUD and actions share one encoder

### Changed

- **`markdown_to_blocks` lifts images to root siblings** ([#89](https://github.com/MehdiZare/strapi-kit/issues/89)) so mixed text+image is not nested under paragraph/list/quote
- **v5 multi-page streams keep `status=draft`** after version detect; only a confirmed v4 client rewrites later pages to `publicationState`
- **Auto + v4 streams re-fetch page 1** ([#93](https://github.com/MehdiZare/strapi-kit/issues/93)) with `publicationState` and discard the `status=` probe so drafts are not missed
- **`get_components()` raises on unparsable items** ([#79](https://github.com/MehdiZare/strapi-kit/issues/79)); skip-and-log is `skip_unparsable=True`
- **CTB `options` lift schema-root keys** ([#80](https://github.com/MehdiZare/strapi-kit/issues/80)) from stock `formatContentType` (not only nested `options`)
- **`StrapiQuery.filter()` fail-fast** ([#60](https://github.com/MehdiZare/strapi-kit/issues/60)) when the argument is not a `FilterBuilder`
- **`document_endpoint` shares `join_document_path` with `BaseClient.document_path`** ([#82](https://github.com/MehdiZare/strapi-kit/issues/82))
- **Typed writes require a `data` object** ([#58](https://github.com/MehdiZare/strapi-kit/issues/58)); parser `ValidationError` on a 2xx single-entity body is `UnstructuredResponseError` ([#59](https://github.com/MehdiZare/strapi-kit/issues/59))
- **`blocks_to_markdown` escapes ATX/list/quote prefixes** at the start of generated lines ([#78](https://github.com/MehdiZare/strapi-kit/issues/78))
- **E2E article attribute `status` renamed to `workflow_state`** ([#68](https://github.com/MehdiZare/strapi-kit/issues/68)); live D&P e2e covers stock `publish()` ([#44](https://github.com/MehdiZare/strapi-kit/issues/44))
- Every HTTP error now carries `status_code` on the exception (`401`,
  `404`, `429`, …), not only `ServerError`.
- Non-JSON 2xx responses raise `UnstructuredResponseError` instead of
  `FormatError`. `FormatError` remains for import/export payloads.
  A 2xx JSON **array** (stock Upload `GET /upload/files`) is still
  success and is wrapped as `{"data": [...]}`.
- **Dependency refresh** ([#33](https://github.com/MehdiZare/strapi-kit/issues/33),
  [#34](https://github.com/MehdiZare/strapi-kit/issues/34),
  [#35](https://github.com/MehdiZare/strapi-kit/issues/35),
  [#37](https://github.com/MehdiZare/strapi-kit/issues/37),
  [#38](https://github.com/MehdiZare/strapi-kit/issues/38)):
  GitHub Actions majors (`checkout` v6, `create-or-update-comment` v5,
  `create-pull-request` v8, `deploy-pages` v5, `codecov-action` v6,
  plus `setup-python` v7, `cache` v6, `upload-pages-artifact` v5,
  `setup-uv` v10.0.0, `action-gh-release` v3). Runtime/dev floors
  raised to current stables (`pydantic` 2.13, `mypy` 2.3, `ruff` 0.16,
  `pytest` 9.1, `respx` 0.23, and matching lockfile upgrades).
  `safety` stays `<4.0.0` so CI does not need a Safety API token.
- `StrapiQuery.populate()` raises `ValidationError` immediately when given
  a non-`Populate` value (for example a comma-separated string) instead of
  failing later in `to_query_params()`.
- Default CI and `make test` / `make test-verbose` / `make coverage` run
  `pytest tests/unit` so unmarked files under `tests/e2e/` cannot be
  collected. `make e2e` remains the live-Strapi path.

### Fixed

- **Typed write/parse status isolation** — `UnstructuredResponseError.status_code` is stored in a contextvar so concurrent `AsyncClient` requests cannot stamp the wrong HTTP status
- **`join_document_path` rejects whitespace-only collection names** (same as blank ids) so `"   /id"` cannot be emitted
- **Streamers raise on empty later pages** (or an empty first page with `total > 0`) instead of treating empty `data` as a complete collection
- **Default `status=draft` is dropped after a first-page 400** so collections without Draft & Publish still export
- **`markdown_to_blocks` image nodes include the official empty text child**
- `_normalize_content_type_item()` no longer drops Draft & Publish sources when flattening Strapi v5 CTB payloads
- `get_content_types()` raises `ValidationError` (not `AttributeError`/`TypeError`) when `data` is not a list or an item is not an object
- **Trailing `/api` stripped from `StrapiConfig.base_url`** ([#47](https://github.com/MehdiZare/strapi-kit/issues/47))
  - `https://cms.example.com/api` and `https://cms.example.com/api/` now normalize to `https://cms.example.com`
  - Prevents `_build_url` from producing `/api/api/...` when operators paste the REST root
  - Does not strip `/api` from the middle of a path (`https://host/api/v1` stays) or `/admin`
- **Document ID path injection on typed CRUD** ([#50](https://github.com/MehdiZare/strapi-kit/issues/50))
  - IDs containing `/`, `?`, `#`, or `%` no longer change the request path or inject query parameters when passed via `document_id=`

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

[Unreleased]: https://github.com/MehdiZare/strapi-kit/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/MehdiZare/strapi-kit/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.6...v0.1.0
[0.0.6]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.5...v0.0.6
[0.0.5]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.4...v0.0.5
[0.0.4]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.3...v0.0.4
[0.0.3]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/MehdiZare/strapi-kit/releases/tag/v0.0.1
