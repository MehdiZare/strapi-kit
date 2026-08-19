# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The repository [`CHANGELOG.md`](https://github.com/MehdiZare/strapi-kit/blob/dev/CHANGELOG.md)
is the full Keep a Changelog record (including 0.0.x). This page is the
user-facing summary.

## [Unreleased]

Import restores i18n localizations of a shared `documentId` (first locale
creates; later locales `PUT {destDoc}?locale=`). SKIP is per-locale.
FAIL writes missing locales, does not overwrite existing locales or their
outbound relations, then raises after the full write pass.
`exists()` no longer treats an unrelated draft 400 as “does not exist.”
Import writes nested component/dynamic-zone relations, posts dest media
ids (`media_write()`), and falls back to numeric relation PUTs on a v4
destination.
The e2e Docker fixture includes an i18n `localized-articles` type.
Export metadata includes walked component schemas. Media remapping
follows `FieldType.MEDIA` when a schema is present.
FAIL dry-run probes locale conflicts and raises without writing.
Dry-run no longer maps missing dests to id `0` or the source
`documentId`; existing dests still map real dest ids. Dry-run reports
unresolved dest relations as warnings (`relations_unresolved`) and
counts `entities_to_publish`. `success` on dry-run is write-safety,
not “relations would apply.” Incomplete dest-relation fields are not
written. JSONL export persists `total_entities` / `total_media` on the
metadata line. JSONL import shares preflight validation with
`import_data` and does not pre-create empty mapping dicts. Component
extract/strip unwraps v4 `{data}` / `{data, meta}` wrappers and logs
unexpected payload shapes.
The e2e workflow also runs on library path changes and keeps the
compose stack until logs are collected.

## [0.3.0] - 2026-08-16

v5 export/import populate contract. Trackers: #96 #97 #98 #99 #100 #101.

### Upgrade notes

- Export/import require `pluralName` from the content-type schema (no UID
  path invention).
- Import writes relations with `relation_write()` (v5 documentId strings).
- `ExportedEntity` stores `published_at` / `locale`; import publishes live
  source documents after relation writes.
- Extra locales of the same `documentId` are not restored as i18n
  localizations (follow-up).
- Short stream pages before `total` raise instead of stopping early.
- `upload_file` / `upload_files` re-raise auth / not-found / server errors.

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
- Import existence checks are draft-inclusive (published GET, then
  `status=draft`). Auth / 5xx / network errors on the probe are no longer
  treated as “does not exist”.
- Export/import still extracts relations and media from the v4
  `{data: ...}` populate shape. Flat Strapi 5 `populate=*` objects are a
  follow-up (do not treat 0.2.0 as a complete v5 migrate path).

### Added

