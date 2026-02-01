"""Example: Export/Import with Schema-Based Relation Resolution

This example demonstrates how to export and import Strapi content
with automatic relation resolution using cached content type schemas.
"""

from pydantic import SecretStr

from strapi_kit import StrapiConfig, StrapiExporter, StrapiImporter, SyncClient
from strapi_kit.models import ImportOptions

# Configure source and target Strapi instances
source_config = StrapiConfig(
    base_url="http://localhost:1337",
    api_token=SecretStr("source-token"),
)

target_config = StrapiConfig(
    base_url="http://localhost:1338",
    api_token=SecretStr("target-token"),
)


def export_with_schemas():
    """Export content types with schemas (always included for relation resolution)."""
    with SyncClient(source_config) as client:
        exporter = StrapiExporter(client)

        # Export content types (schemas automatically included)
        export_data = exporter.export_content_types(
            ["api::article.article", "api::author.author"],
            include_media=False,
        )

        # Verify schemas are included
        print(f"Exported {export_data.get_entity_count()} entities")
        print(f"Schemas included: {list(export_data.metadata.schemas.keys())}")

        # Save to file
        exporter.save_to_file(export_data, "export_with_schemas.json")
        print("Export saved to export_with_schemas.json")

        return export_data


def import_with_relation_resolution(export_data):
    """Import content with automatic relation resolution."""
    with SyncClient(target_config) as client:
        importer = StrapiImporter(client)

        # Import with relation resolution
        result = importer.import_data(
            export_data,
            options=ImportOptions(
                skip_relations=False,  # Enable relation import
                dry_run=False,
            ),
        )

        # Print results
        print("\nImport Results:")
        print(f"  Entities imported: {result.entities_imported}")
        print(f"  Entities skipped: {result.entities_skipped}")
        print(f"  Success: {result.success}")

        # Show ID mapping
        print("\nID Mapping:")
        for content_type, mapping in result.id_mapping.items():
            print(f"  {content_type}:")
            for old_id, new_id in mapping.items():
                print(f"    {old_id} -> {new_id}")

        # Show warnings
        if result.warnings:
            print("\nWarnings:")
            for warning in result.warnings:
                print(f"  - {warning}")

        return result


def main():
    """Run the export/import example."""
    print("=" * 60)
    print("Export/Import with Schema-Based Relation Resolution")
    print("=" * 60)

    # Step 1: Export with schemas
    print("\n1. Exporting content with schemas...")
    export_data = export_with_schemas()

    # Step 2: Import with relation resolution
    print("\n2. Importing content with relation resolution...")
    import_with_relation_resolution(export_data)

    print("\n" + "=" * 60)
    print("Example completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
