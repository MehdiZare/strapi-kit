# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Write-404 classification probes the write's own status first** —
  `update(..., classify_write_404=True)` and
  `remove(..., classify_write_404=True)` no longer treat a draft-only
  document as a missing-token problem when the write addressed the
  published version (`status=published` or omitted status). Probe 1 uses
  the write query (omit-status for `remove`). A hit is still
  `AuthorizationError`. A miss then probes `status=draft` only when the
  write was not already draft. Draft-only remains `NotFoundError`.
  A probe HTTP 404 is an answer, not a failed probe.

## [0.4.0] - 2026-08-19

i18n localizations, nested component/dynamic-zone relations, dest media
writes, FAIL-write missing locales, dry-run / JSONL preflight, and
Docker e2e CI. Tracker: #144.

### Upgrade notes

- Import restores extra locales of a shared `documentId`
  (`PUT {destDoc}?locale=`). 0.3.0 keyed existence on `documentId` only.
- `ConflictResolution.SKIP` is per-locale: a missing locale is written
  even when another locale of the same document exists.
- `ConflictResolution.FAIL` writes missing locales, does not overwrite
  existing locale fields or their outbound relations, then raises after
  the entity/relation/publish pass.
- Dry-run no longer maps dest id `0` or the source `documentId` as a
  write target. `success` on dry-run is write-safety; check
  `relations_unresolved` for dest-relation apply-ability.
- `ExportMetadata.total_entities` / `total_media` default to `None`
  (unknown). `0` is empty. Import recounts when either field is `None`
  or `0` so older JSONL files work.
- Relation IDs on `ExportedEntity.relations` and
  `UnresolvedRelation.old_id` are `StrictInt | StrictStr`. A
  numeric-looking documentId (`"5"`) stays a string. `RelationId` is
  not an `isinstance` target.

### Added

- Import restores i18n localizations of a shared `documentId`: existence
  and writes key on `(documentId, locale)`; later locales
  `PUT {destDoc}?locale=` (#104)
- SKIP is per-locale — a missing locale is not treated as a conflict
- Export metadata stores walked component schemas so nested import does
  not need a dest Content-Type Builder fetch (#118)
- Import remaps media via `FieldType.MEDIA` / component / dynamic-zone
  schema walk; `mime` heuristic is used when no schema is present or a
  field/component schema cannot be resolved (#120)
- FAIL dry-run probes `(documentId, locale)` and raises after the pass
  without writing (#121)
- Live e2e: FAIL writes the missing locale then raises (#117)
- Shared e2e ``delete_document`` helper for draft and per-locale DELETE
  (#119)
- GitHub Actions `E2E` workflow rebuilds the Docker fixture and runs
  `pytest tests/e2e --e2e` on a schedule, manually, or when e2e / library
  paths change. On failure it collects compose logs before teardown
  (#122 #130)
- FAIL writes missing locales, then aborts if any locale already existed (#111)
- Nested component / dynamic-zone relation writes on import (`seo[0].author`)
  (#105)
- `media_write()` and dest file `documentId` mapping so import posts write
  ids, not remapped populate blobs (#106)
- v4 destination relation import falls back to numeric
  `build_nested_numeric_payload` + `PUT {endpoint}/{id}` (#108)
- Live e2e Docker fixture: `localized-articles` i18n type + French locale,
  and import tests that restore `en`/`fr` on one `documentId` (#112)
- Dry-run reports unresolved dest relations / nested skips as warnings and
  counts `entities_to_publish` without writing (#135)
- JSONL import shares export-metadata preflight and relation-target
  validation with `import_data`. Preflight indexes every type in the
  file, including types omitted from `content_types`. When streaming
  metadata leaves `total_entities` / `total_media` at 0, import counts
  the file instead of trusting those fields (#136)
- Relation preflight warns when a row has relations but no export schema,
  or a path cannot resolve to a target type (#136)
- Import records per-target dest-resolution misses on
  `ImportResult.unresolved_relations` / `relations_unresolved` (#139 #141)
- `ImportResult.finalize()` snapshots `success` from `entities_failed`
  and `errors` (#146)

### Changed

- FAIL finishes the whole entity/relation/publish pass (including later
  rows). Existing locale fields and outbound relations are not overwritten.
  `ImportExportError.details` includes imported/failed counts and later-pass
  errors (#111)
- `RelationResolver` walks component fields by payload shape (`list` vs
  `dict`), not `repeatable`, matching schema-aware media remapping (#133)
- Dry-run import no longer records dest id `0` or the source `documentId`
  as a write target. Existing dests, including a missing locale of an
  existing document, still map real dest ids. A resolve-only later pass
  reports dest gaps without writing (#131 #135)
- JSONL import no longer pre-creates empty per-type mapping dicts; missing
  dests stay `{}`. Unmapped relation rows are recorded on `ImportResult`
  (#136)
- Component extract/strip unwraps v4 `{data: ...}` wrappers only when
  the object is `{data}` / `{data, meta}`, and logs unexpected scalar /
  non-dict list payloads (#137)
- Live import records an unmapped relation row as an error; dry-run
  still records it as a warning (#136)
- Incomplete dest-relation fields (a subset of IDs unresolved) are not
  written. Live records each miss as an error; dry-run records a
  warning and does not flip `success` (#139 #141)
- Relation-pass catches `StrapiError` only (with traceback) and lets
  unexpected exceptions propagate. Live `entities_to_publish` increments
  only when a dest documentId is queued; dry-run still counts source
  intent (#140)
- `export_to_jsonl` rewrites the metadata line with real
  `total_entities` / `total_media` after the stream. Import still
  recounts when those fields are 0 so older files work (#142)
- `ExportMetadata.total_entities` / `total_media` default to `None`
  (unknown). `0` is empty. Finished `export_content_types` snapshots
  both (`total_media == 0` when there is no media). Import still
  recounts when the fields are `None` or `0` so older JSONL files
  work (#148)

### Fixed

- Numeric dest fallback no longer reports documentId-path misses after
  IDs resolved (a v4 nested skip is not a dest-resolution miss)
- Relation IDs on `ExportedEntity.relations` and
  `UnresolvedRelation.old_id` are `StrictInt | StrictStr` so a
  numeric-looking documentId (`"5"`) is not coerced to `5` (#145)
- Extract rejects `bool` relation ids (`True` is a subclass of `int`)
  so extract and `ExportedEntity` validation agree (#150)
- E2E compose probe retries `docker compose` and does not fall back to a
  missing `docker-compose` v1 binary
- Export/import i18n streams use ``locale=*`` (Strapi 5.34 ``locale=all``
  returns an empty list). ``all`` remains a fallback when ``*`` is rejected.
- Export drops populate ``localizations`` so dest writes do not 400
  (`Invalid key localizations`).
- `exists()` draft `ValidationError` is absent only for unknown
  `status` / `publicationState` (a populate/filter 400 raises) (#107)

### Removed

- Unused export/import UID pluralization fallbacks and heuristic
  `extract_relations` / `strip_relations` (schema-aware extract/strip
  remain). `build_relation_payload` remains a public helper (#109)
