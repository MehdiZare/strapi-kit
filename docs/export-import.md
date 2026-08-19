# Export/Import Guide

## Overview

strapi-kit provides comprehensive export/import functionality for migrating Strapi content between instances. The system automatically handles relation resolution using content type schemas.

## Quick Start

### Export

```python
from strapi_kit import SyncClient, StrapiExporter, StrapiConfig

config = StrapiConfig(base_url="http://localhost:1337", api_token="token")

with SyncClient(config) as client:
    exporter = StrapiExporter(client)

    # Export content types. Default document_status=DRAFT (v5 status=draft).
    # Pass document_status=None for published-only.
    # include_media defaults to True and then requires media_dir.
    export_data = exporter.export_content_types(
        ["api::article.article", "api::author.author"],
        include_media=False,
    )

    # Save to file
    exporter.save_to_file(export_data, "export.json")
```

### Import

```python
from strapi_kit import StrapiImporter

target_config = StrapiConfig(base_url="http://localhost:1338", api_token="token")

with SyncClient(target_config) as client:
    importer = StrapiImporter(client)

    # Load and import
    export_data = StrapiExporter.load_from_file("export.json")
    result = importer.import_data(export_data)

    print(f"Imported {result.entities_imported} entities")
```

## Relation Resolution

### How It Works

Relations are automatically resolved using content type schemas:

1. **During Export**: Schemas are fetched from the Content-Type Builder API
2. **Schema Storage**: Schemas are included in the export metadata
3. **During Import**: Relations are resolved by looking up target content types from schemas.
Component schemas walked at export are stored in `metadata.component_schemas` so
nested paths such as `seo[0].author` resolve without a destination Content-Type
Builder fetch.

**Example**: When importing an article with `{"author": ["auth-doc"]}`, the
system:
1. Looks up the schema to find that `author` targets `"api::author.author"`
2. Maps the source `documentId` to the destination `documentId`
3. PUTs `{"data": {"author": "new-author-doc"}}` via `relation_write()`

Relation writes cover top-level fields and nested component / dynamic-zone
paths such as `seo[0].author`. Nested writes merge dest `documentId`s into
a copy of the exported component object so scalar component fields are
kept. Paths that cannot be applied (missing component shell) are import
errors (`success=False`). On dry-run those nested skips are warnings and
do not flip `success`. Per-target dest-resolution misses are attached to
`result.unresolved_relations` / `result.relations_unresolved`. A field
that resolved only a subset of IDs is not written. On dry-run, `success`
is write-safety; check `relations_unresolved`. On live import, each dest
miss is an error and flips `success`.

On a v4 destination (create returns no `documentId`), import falls back to
numeric `build_nested_numeric_payload` / `PUT {endpoint}/{new_id}`.
`build_relation_payload` remains a public helper.

Media fields are converted to a dest write id (`documentId` when the
upload recorded one, otherwise the remapped numeric id). Populate blobs
(`mime`, `url`, source `documentId`) are not posted.

`locale=*` export yields one row per locale with the same `documentId`
(``locale=all`` is a fallback when ``*`` is rejected).
Import keys existence and writes by `(documentId, locale)`. The first locale
of a source document creates (or updates/skips that locale). Later locales
of the same source `documentId` write `PUT {destDoc}?locale=`. Relation
updates and publish pass the row locale. `ConflictResolution.SKIP` is
per-locale: a missing locale is written even when another locale of the
same document already exists.

### Schema Structure

Schemas include field metadata for relation resolution:

```python
{
  "uid": "api::article.article",
  "pluralName": "articles",
  "fields": {
    "author": {
      "type": "relation",
      "relation": "manyToOne",
      "target": "api::author.author"
    }
  }
}
```

## Export Options

### Basic Export

```python
export_data = exporter.export_content_types(
    ["api::article.article", "api::author.author"],
    include_media=False,
)
```

Schemas are always included for relation resolution. Completeness
defaults to `document_status=DocumentStatus.DRAFT` (v5 `status=draft`,
confirmed v4 `publicationState=preview`). Pass `document_status=None`
for published-only.

