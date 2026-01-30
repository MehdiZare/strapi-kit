# Strapi Migration Guide

Complete guide for migrating content between Strapi v5 instances using py-strapi.

## 📋 Table of Contents

1. [Quick Start](#quick-start)
2. [Simple Migration](#simple-migration)
3. [Full Migration](#full-migration)
4. [Common Scenarios](#common-scenarios)
5. [Troubleshooting](#troubleshooting)

---

## 🚀 Quick Start

### Prerequisites

```bash
# Install py-strapi
pip install strapi-kit

# Or with uv (faster)
uv pip install strapi-kit
```

### Get API Tokens

1. Open Strapi Admin Panel
2. Go to **Settings** → **API Tokens**
3. Create a new token with **Full Access**
4. Copy the token (you won't see it again!)

---

## 📦 Simple Migration

Use `simple_migration.py` for straightforward migrations with known content types.

### 1. Configure

Edit `examples/simple_migration.py`:

```python
SOURCE_URL = "http://localhost:1337"
SOURCE_TOKEN = "your-source-api-token-here"

TARGET_URL = "http://localhost:1338"
TARGET_TOKEN = "your-target-api-token-here"

CONTENT_TYPES = [
    "api::article.article",
    "api::author.author",
    "api::category.category",
]
```

### 2. Run

```bash
python examples/simple_migration.py
```

### 3. Output

```
🚀 Starting Strapi Migration
============================================================

📥 Exporting from http://localhost:1337...
✓ Exported 3 content types
✓ Saved backup to migration_backup.json

📤 Importing to http://localhost:1338...
✓ Imported 127 entities
✓ Uploaded 45 media files
✓ Resolved 89 relations

✅ Migration complete!
============================================================
```

---

## 🔧 Full Migration

Use `full_migration_v5.py` for production migrations with auto-discovery.

### Available Commands

```bash
# Export only
python examples/full_migration_v5.py export

# Import only
python examples/full_migration_v5.py import

# Full migration (export + import)
python examples/full_migration_v5.py migrate

# Verify migration
python examples/full_migration_v5.py verify

# Show help
python examples/full_migration_v5.py help
```

### Features

✅ **Auto-discovers all content types** - No need to list them manually
✅ **Progress bars** - See real-time progress
✅ **Detailed reports** - Know exactly what was migrated
✅ **Verification** - Compare source and target counts
✅ **Error handling** - Detailed error messages and recovery
✅ **Batch processing** - Efficient for large datasets

### Example: Full Migration

```bash
# Step 1: Configure credentials
# Edit examples/full_migration_v5.py:
SOURCE_CONFIG = StrapiConfig(
    base_url="http://localhost:1337",
    api_token=SecretStr("your-source-token"),
    api_version="v5",
    timeout=120.0,
)

TARGET_CONFIG = StrapiConfig(
    base_url="http://localhost:1338",
    api_token=SecretStr("your-target-token"),
    api_version="v5",
    timeout=120.0,
)

# Step 2: Run migration
python examples/full_migration_v5.py migrate

# Step 3: Verify
python examples/full_migration_v5.py verify
```

### Example Output

```
================================================================================
🚀 FULL STRAPI V5 MIGRATION
================================================================================
Source: http://localhost:1337
Target: http://localhost:1338

================================================================================
📦 EXPORTING ALL CONTENT FROM SOURCE STRAPI V5 INSTANCE
================================================================================

✓ Connected to source: http://localhost:1337
  API Version: v5

🔍 Discovering content types...
   Found 12 content types:
   - api::article.article
   - api::author.author
   - api::category.category
   - api::tag.tag
   - api::comment.comment
   ...

📥 Exporting 12 content types...
[████████████████████████████████████████] 100% | Processing articles

💾 Saving export data to ./strapi_migration/export_data.json...

================================================================================
✅ EXPORT COMPLETE
================================================================================
Content types exported: 12
Total entities exported: 1,847
Media files downloaded: 234
Export file: ./strapi_migration/export_data.json
Media directory: ./strapi_migration/media
Total export size: 45.32 MB


================================================================================
📦 IMPORTING ALL CONTENT TO TARGET STRAPI V5 INSTANCE
================================================================================

📂 Loading export data from ./strapi_migration/export_data.json...
   Content types: 12
   Total entities: 1,847
   Media files: 234

✓ Connected to target: http://localhost:1338
  API Version: v5

📤 Importing 1,847 entities...
[████████████████████████████████████████] 100% | Importing articles

================================================================================
✅ IMPORT COMPLETE
================================================================================
Entities imported: 1,847
Entities updated: 0
Entities skipped: 0
Media files uploaded: 234
Relations resolved: 3,421

📋 ID Mapping (sample):
   api::article.article:
      doc_abc123 → doc_xyz789
      doc_def456 → doc_uvw012
      doc_ghi789 → doc_rst345
   api::author.author:
      doc_auth01 → doc_auth99
      doc_auth02 → doc_auth88
      doc_auth03 → doc_auth77

================================================================================
✅ MIGRATION COMPLETED SUCCESSFULLY
================================================================================
```

---

## 💡 Common Scenarios

### Scenario 1: Migrate Specific Content Types Only

Use **simple_migration.py** and specify only the content types you need:

```python
CONTENT_TYPES = [
    "api::article.article",
    # Only articles, no authors or categories
]
```

### Scenario 2: Migrate Everything

Use **full_migration_v5.py** which auto-discovers all content types:

```bash
python examples/full_migration_v5.py migrate
```

### Scenario 3: Migrate Without Media Files

Edit either script to exclude media:

```python
export_data = exporter.export_content_types(
    content_types,
    include_media=False,  # Don't download media
)
```

### Scenario 4: Test Migration First (Dry Run)

Export first, inspect the JSON, then import:

```bash
# Export
python examples/full_migration_v5.py export

# Inspect the export file
cat ./strapi_migration/export_data.json | jq '.'

# Import when ready
python examples/full_migration_v5.py import
```

### Scenario 5: Migrate from v4 to v5

The library handles both v4 and v5 automatically. Just set:

```python
SOURCE_CONFIG = StrapiConfig(
    base_url="http://localhost:1337",
    api_token=SecretStr("source-token"),
    api_version="v4",  # Source is v4
)

TARGET_CONFIG = StrapiConfig(
    base_url="http://localhost:1338",
    api_token=SecretStr("target-token"),
    api_version="v5",  # Target is v5
)
```

The library automatically normalizes responses and handles the differences.

### Scenario 6: Backup Before Deployment

Create a backup before deploying:

```bash
# Backup production
python examples/full_migration_v5.py export

# File is saved to: ./strapi_migration/export_data.json
# Copy this file to a safe location

# If something goes wrong, restore:
python examples/full_migration_v5.py import
```

---

## 🔍 Troubleshooting

### Issue: "Content type not found"

**Problem:** Content type UID is incorrect.

**Solution:** Get correct UIDs from Strapi Admin:
- Go to **Content-Type Builder**
- Click on your content type
- Copy the API ID (e.g., `api::article.article`)

### Issue: "Authentication failed"

**Problem:** API token is invalid or expired.

**Solution:**
1. Generate a new API token in Strapi Admin
2. Ensure token has **Full Access** permissions
3. Use `SecretStr()` to wrap the token:
   ```python
   api_token=SecretStr("your-token-here")
   ```

### Issue: "Relation not resolved"

**Problem:** Related content type was not exported.

**Solution:** Include all related content types:
```python
CONTENT_TYPES = [
    "api::article.article",
    "api::author.author",      # Article has author relation
    "api::category.category",  # Article has category relation
]
```

### Issue: "Media file not found"

**Problem:** Media files were deleted or moved.

**Solution:** Ensure media directory exists and contains files:
```bash
ls -la ./strapi_migration/media/
```

### Issue: "Migration is slow"

**Problem:** Large dataset or slow connection.

**Solutions:**
1. Increase timeout:
   ```python
   StrapiConfig(
       base_url="http://localhost:1337",
       api_token=SecretStr("token"),
       timeout=300.0,  # 5 minutes
   )
   ```

2. Adjust batch size:
   ```python
   options = ImportOptions(
       batch_size=25,  # Smaller batches
   )
   ```

3. Run during off-peak hours

### Issue: "Out of memory"

**Problem:** Too many entities loaded at once.

**Solution:** Use the full migration script which processes in batches:
```bash
python examples/full_migration_v5.py migrate
```

### Issue: "Connection timeout"

**Problem:** Network issues or slow server.

**Solutions:**
1. Check network connectivity
2. Increase timeout (see above)
3. Retry the operation:
   ```python
   StrapiConfig(
       base_url="...",
       api_token=SecretStr("..."),
       timeout=120.0,
       retry=RetryConfig(
           max_attempts=5,
           initial_wait=2.0,
       )
   )
   ```

---

## 📚 Additional Resources

- **Main Documentation**: [README.md](../README.md)
- **API Reference**: [Documentation](https://mehdizare.github.io/strapi-kit/)
- **Export/Import Guide**: [docs/export-import.md](../docs/export-import.md)
- **GitHub Issues**: [Report bugs](https://github.com/mehdizare/py-strapi/issues)

---

## 🤝 Need Help?

1. Check this guide's [Troubleshooting](#troubleshooting) section
2. Read the [main README](../README.md)
3. Open an issue on [GitHub](https://github.com/mehdizare/py-strapi/issues)

---

**Happy Migrating! 🚀**
