#!/usr/bin/env python3
"""Simple Strapi Migration Example

A simplified example for migrating content between two Strapi instances.
Perfect for getting started quickly.

Usage:
    1. Update SOURCE_URL, SOURCE_TOKEN, TARGET_URL, TARGET_TOKEN below
    2. Update CONTENT_TYPES with your content types
    3. Run: python simple_migration.py
"""

from pydantic import SecretStr

from strapi_kit import StrapiConfig, StrapiExporter, StrapiImporter, SyncClient

# ============================================================================
# CONFIGURATION - Update these values
# ============================================================================

SOURCE_URL = "http://localhost:1337"
SOURCE_TOKEN = "your-source-api-token-here"

TARGET_URL = "http://localhost:1338"
TARGET_TOKEN = "your-target-api-token-here"

# List your content types here
CONTENT_TYPES = [
    "api::article.article",
    "api::author.author",
    "api::category.category",
]

# ============================================================================


def main() -> None:
    """Perform a simple migration from source to target."""
    print("🚀 Starting Strapi Migration")
    print("=" * 60)

    # Configure source and target
    source_config = StrapiConfig(
        base_url=SOURCE_URL,
        api_token=SecretStr(SOURCE_TOKEN),
    )

    target_config = StrapiConfig(
        base_url=TARGET_URL,
        api_token=SecretStr(TARGET_TOKEN),
    )

    # Step 1: Export from source
    print(f"\n📥 Exporting from {SOURCE_URL}...")
    with SyncClient(source_config) as source_client:
        exporter = StrapiExporter(source_client)

        # Export content (schemas included automatically for relation resolution)
        export_data = exporter.export_content_types(
            CONTENT_TYPES,
            include_media=True,  # Include media files
            media_dir="./migration_media",  # Where to save media
        )

        print(f"✓ Exported {len(CONTENT_TYPES)} content types")

        # Optionally save to file
        exporter.save_to_file(export_data, "migration_backup.json")
        print("✓ Saved backup to migration_backup.json")

    # Step 2: Import to target
    print(f"\n📤 Importing to {TARGET_URL}...")
    with SyncClient(target_config) as target_client:
        importer = StrapiImporter(target_client)

        # Import with automatic relation resolution
        result = importer.import_data(
            export_data,
            media_dir="./migration_media",  # Upload media from here
        )

        print(f"✓ Imported {result.entities_imported} entities")
        print(f"✓ Uploaded {result.media_imported} media files")

    print("\n✅ Migration complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
