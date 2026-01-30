#!/usr/bin/env python3
"""Complete Strapi v5 Migration Example

This example demonstrates a full content migration from one Strapi v5 instance to another:
1. Export all content types with their entities
2. Download all media files
3. Export schemas for relation resolution
4. Import to target instance with automatic ID mapping
5. Upload media files and update references
6. Resolve and restore all relations

Usage:
    # Export from source
    python full_migration_v5.py export

    # Import to target
    python full_migration_v5.py import

    # Full migration (export + import)
    python full_migration_v5.py migrate
"""

import sys
from pathlib import Path

from pydantic import SecretStr

from py_strapi import StrapiConfig, StrapiExporter, StrapiImporter, SyncClient
from py_strapi.models import ImportOptions

# Configuration
SOURCE_CONFIG = StrapiConfig(
    base_url="http://localhost:1337",  # Source Strapi v5 instance
    api_token=SecretStr("your-source-api-token"),
    api_version="v5",  # Explicitly set v5
    timeout=120.0,  # Longer timeout for large exports
)

TARGET_CONFIG = StrapiConfig(
    base_url="http://localhost:1338",  # Target Strapi v5 instance
    api_token=SecretStr("your-target-api-token"),
    api_version="v5",
    timeout=120.0,
)

# Export configuration
EXPORT_DIR = Path("./strapi_migration")
EXPORT_FILE = EXPORT_DIR / "export_data.json"
MEDIA_DIR = EXPORT_DIR / "media"


def progress_callback(current: int, total: int, message: str) -> None:
    """Display progress during operations."""
    if total > 0:
        percentage = int((current / total) * 100)
        bar_length = 40
        filled = int(bar_length * current / total)
        bar = "█" * filled + "░" * (bar_length - filled)
        print(f"\r[{bar}] {percentage:3d}% | {message}", end="", flush=True)
    else:
        print(f"\r{message}", end="", flush=True)


def discover_content_types(client: SyncClient) -> list[str]:
    """Discover all available content types in Strapi.

    Returns list of content type UIDs (e.g., ['api::article.article', 'api::author.author'])
    """
    print("\n🔍 Discovering content types...")

    try:
        # Get all content types from Content-Type Builder API
        response = client.get("content-type-builder/content-types")
        content_types = response.get("data", [])

        # Filter for API content types (exclude system types)
        api_content_types = [
            ct["uid"]
            for ct in content_types
            if ct.get("uid", "").startswith("api::")
            and ct.get("kind") != "singleType"  # Optionally include single types
        ]

        print(f"   Found {len(api_content_types)} content types:")
        for ct in api_content_types:
            print(f"   - {ct}")

        return api_content_types

    except Exception as e:
        print(f"   ⚠️  Could not auto-discover content types: {e}")
        print("   💡 Tip: Manually specify content types if discovery fails")
        return []


def export_all_content() -> None:
    """Export all content from source Strapi instance."""
    print("=" * 80)
    print("📦 EXPORTING ALL CONTENT FROM SOURCE STRAPI V5 INSTANCE")
    print("=" * 80)

    # Create export directories
    EXPORT_DIR.mkdir(exist_ok=True)
    MEDIA_DIR.mkdir(exist_ok=True)

    with SyncClient(SOURCE_CONFIG) as client:
        print(f"\n✓ Connected to source: {SOURCE_CONFIG.base_url}")
        print(f"  API Version: {client.api_version}")

        # Discover all content types
        content_types = discover_content_types(client)

        if not content_types:
            print("\n⚠️  No content types found. Exiting.")
            return

        # Create exporter
        exporter = StrapiExporter(client)

        # Export all content types with media
        print(f"\n📥 Exporting {len(content_types)} content types...")
        export_data = exporter.export_content_types(
            content_types,
            include_media=True,
            media_dir=str(MEDIA_DIR),
            progress_callback=progress_callback,
        )

        # Save export data
        print(f"\n\n💾 Saving export data to {EXPORT_FILE}...")
        exporter.save_to_file(export_data, str(EXPORT_FILE))

        # Print summary
        total_entities = sum(len(ct.get("entities", [])) for ct in export_data["content_types"])
        total_media = len(export_data.get("media", []))

        print("\n" + "=" * 80)
        print("✅ EXPORT COMPLETE")
        print("=" * 80)
        print(f"Content types exported: {len(content_types)}")
        print(f"Total entities exported: {total_entities}")
        print(f"Media files downloaded: {total_media}")
        print(f"Export file: {EXPORT_FILE}")
        print(f"Media directory: {MEDIA_DIR}")
        print(f"Total export size: {EXPORT_FILE.stat().st_size / 1024 / 1024:.2f} MB")