- Typed Blocks nodes (`BlockNode`, `TextNode`, …)
  ([#87](https://github.com/MehdiZare/strapi-kit/issues/87)).
- `ContentTypeOptions` with `extra="allow"`; Draft & Publish is stripped
  from `options` ([#88](https://github.com/MehdiZare/strapi-kit/issues/88)).
- Stream/export `document_status`
  ([#84](https://github.com/MehdiZare/strapi-kit/issues/84),
  [#85](https://github.com/MehdiZare/strapi-kit/issues/85)).
- `UnstructuredResponseError.reason`
  ([#86](https://github.com/MehdiZare/strapi-kit/issues/86)).
- Stock REST `publish()`
  ([#65](https://github.com/MehdiZare/strapi-kit/issues/65)).
- Stream/export completeness via pagination echo
  ([#81](https://github.com/MehdiZare/strapi-kit/issues/81),
  [#67](https://github.com/MehdiZare/strapi-kit/issues/67)).
- Inline `markdown_to_blocks` ([#77](https://github.com/MehdiZare/strapi-kit/issues/77)).
- Relation write helper `relation_write()` / `RelationWriteOp`
  ([#54](https://github.com/MehdiZare/strapi-kit/issues/54)).
- `assert_pagination_echo()`
  ([#48](https://github.com/MehdiZare/strapi-kit/issues/48)).
- `is_uniqueness_violation()` and `ValidationError.field_errors`
  ([#53](https://github.com/MehdiZare/strapi-kit/issues/53),
  [#76](https://github.com/MehdiZare/strapi-kit/issues/76)).
- Origin-path `api_prefix=False` and `get_admin_information()`
  ([#46](https://github.com/MehdiZare/strapi-kit/issues/46)).
- `collection_endpoint()` / `document_endpoint()` from `pluralName` only
  ([#49](https://github.com/MehdiZare/strapi-kit/issues/49)).
- First-class CTB `draft_and_publish` (`True` / `False` / `None`)
  ([#45](https://github.com/MehdiZare/strapi-kit/issues/45)).
- Blocks ↔ markdown and `FieldType.BLOCKS`
  ([#51](https://github.com/MehdiZare/strapi-kit/issues/51)).
- `DocumentStatus`, `PublicationFilter`, `exists()`, write-404 classify,
  `publish` / `unpublish` / `discard_draft`, wire enums,
  `MethodNotAllowedError`, `UnstructuredResponseError`.
- Percent-encoded `document_id=` on typed CRUD
  ([#50](https://github.com/MehdiZare/strapi-kit/issues/50)).

### Changed

- `markdown_to_blocks` lifts images to root siblings
  ([#89](https://github.com/MehdiZare/strapi-kit/issues/89)).
- v5 multi-page streams keep `status=draft` after detect; auto + v4
  re-fetch page 1 with `publicationState`
  ([#93](https://github.com/MehdiZare/strapi-kit/issues/93)).
- `get_components()` raises unless `skip_unparsable=True`
  ([#79](https://github.com/MehdiZare/strapi-kit/issues/79)).
- CTB options lift schema-root keys
  ([#80](https://github.com/MehdiZare/strapi-kit/issues/80)).
- `filter()` fail-fast
  ([#60](https://github.com/MehdiZare/strapi-kit/issues/60));
  shared document path encoder
  ([#82](https://github.com/MehdiZare/strapi-kit/issues/82));
  write `data` object + parser wrap
  ([#58](https://github.com/MehdiZare/strapi-kit/issues/58),
  [#59](https://github.com/MehdiZare/strapi-kit/issues/59)).
- Line-prefix escaping in `blocks_to_markdown`
  ([#78](https://github.com/MehdiZare/strapi-kit/issues/78)).
- Every HTTP error carries `status_code`. Non-JSON 2xx is
  `UnstructuredResponseError`. Default CI / `make test` runs
  `pytest tests/unit` only.

### Fixed

- Concurrent `AsyncClient` writes no longer stamp the wrong HTTP status
  on `UnstructuredResponseError`.
- `join_document_path` rejects whitespace-only collection names.
- Streamers raise on empty later pages (or an empty first page with
  `total > 0`).
- Default `status=draft` is dropped after a first-page 400 (Draft &
  Publish off).
- Trailing `/api` stripped from `StrapiConfig.base_url`
  ([#47](https://github.com/MehdiZare/strapi-kit/issues/47)).
- Document IDs containing `/`, `?`, `#`, or `%` are percent-encoded
  ([#50](https://github.com/MehdiZare/strapi-kit/issues/50)).

## [0.1.0] - 2026-02-04

### Fixed

- Race conditions in async bulk operations
  ([#30](https://github.com/MehdiZare/strapi-kit/pull/30)).
- JSONL media manifest no longer consumes the entity stream.
- v5 string relation IDs (`documentId`) on import.
- JSONL import path traversal protection and two-pass streaming
  ([#29](https://github.com/MehdiZare/strapi-kit/pull/29)).
- `update_media` version detection and streaming downloads
  ([#28](https://github.com/MehdiZare/strapi-kit/issues/28)).

### Added

- Schema-driven relation extraction and JSONL streaming export/import
  ([#28](https://github.com/MehdiZare/strapi-kit/issues/28)).

## [0.0.6] - 2026-02-03

### Added

- Content-Type Builder API, UID conversion utilities, SEO detection.

### Fixed

- Extra `STRAPI_*` env vars no longer break `StrapiConfig`.
- v5 Content-Type Builder list flattening.

[Unreleased]: https://github.com/MehdiZare/strapi-kit/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/MehdiZare/strapi-kit/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.6...v0.1.0
[0.0.6]: https://github.com/MehdiZare/strapi-kit/compare/v0.0.5...v0.0.6
