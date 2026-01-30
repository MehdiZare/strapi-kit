"""Example: Export and import Strapi data with media files.

This example demonstrates the complete export/import flow including:
- Exporting content types with all entities
- Downloading media files during export
- Saving export data to JSON
- Loading export data from JSON
- Uploading media files during import
- Creating entities with updated media references
- Importing relations

Usage:
    # Export from source instance
    python export_import_with_media.py export

    # Import to target instance
    python export_import_with_media.py import
"""

import sys
from pathlib import Path

from py_strapi import StrapiExporter, StrapiImporter, SyncClient
from py_strapi.models import ImportOptions, StrapiConfig


def progress_callback(current: int, total: int, message: str) -> None:
    """Display progress during export/import."""
    percentage = int((current / total) * 100) if total > 0 else 0
    print(f"[{percentage:3d}%] {message}")


def export_data() -> None:
    """Export data from source Strapi instance."""
    print("=" * 60)
    print("EXPORTING DATA FROM SOURCE INSTANCE")
    print("=" * 60)

    # Configure source instance
    source_config = StrapiConfig(
        base_url="http://localhost:1337", api_token="your-source-api-token-here"
    )

    # Create export directory
    export_dir = Path("export")
    media_dir = export_dir / "media"
    export_dir.mkdir(exist_ok=True)
    media_dir.mkdir(exist_ok=True)

    # Export content types
    with SyncClient(source_config) as client:
        exporter = StrapiExporter(client)

        print("\nExporting content types...")
        export_data = exporter.export_content_types(
            content_types=[
                "api::article.article",
                "api::author.author",
                "api::category.category",
            ],
            include_media=True,
            media_dir=media_dir,
            progress_callback=progress_callback,
        )

        # Save to file
        export_file = export_dir / "data.json"
        StrapiExporter.save_to_file(export_data, export_file)

        # Display summary
        print("\n" + "=" * 60)
        print("EXPORT SUMMARY")
        print("=" * 60)
        print(f"Total entities: {export_data.get_entity_count()}")
        print(f"Total media files: {len(export_data.media)}")
        print(f"Export saved to: {export_file}")
        print(f"Media files in: {media_dir}")

        # Show breakdown by content type
        print("\nEntities by content type:")
        for content_type, entities in export_data.entities.items():
            print(f"  - {content_type}: {len(entities)} entities")


def import_data() -> None:
    """Import data to target Strapi instance."""
    print("=" * 60)
    print("IMPORTING DATA TO TARGET INSTANCE")
    print("=" * 60)

    # Configure target instance
    target_config = StrapiConfig(
        base_url="http://localhost:1338",  # Different port/host for target
        api_token="your-target-api-token-here",
    )

    # Load export data
    export_dir = Path("export")
    export_file = export_dir / "data.json"
    media_dir = export_dir / "media"

    if not export_file.exists():
        print(f"\nError: Export file not found: {export_file}")
        print("Please run 'export' first.")
        return

    print(f"\nLoading export from: {export_file}")
    export_data = StrapiExporter.load_from_file(export_file)

    print(f"Found {export_data.get_entity_count()} entities")
    print(f"Found {len(export_data.media)} media files")

    # Import to target instance
    with SyncClient(target_config) as client:
        importer = StrapiImporter(client)

        # Configure import options
        options = ImportOptions(
            import_media=True,
            skip_relations=False,
            dry_run=False,  # Set to True to validate without creating
            progress_callback=progress_callback,
        )

        print("\nImporting data...")
        result = importer.import_data(
            export_data,
            options=options,
            media_dir=media_dir,
        )

        # Display summary
        print("\n" + "=" * 60)
        print("IMPORT SUMMARY")
        print("=" * 60)
        print(f"Entities imported: {result.entities_imported}")
        print(f"Entities failed: {result.entities_failed}")
        print(f"Media imported: {result.media_imported}")
        print(f"Media skipped: {result.media_skipped}")

        # Show errors if any
        if result.errors:
            print("\nErrors:")
            for error in result.errors[:10]:  # Show first 10
                print(f"  - {error}")
            if len(result.errors) > 10:
                print(f"  ... and {len(result.errors) - 10} more")

        # Show warnings if any
        if result.warnings:
            print("\nWarnings:")
            for warning in result.warnings[:10]:  # Show first 10
                print(f"  - {warning}")
            if len(result.warnings) > 10:
                print(f"  ... and {len(result.warnings) - 10} more")

        # Final status
        if result.success:
            print("\n✓ Import completed successfully!")
        else:
            print(f"\n✗ Import completed with {result.entities_failed} failures")


def dry_run_import() -> None:
    """Validate import without creating entities (dry run)."""
    print("=" * 60)
    print("DRY RUN - VALIDATING IMPORT")
    print("=" * 60)

    target_config = StrapiConfig(
        base_url="http://localhost:1338", api_token="your-target-api-token-here"
    )

    export_file = Path("export/data.json")
    if not export_file.exists():
        print(f"\nError: Export file not found: {export_file}")
        return

    export_data = StrapiExporter.load_from_file(export_file)

    with SyncClient(target_config) as client:
        importer = StrapiImporter(client)

        # Dry run - validate only
        options = ImportOptions(
            dry_run=True,  # Don't actually create anything
            progress_callback=progress_callback,
        )

        print("\nValidating import (dry run)...")
        result = importer.import_data(export_data, options=options)

        print("\n" + "=" * 60)
        print("VALIDATION SUMMARY")
        print("=" * 60)
        print(f"Would import: {result.entities_imported} entities")
        print(f"Validation errors: {len(result.errors)}")
        print(f"Validation warnings: {len(result.warnings)}")

        if result.errors:
            print("\nValidation errors found:")
            for error in result.errors:
                print(f"  - {error}")
        else:
            print("\n✓ Validation passed - ready to import!")


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nCommands:")
        print("  export     - Export data from source instance")
        print("  import     - Import data to target instance")
        print("  validate   - Dry run validation (no changes)")
        return

    command = sys.argv[1].lower()

    if command == "export":
        export_data()
    elif command == "import":
        import_data()
    elif command == "validate":
        dry_run_import()
    else:
        print(f"Unknown command: {command}")
        print("Use: export, import, or validate")


if __name__ == "__main__":
    main()