def import_all_content() -> None:
    """Import all content to target Strapi instance."""
    print("=" * 80)
    print("📦 IMPORTING ALL CONTENT TO TARGET STRAPI V5 INSTANCE")
    print("=" * 80)

    # Check if export exists
    if not EXPORT_FILE.exists():
        print(f"\n❌ Export file not found: {EXPORT_FILE}")
        print("   Run 'python full_migration_v5.py export' first")
        return

    # Load export data
    print(f"\n📂 Loading export data from {EXPORT_FILE}...")
    export_data = StrapiExporter.load_from_file(str(EXPORT_FILE))

    total_entities = sum(len(ct.get("entities", [])) for ct in export_data["content_types"])
    total_media = len(export_data.get("media", []))
    print(f"   Content types: {len(export_data['content_types'])}")
    print(f"   Total entities: {total_entities}")
    print(f"   Media files: {total_media}")

    with SyncClient(TARGET_CONFIG) as client:
        print(f"\n✓ Connected to target: {TARGET_CONFIG.base_url}")
        print(f"  API Version: {client.api_version}")

        # Create importer
        importer = StrapiImporter(client)

        # Configure import options
        options = ImportOptions(
            dry_run=False,
            progress_callback=progress_callback,
        )

        # Import data
        print(f"\n📤 Importing {total_entities} entities...")
        result = importer.import_data(
            export_data,
            options=options,
            media_dir=str(MEDIA_DIR),
        )

        # Print detailed results
        print("\n\n" + "=" * 80)
        print("✅ IMPORT COMPLETE")
        print("=" * 80)
        print(f"Entities imported: {result.entities_imported}")
        print(f"Entities updated: {result.entities_updated}")
        print(f"Entities skipped: {result.entities_skipped}")
        print(f"Media files imported: {result.media_imported}")

        if result.errors:
            print(f"\n⚠️  Errors encountered: {len(result.errors)}")
            for error in result.errors[:5]:  # Show first 5 errors
                print(f"   - {error}")
            if len(result.errors) > 5:
                print(f"   ... and {len(result.errors) - 5} more errors")

        # Show ID mapping sample
        if result.id_mapping:
            print("\n📋 ID Mapping (sample):")
            for content_type, mappings in list(result.id_mapping.items())[:3]:
                print(f"   {content_type}:")
                for old_id, new_id in list(mappings.items())[:3]:
                    print(f"      {old_id} → {new_id}")


def migrate_all_content() -> None:
    """Perform complete migration: export from source and import to target."""
    print("=" * 80)
    print("🚀 FULL STRAPI V5 MIGRATION")
    print("=" * 80)
    print(f"Source: {SOURCE_CONFIG.base_url}")
    print(f"Target: {TARGET_CONFIG.base_url}")
    print()

    try:
        # Step 1: Export
        export_all_content()

        # Step 2: Import
        print("\n\n")
        import_all_content()

        print("\n" + "=" * 80)
        print("✅ MIGRATION COMPLETED SUCCESSFULLY")
        print("=" * 80)

    except Exception as e:
        print(f"\n\n❌ Migration failed: {e}")
        raise


def verify_migration() -> None:
    """Verify that migration was successful by comparing counts."""
    print("=" * 80)
    print("🔍 VERIFYING MIGRATION")
    print("=" * 80)

    with SyncClient(SOURCE_CONFIG) as source_client:
        print(f"\n📊 Source instance ({SOURCE_CONFIG.base_url}):")

        # Discover content types
        content_types = discover_content_types(source_client)

        source_counts: dict[str, int] = {}
        for ct in content_types:
            try:
                # Extract collection name from UID (e.g., "api::article.article" -> "articles")
                collection = ct.split("::")[-1].split(".")[0] + "s"
                response = source_client.get(collection, params={"pagination[limit]": 1})
                count = response.get("meta", {}).get("pagination", {}).get("total", 0)
                source_counts[ct] = count
                print(f"   {ct}: {count} entities")
            except Exception as e:
                print(f"   {ct}: Error getting count - {e}")

    with SyncClient(TARGET_CONFIG) as target_client:
        print(f"\n📊 Target instance ({TARGET_CONFIG.base_url}):")

        target_counts: dict[str, int] = {}
        for ct in content_types:
            try:
                collection = ct.split("::")[-1].split(".")[0] + "s"
                response = target_client.get(collection, params={"pagination[limit]": 1})
                count = response.get("meta", {}).get("pagination", {}).get("total", 0)
                target_counts[ct] = count
                print(f"   {ct}: {count} entities")
            except Exception as e:
                print(f"   {ct}: Error getting count - {e}")

    # Compare counts
    print("\n📈 Comparison:")
    all_match = True
    for ct in content_types:
        source_count = source_counts.get(ct, 0)
        target_count = target_counts.get(ct, 0)
        match = "✅" if source_count == target_count else "⚠️"
        print(f"   {match} {ct}: {source_count} → {target_count}")
        if source_count != target_count:
            all_match = False

    if all_match:
        print("\n✅ All content types match!")
    else:
        print("\n⚠️  Some content types have different counts")


def show_help() -> None:
    """Show usage help."""
    print(__doc__)


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        show_help()
        return

    command = sys.argv[1].lower()

    try:
        if command == "export":
            export_all_content()
        elif command == "import":
            import_all_content()
        elif command == "migrate":
            migrate_all_content()
        elif command == "verify":
            verify_migration()
        elif command in ["help", "-h", "--help"]:
            show_help()
        else:
            print(f"❌ Unknown command: {command}")
            print("\nAvailable commands:")
            print("  export   - Export all content from source instance")
            print("  import   - Import all content to target instance")
            print("  migrate  - Full migration (export + import)")
            print("  verify   - Verify migration by comparing counts")
            print("  help     - Show this help message")

    except KeyboardInterrupt:
        print("\n\n⚠️  Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
