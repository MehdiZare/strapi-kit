# Export/Import Guide

## Overview

py-strapi provides comprehensive export/import functionality for migrating Strapi content between instances. The system automatically handles relation resolution using content type schemas.

## Quick Start

### Export

```python
from py_strapi import SyncClient, StrapiExporter, StrapiConfig

config = StrapiConfig(base_url="http://localhost:1337", api_token="token")

with SyncClient(config) as client:
    exporter = StrapiExporter(client)

    # Export content types
    export_data = exporter.export_content_types([
        "api::article.article",
        "api::author.author"
    ])

    # Save to file
    exporter.save_to_file(export_data, "export.json")
```

### Import

```python
from py_strapi import StrapiImporter

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
3. **During Import**: Relations are resolved by looking up target content types from schemas

**Example**: When importing an article with `{"author": [5]}`, the system:
1. Looks up the schema to find that `author` targets `"api::author.author"`
2. Uses the ID mapping to convert old ID 5 to the new ID in the target instance
3. Updates the article with the resolved relation

### Schema Structure

Schemas include field metadata for relation resolution:

```python
{
  "uid": "api::article.article",
  "fields": {
    "author": {
      "type": "relation",
      "relation": "manyToOne",
      "target": "api::author.author"  # Used for ID mapping
    }
  }
}
```

## Export Options

### Basic Export

```python
export_data = exporter.export_content_types([
    "api::article.article",
    "api::author.author"
])
```

Schemas are always included for relation resolution.

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
from py_strapi.models import ImportOptions, ConflictResolution

options = ImportOptions(
    skip_relations=False,          # Import relations (default)
    import_media=True,              # Import media files
    conflict_resolution=ConflictResolution.SKIP,  # Skip conflicts
    dry_run=False                   # Actually perform import
)

result = importer.import_data(export_data, options)
```

### Conflict Resolution Strategies

- `SKIP`: Skip entities that already exist
- `UPDATE`: Update existing entities (not yet implemented)
- `ERROR`: Raise error on conflicts

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
from py_strapi.cache import InMemorySchemaCache

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

**Issue**: "Could not resolve X ID Y for field Z" warning

**Cause**: A specific entity referenced by a relation wasn't included

**Solutions**:
1. Ensure all entities are exported (check filters)
2. Import the missing entities first
3. Create the missing entities manually in target instance

### Schema Fetch Failures

**Issue**: "Failed to fetch schema for X" error

**Cause**: Content-Type Builder API unavailable or content type doesn't exist

**Solutions**:
1. Verify content type UID is correct
2. Check API token has permissions to access Content-Type Builder
3. Verify Strapi instance is accessible

## Performance Considerations

- **Export**: +1 API call per content type (schema fetch)
- **Import**: No additional API calls (schemas loaded from export)
- **Memory**: ~10KB per content type schema (typical)
- **Cache**: In-memory only, cleared after operation

## Best Practices

1. **Export Complete Sets**: Always export related content types together
2. **Test First**: Use `dry_run=True` to validate imports
3. **Check Results**: Always review warnings and errors after import
4. **Media Handling**: Download media files if needed for offline migration
5. **Version Compatibility**: Ensure source and target Strapi versions are compatible

## Schema Model Reference

```python
from py_strapi.models import (
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
    fields={...}
)

# Helper methods
target = schema.get_field_target("author")
is_rel = schema.is_relation_field("author")
```

## Example: Complete Migration

```python
from py_strapi import SyncClient, StrapiConfig, StrapiExporter, StrapiImporter
from py_strapi.models import ImportOptions

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
    export_data = exporter.export_content_types([
        "api::article.article",
        "api::author.author",
        "api::category.category"
    ])
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

- [API Reference](api-reference.md)
- [Media Handling](media.md)
- [Type-Safe Queries](models.md)