Import conflict detection follows that default: a published miss is
retried with `status=draft` so a draft-only re-import does not create a
second document.

Relation and media extraction accept both the v4 `{ "data": ... }`
wrapper and flat Strapi 5 `populate=*` objects (`documentId` / `mime`
at the field root). Import writes relations with `relation_write()`
(documentId strings). Export/import require `pluralName` from the
content-type schema and do not invent a path from the UID.

### Export with Media

```python
export_data = exporter.export_content_types(
    ["api::article.article"],
    include_media=True,
    media_dir="export/media"
)
```

### Progress Tracking

```python
def progress_callback(current, total, message):
    print(f"[{current}/{total}] {message}")

export_data = exporter.export_content_types(
    ["api::article.article"],
    progress_callback=progress_callback
)
```

## Import Options

### Basic Import

```python
result = importer.import_data(export_data)
```

### Import Options

```python
from strapi_kit.models import ImportOptions, ConflictResolution

options = ImportOptions(
    skip_relations=False,          # Import relations (default)
    import_media=True,              # Import media files
    conflict_resolution=ConflictResolution.SKIP,  # Skip conflicts
    dry_run=False                   # Actually perform import
)

result = importer.import_data(export_data, options)
```

### Conflict Resolution Strategies

Conflicts are per `(documentId, locale)`. A missing locale of an existing
document is not a conflict.

- `SKIP`: Skip locales that already exist; write missing locales
- `UPDATE`: Overwrite existing locales; write missing locales
- `FAIL`: Finish the whole entity/relation/publish pass, including later
  rows. Write missing locales. Do not overwrite existing locale fields or
  their outbound relations. Then raise `ImportExportError` (import-level
  failure, not fail-fast on the first hit). The exception `details` include
  what already landed (`entities_imported`, `relations_imported`, `errors`,
  `relations_unresolved`). Dry-run still probes `(documentId, locale)` and
  raises; it does not write.

## JSONL export

`export_to_jsonl` writes metadata first, then entities, then a media
manifest. After the stream it rewrites line 1 with real
`total_entities` / `total_media` (sibling temp copy, O(1) memory).
Older files that still have `0` are recounted on import.

## Working with Relations

### Ensuring Complete Exports

To ensure all relations are resolved, include all related content types:

```python
# Include all related content types
export_data = exporter.export_content_types([
    "api::article.article",
    "api::author.author",      # Referenced by articles
    "api::category.category"   # Referenced by articles
])
```

### Checking Import Results

```python
result = importer.import_data(export_data)

# Check results
print(f"Success: {result.success}")
print(f"Entities imported: {result.entities_imported}")
print(f"Entities skipped: {result.entities_skipped}")
print(f"Unresolved dest relations: {result.relations_unresolved}")

# View ID mapping
for content_type, mapping in result.id_mapping.items():
    print(f"{content_type}:")
    for old_id, new_id in mapping.items():
        print(f"  {old_id} -> {new_id}")

# Check for warnings/errors
for warning in result.warnings:
    print(f"Warning: {warning}")

for error in result.errors:
    print(f"Error: {error}")
```

## Inspecting Schemas

You can inspect schemas in export data:

```python
# Load export
export_data = StrapiExporter.load_from_file("export.json")

# Inspect schemas
for content_type, schema in export_data.metadata.schemas.items():
    print(f"\n{content_type}:")
    print(f"  Display Name: {schema.display_name}")

    # Show relations
    for field_name, field in schema.fields.items():
        if field.type == "relation":
            print(f"  Relation: {field_name} -> {field.target}")
```

## Direct Schema Cache Usage

The schema cache can be used directly:

```python
from strapi_kit.cache import InMemorySchemaCache

with SyncClient(config) as client:
    cache = InMemorySchemaCache(client)

    # Get schema
    schema = cache.get_schema("api::article.article")

    # Check relation targets
    target = schema.get_field_target("author")
    print(target)  # "api::author.author"

    # Check if field is a relation
    is_rel = schema.is_relation_field("author")
    print(is_rel)  # True
```

