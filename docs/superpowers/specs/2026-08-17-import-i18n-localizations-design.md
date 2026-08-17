# Import i18n localizations (shared documentId)

**Tracker:** #104 (primary). Adjacent in this cut: JSONL import path, locale on relation PUTs, #107.
**Branch:** `feat/import-i18n-localizations` from `origin/dev`.
**Date:** 2026-08-17

## Problem

0.3.0 export already sends `locale=all` and stores `locale` on each `ExportedEntity`. Rows for `en` and `fr` share one source `documentId`.

Import still keys existence and SKIP/UPDATE on `documentId` only, and relation PUTs omit `locale`:

- New destination: each locale `POST`s a separate document.
- Same destination + default SKIP: the first locale hits; later locales are skipped.
- Relation writes land on the default locale even when the row is French.

Documented as a 0.3.0 limitation in `CHANGELOG.md` and `docs/export-import.md`.

`#107` is a leftover from the same existence work: import `_check_entity_exists` only treats `Invalid key status` / `Invalid key publicationState` as absent. Public `SyncClient.exists()` / `AsyncClient.exists()` still swallow **all** draft `ValidationError`s, so a populate/filter 400 looks like “does not exist.”

## Goal

Restore localizations as one Strapi 5 document:

1. Key existence and writes by `(documentId, locale)`.
2. First locale of a source document creates (or updates/skips that locale).
3. Later locales of the same source `documentId` write `PUT {destDocumentId}?locale=`.
4. Pass `locale` on relation updates (create/update/publish already do via `_write_query`).
5. Tighten public `exists()` to the same unknown-status-param rule import already uses.

## Non-goals

- #105 nested component / dynamic-zone relation writes.
- #106 media write via destination `documentId` / `media_write()`.
- #108 v4 destination relation import.
- #109 delete unused UID fallback and v4 heuristic helpers.
- Adding `locale` to the public `exists()` signature.
- Changing export (`locale=all` stream is already correct).
- Schema-flag detection of i18n (`ContentTypeSchema` does not store `pluginOptions.i18n`).

## Decision: SKIP is per-locale

`ConflictResolution.SKIP` means “this locale already exists on the destination document,” not “skip the whole document.”

If dest already has locale A and the export row is locale B:

- SKIP → write B as a localization (`PUT dest?locale=B`).
- UPDATE → write B the same way (create-or-update that locale).
- FAIL → only if locale B already exists.

A missing locale is never a conflict.

## Approaches considered

1. **Shared `documentId` restore (chosen).** First locale creates; later locales `PUT {destDoc}?locale=`. Matches stock Strapi 5 REST (`PUT /api/{plural}/{documentId}?locale=` creates or updates that locale).
2. **Per-locale creates only.** Stop skipping later locales but still `POST` each one. Dest `documentId`s diverge. Not a localization restore.
3. **Fail loud on a second locale.** Honest, does not restore i18n.

## Architecture

Three small units, all inside existing modules:

| Unit | Responsibility | Depends on |
| --- | --- | --- |
| Unknown-query-param predicates | Closed string checks for `Invalid key status` / `publicationState` / `locale` | `ValidationError` |
| Locale-aware existence probe | Published GET, then draft GET, optional locale, one no-locale retry on `Invalid key locale` | Client `get_one` |
| Import write decision | Create vs localize vs skip/update/fail; shared by JSON and JSONL | Probe + mappings + `_write_query` |

Relation pass stays a second pass. It already resolves dest `documentId`; it must also send `_write_query(entity)` so the PUT is locale-scoped.

## Data flow

For each exported row `(content_type, entity.id, entity.document_id, entity.locale, entity.data)`:

```
source_doc = entity.document_id
locale     = entity.locale
dest_doc   = result.doc_id_to_new_document_id[ct].get(source_doc)   # earlier locale this run

if source_doc:
    this_locale = probe(endpoint, source_doc, locale)   # dest may reuse source ids

if this_locale is a hit:
    dest_doc = dest_doc or this_locale.document_id or source_doc
    SKIP / UPDATE / FAIL for this locale only
elif dest_doc is not None:
    PUT dest_doc ?locale=     # another locale already imported this run
elif source_doc and probe_any_locale(endpoint, source_doc) is a hit:
    dest_doc = hit.document_id or source_doc
    PUT dest_doc ?locale=     # same-instance, this locale missing
else:
    POST ?locale=             # new document
    dest_doc = response.document_id
```

Record mappings after every successful write or SKIP so later locales and relation writes share one dest `documentId`.

Strapi 5 localizations share `documentId` and have distinct numeric `id`s. `id_mapping[ct][entity.id]` stays per-row. `doc_id_to_new_document_id[ct][source_doc]` is the shared dest document.

## Existence probe

Replace `_check_entity_exists(endpoint, document_id) -> int | None` with a probe that returns enough to map:

```python
@dataclass(frozen=True, slots=True)
class _ExistingDocument:
    id: int
    document_id: str | None
```

`_probe_document(endpoint, document_id, locale: str | None) -> _ExistingDocument | None`

Rules (same raise/absent policy as today’s import probe):

1. `GET {path}` with `locale=` when `locale` is set; without locale otherwise.
2. Hit with an identifiable entity (`id` or `documentId`) → return it.
3. `NotFoundError` → try once more with `status=draft` (and the same locale).
4. Draft `NotFoundError` → absent.
5. Draft `ValidationError` that is unknown `status` / `publicationState` → absent.
6. Any other `ValidationError` except unknown `locale` (below) → raise.
7. Auth / 5xx / network → raise.

