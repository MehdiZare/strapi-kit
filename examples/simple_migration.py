#!/usr/bin/env python3
"""Simple Strapi Migration Example

A simplified example for migrating content between two Strapi instances.
Perfect for getting started quickly.

Usage:
    1. Update SOURCE_URL, SOURCE_TOKEN, TARGET_URL, TARGET_TOKEN below
    2. Update CONTENT_TYPES with your content types
    3. Run: python simple_migration.py

Environment Variables (optional):
    SOURCE_STRAPI_URL: Override SOURCE_URL
    SOURCE_STRAPI_TOKEN: Override SOURCE_TOKEN
    TARGET_STRAPI_URL: Override TARGET_URL
    TARGET_STRAPI_TOKEN: Override TARGET_TOKEN
"""

import os
from datetime import datetime

from pydantic import SecretStr

from strapi_kit import StrapiConfig, StrapiExporter, StrapiImporter, SyncClient
from strapi_kit.exceptions import StrapiError
from strapi_kit.models import StrapiQuery

# ============================================================================
# CONFIGURATION - Update these values or use environment variables
# ============================================================================

SOURCE_URL = os.getenv("SOURCE_STRAPI_URL", "http://localhost:1337")
SOURCE_TOKEN = os.getenv("SOURCE_STRAPI_TOKEN", "your-source-api-token-here")

TARGET_URL = os.getenv("TARGET_STRAPI_URL", "http://localhost:1338")
TARGET_TOKEN = os.getenv("TARGET_STRAPI_TOKEN", "your-target-api-token-here")

# List your content types here
CONTENT_TYPES = [
    "api::article.article",
    "api::author.author",
    "api::category.category",
]

# ============================================================================


def validate_config() -> None:
    """Validate configuration before migration.

    Raises:
        ValueError: If required configuration is missing or invalid.
    """
    if not SOURCE_TOKEN or SOURCE_TOKEN == "your-source-api-token-here":
        raise ValueError(
            "SOURCE_TOKEN not configured. "
            "Set SOURCE_STRAPI_TOKEN environment variable or update SOURCE_TOKEN in the script."
        )
    if not TARGET_TOKEN or TARGET_TOKEN == "your-target-api-token-here":
        raise ValueError(
            "TARGET_TOKEN not configured. "
            "Set TARGET_STRAPI_TOKEN environment variable or update TARGET_TOKEN in the script."
        )
    if not SOURCE_URL:
        raise ValueError("SOURCE_URL cannot be empty.")
    if not TARGET_URL:
        raise ValueError("TARGET_URL cannot be empty.")


def _uid_to_endpoint(uid: str) -> str:
    """Convert content type UID to API endpoint.

    Args:
        uid: Content type UID (e.g., "api::article.article")

    Returns:
        API endpoint (e.g., "articles")
    """
    parts = uid.split("::")
    if len(parts) == 2:
        name = parts[1].split(".")[0]
        # Handle common irregular plurals
        if name.endswith("y") and not name.endswith(("ay", "ey", "oy", "uy")):
            return name[:-1] + "ies"  # category -> categories
        if name.endswith(("s", "x", "z", "ch", "sh")):
            return name + "es"  # class -> classes
        if not name.endswith("s"):
            return name + "s"
        return name
    return uid


def verify_connection(
    client: SyncClient, name: str, content_types: list[str] | None = None
) -> bool:
    """Verify connection to a Strapi instance.

    Args:
        client: The Strapi client to test.
        name: Display name for the instance (e.g., "source", "target").
        content_types: List of content type UIDs to derive test endpoint from.
            If empty or None, skips verification and returns True.

    Returns:
        True if connection is successful, False otherwise.
    """
    # Skip verification if no content types configured
    if not content_types:
        print(f"  Skipping connection verification for {name} (no content types configured)")
        return True

    # Derive endpoint from first content type
    endpoint = _uid_to_endpoint(content_types[0])

    try:
        # Try to fetch a single item to verify connection
        client.get_many(endpoint, query=StrapiQuery().paginate(1, 1))
        print(f"  Connection to {name} verified")
        return True
    except StrapiError as e:
        print(f"  Failed to connect to {name}: {e}")
        return False
    except Exception as e:
        print(f"  Unexpected error connecting to {name}: {e}")
        return False


def main() -> None:
    """Perform a simple migration from source to target."""
    print("Starting Strapi Migration")
    print("=" * 60)

    # Validate configuration
    try:
        validate_config()
    except ValueError as e:
        print(f"Configuration error: {e}")
        return

    # Generate unique run ID for file paths
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    media_dir = f"./migration_media_{run_id}"
    backup_file = f"migration_backup_{run_id}.json"

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
    print(f"\nExporting from {SOURCE_URL}...")
    try:
        with SyncClient(source_config) as source_client:
            # Verify connection first
            if not verify_connection(source_client, "source", CONTENT_TYPES):
                print("Aborting migration due to connection failure.")
                return

            exporter = StrapiExporter(source_client)

            # Export content (schemas included automatically for relation resolution)
            export_data = exporter.export_content_types(
                CONTENT_TYPES,
                include_media=True,  # Include media files
                media_dir=media_dir,  # Where to save media
            )

            print(f"  Exported {len(CONTENT_TYPES)} content types")

            # Optionally save to file
            exporter.save_to_file(export_data, backup_file)
            print(f"  Saved backup to {backup_file}")
    except StrapiError as e:
        print(f"Export failed: {e}")
        return
    except Exception as e:
        print(f"Unexpected error during export: {e}")
        return

    # Step 2: Import to target
    print(f"\nImporting to {TARGET_URL}...")
    try:
        with SyncClient(target_config) as target_client:
            # Verify connection first
            if not verify_connection(target_client, "target", CONTENT_TYPES):
                print("Aborting migration due to connection failure.")
                print(f"Export data saved to {backup_file} - you can retry import later.")
                return

            importer = StrapiImporter(target_client)

            # Import with automatic relation resolution
            result = importer.import_data(
                export_data,
                media_dir=media_dir,  # Upload media from here
            )

            print(f"  Imported {result.entities_imported} entities")
            print(f"  Uploaded {result.media_imported} media files")
    except StrapiError as e:
        print(f"Import failed: {e}")
        print(f"Export data saved to {backup_file} - you can retry import later.")
        return
    except Exception as e:
        print(f"Unexpected error during import: {e}")
        print(f"Export data saved to {backup_file} - you can retry import later.")
        return

    print("\nMigration complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