## Troubleshooting

### Missing Relations

**Issue**: "No ID mapping for X" warning

**Cause**: A relation references a content type not included in the export

**Solution**: Include all related content types:

```python
export_data = exporter.export_content_types([
    "api::article.article",
    "api::author.author",  # Add missing content types
])
```

### Unresolved IDs

**Issue**: `"Could not resolve X ID Y for field Z"`

On live import this is an **error** (`success=False`) and a row on
`result.unresolved_relations`. On dry-run it is a **warning**; `success`
stays write-safe — check `relations_unresolved`.

**Cause**: A specific dest-relation target did not map (the entity was
omitted from the export, or the dest never received a mapping)

**Solutions**:
1. Ensure all entities are exported (check filters)
2. Import the missing entities first
3. Create the missing entities manually in the target instance
4. Review `result.unresolved_relations` for the field, source id, and
   target type

### Schema Fetch Failures

**Issue**: `ImportExportError: Schema with pluralName is required to export …`

**Cause**: Content-Type Builder is unreachable, the UID is wrong, or the
schema has no `pluralName` (export/import will not invent a path from
the UID).

**Solutions**:
1. Verify the content type UID
2. Check the API token can read Content-Type Builder
3. Confirm the schema includes `pluralName`

## Performance Considerations

- **Export**: +1 API call per content type (schema fetch)
- **Import**: No additional API calls (schemas loaded from export)
- **Memory**: ~10KB per content type schema (typical)
- **Cache**: In-memory only, cleared after operation

## Best Practices

1. **Export Complete Sets**: Always export related content types together
2. **Test First**: Use `dry_run=True` to validate imports. Dry-run
   counts missing dests as imported but does not map them to dest
   id `0` or the source `documentId`. It still reports unresolved
   dest relations as warnings (`relations_unresolved`) and counts
   `entities_to_publish` (live source rows this import would attempt to
   publish; SKIP/FAIL existing locales are not counted). Dry-run
   `success` is write-safety, not “relations would apply.” Existing dests
   (SKIP/UPDATE, or a missing locale of an existing document) still map
   real dest ids.
3. **Check Results**: Always review warnings, errors, and
   `relations_unresolved` after import
4. **Media Handling**: Download media files if needed for offline migration
5. **Version Compatibility**: Ensure source and target Strapi versions are compatible

## Schema Model Reference

```python
from strapi_kit.models import (
    ContentTypeSchema,
    FieldSchema,
    FieldType,
    RelationType
)

# ContentTypeSchema
schema = ContentTypeSchema(
    uid="api::article.article",
    display_name="Article",
    kind="collectionType",
    plural_name="articles",
    fields={...}
)

# Helper methods
target = schema.get_field_target("author")
is_rel = schema.is_relation_field("author")
```

## Example: Complete Migration

```python
from strapi_kit import SyncClient, StrapiConfig, StrapiExporter, StrapiImporter
from strapi_kit.models import ImportOptions

# Source instance
source_config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token="source-token"
)

# Target instance
target_config = StrapiConfig(
    base_url="http://localhost:1338",
    api_token="target-token"
)

# Export from source
with SyncClient(source_config) as client:
    exporter = StrapiExporter(client)
    export_data = exporter.export_content_types(
        [
            "api::article.article",
            "api::author.author",
            "api::category.category",
        ],
        include_media=False,
    )
    exporter.save_to_file(export_data, "migration.json")

# Import to target
with SyncClient(target_config) as client:
    importer = StrapiImporter(client)
    export_data = StrapiExporter.load_from_file("migration.json")

    # Dry run first
    result = importer.import_data(
        export_data,
        options=ImportOptions(dry_run=True)
    )

    if result.success:
        # Actual import
        result = importer.import_data(export_data)
        print(f"Migration complete: {result.entities_imported} entities")
```

## Related Documentation

- [Media Handling](media.md)
- [Type-Safe Queries](models.md)