**Unknown `locale`:** if a GET (published or draft) is `Invalid key locale`, retry that GET once without `locale`. Same pattern as export dropping `locale=all` only on that message. A populate/filter 400 still raises.

`probe_any_locale` is a collection GET
`filters[documentId][$eq]={source_doc}&locale=all` (published, then draft).
A no-locale document GET is the default locale only. `Invalid key locale`
falls back to that default-locale document GET.

Rows with no `document_id` skip the probe and always `POST` (today’s behavior).

Rows with no `locale` probe and write without `locale` (non-i18n).

## Writes

Reuse `_write_query(entity)` for create, update, localize, publish, and relation PUT.

- **Create:** `client.create(endpoint, data, query=write_query)` — new dest document.
- **Update existing locale:** `client.update(endpoint, data, document_id=dest_doc, query=write_query)`.
- **Add missing locale:** same `update` call. Stock REST create-or-updates that locale on the existing document. Do not `POST`.
- **Publish:** already `publish(..., query=_write_query(entity))`. Queue one publish per imported locale row that had `published_at`.

Count a newly written localization as `entities_imported`. Count an UPDATE of an existing locale as `entities_updated`. SKIP increments `entities_skipped`.

Dry-run does not write; it still increments `entities_imported` as today.

## Relation pass

`_apply_entity_relations` today:

```python
self.client.update(endpoint, payload, document_id=new_document_id)
# or update(f"{endpoint}/{new_id}", payload)
```

Change: pass `query=self._write_query(entity)` on both branches.

Do not change payload shape (`relation_write()` / top-level keys only). Nested prefixed keys stay #105.

JSONL pass 2 must use the same helper so locale is not in-memory-only.

## Public `exists()` (#107)

`SyncClient.exists` and `AsyncClient.exists` draft probe:

```python
except ValidationError as error:
    if is_unknown_status_param(error):
        return False
    raise
```

A draft `Invalid key populate` (or any non-status 400) raises.

Do not add a `locale` argument.

## Shared predicates

Extract the two message checks so streaming, import, and `exists()` cannot drift:

- `is_unknown_status_param(error: ValidationError) -> bool`
  `"invalid key status"` or `"invalid key publicationstate"` in `str(error).lower()`.
- `is_unknown_locale_param(error: ValidationError) -> bool`
  `"invalid key locale"` in `str(error).lower()`.

Place them next to the existing stream helper (move `_is_unknown_stream_status_param` to a small importable function and keep a thin alias if needed). Importer existence and client `exists()` call the same function. No new public package export unless one already wraps stream helpers.

## Error handling

- Failed localize `PUT` is an import error (`add_error`, `entities_failed`), same as failed create.
- Existence probe 401/403/5xx still abort the row as today (auth on probe must not look absent).
- Writing `?locale=` to a non-i18n destination is a `ValidationError` on create/update and is recorded as a row error. Do not retry the write without locale (that would create a second default-locale document).
- Mapping a localization onto a dest `documentId` that this run already created is required; never `POST` a second locale of the same source `documentId` once a dest mapping exists.

## Testing

Unit tests in `tests/unit/test_export_import.py` and `tests/unit/test_document_exists.py`. respx mocks, both JSON and JSONL where the write decision lives in both paths.

Required cases:

1. **New dest, two locales, same source `documentId`.** One `POST ?locale=en`, one `PUT {destDoc}?locale=fr`. Dest `documentId` from the create response is reused. `doc_id_to_new_document_id` has one entry.
2. **Order independence.** `fr` row first, then `en` — still one create and one localize PUT. Do not assume default locale arrives first.
3. **Same dest SKIP, en exists, fr missing.** GET `?locale=en` hits; GET `?locale=fr` 404s; `PUT {sourceDoc}?locale=fr`. `entities_skipped == 1`, `entities_imported == 1`.
4. **Same dest SKIP, both locales exist.** Two skips, no create/update.
5. **FAIL** only when this locale exists; missing sibling locale is still written.
6. **Relation PUT includes `locale`.** After a French row, the relation update query has `locale=fr`.
7. **Publish includes `locale`.** Already covered for `en`; add a French live row.
8. **JSONL** matches case 1 (create + localize, shared dest `documentId`).
9. **No locale on row** — behavior unchanged (no `locale` query param).
10. **Existence `Invalid key locale`** — retry without locale; do not raise.
11. **`exists()` draft `Invalid key populate` raises** (sync and async). Draft `Invalid key status` still returns False.

No live e2e requirement for this cut (e2e fixture is not i18n). If a later cut adds i18n to the Docker app, add a live localize test then.

## Docs

- `CHANGELOG.md` `[Unreleased]`: restore localizations; SKIP is per-locale; `exists()` no longer swallows unrelated draft 400s.
- `docs/export-import.md`: replace the “keys existence on documentId only” paragraph with the restore contract.
- `docs/changelog.md`: same user-facing note as the changelog.

## Files

- `src/strapi_kit/export/importer.py` — probe, write decision, relation `query=`.
- `src/strapi_kit/client/sync_client.py` / `async_client.py` — `exists()` draft 400 filter.
- `src/strapi_kit/operations/streaming.py` (or a tiny shared util it already owns) — predicates.
- `tests/unit/test_export_import.py`
- `tests/unit/test_document_exists.py`
- `CHANGELOG.md`, `docs/export-import.md`, `docs/changelog.md`

## Success criteria

- Importing an `en`+`fr` export onto an empty v5 dest yields one dest `documentId` with two locales.
- Re-import with SKIP adds only missing locales and does not create a second document.
- Relation and publish requests for a locale-scoped row include that locale.
- `exists()` raises on a draft populate 400.
- `make test`, `mypy src/strapi_kit/`, and `ruff check` pass.
