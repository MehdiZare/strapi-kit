"""Models for export file format.

Defines the structure of exported Strapi data for portability
and version compatibility.
"""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ExportMetadata(BaseModel):
    """Metadata about the export.

    Attributes:
        version: Export format version (semver)
        strapi_version: Strapi API version (v4 or v5)
        exported_at: ISO timestamp of export
        source_url: Base URL of source Strapi instance
        content_types: List of exported content type UIDs
        total_entities: Total number of entities exported
        total_media: Total number of media files exported
    """

    version: str = Field(
        default="1.0.0",
        description="Export format version (semver)",
    )
    strapi_version: str = Field(
        ...,
        description="Strapi API version (v4 or v5)",
    )
    exported_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="ISO timestamp of export",
    )
    source_url: str = Field(
        ...,
        description="Base URL of source Strapi instance",
    )
    content_types: list[str] = Field(
        default_factory=list,
        description="List of exported content type UIDs",
    )
    total_entities: int = Field(
        default=0,
        description="Total number of entities exported",
    )
    total_media: int = Field(
        default=0,
        description="Total number of media files exported",
    )


class ExportedEntity(BaseModel):
    """A single exported entity with metadata.

    Attributes:
        id: Original entity ID
        document_id: Document ID (v5 only)
        content_type: Content type UID
        data: Entity data (attributes)
        relations: Relation field mapping
    """

    id: int = Field(..., description="Original entity ID")
    document_id: str | None = Field(None, description="Document ID (v5 only)")
    content_type: str = Field(..., description="Content type UID")
    data: dict[str, Any] = Field(..., description="Entity data (attributes)")
    relations: dict[str, list[int | str]] = Field(
        default_factory=dict,
        description="Relation field mapping (field -> [ids])",
    )


class ExportedMediaFile(BaseModel):
    """A media file reference in the export.

    Attributes:
        id: Original media file ID
        url: Original URL (may be relative or absolute)
        name: File name
        mime: MIME type
        size: File size in bytes
        hash: File hash (for deduplication)
        local_path: Path in export archive (relative)
    """

    id: int = Field(..., description="Original media file ID")
    url: str = Field(..., description="Original URL")
    name: str = Field(..., description="File name")
    mime: str = Field(..., description="MIME type")
    size: int = Field(..., description="File size in bytes")
    hash: str = Field(..., description="File hash")
    local_path: str = Field(..., description="Path in export archive (relative)")


class ExportData(BaseModel):
    """Complete export data structure.

    This is the root model for exported data, containing metadata,
    entities, and media references.

    Attributes:
        metadata: Export metadata
        entities: Exported entities grouped by content type
        media: Media file references
    """

    metadata: ExportMetadata = Field(..., description="Export metadata")
    entities: dict[str, list[ExportedEntity]] = Field(
        default_factory=dict,
        description="Entities grouped by content type UID",
    )
    media: list[ExportedMediaFile] = Field(
        default_factory=list,
        description="Media file references",
    )

    def get_entity_count(self) -> int:
        """Get total number of exported entities.

        Returns:
            Total entity count across all content types
        """
        return sum(len(entities) for entities in self.entities.values())

    def get_media_count(self) -> int:
        """Get total number of exported media files.

        Returns:
            Total media file count
        """
        return len(self.media)
