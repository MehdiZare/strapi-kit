"""Media file models for Strapi file uploads.

Models for parsing media/file fields with multiple formats.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MediaFormat(BaseModel):
    """A specific format/size of a media file.

    Strapi generates multiple formats for images (thumbnail, small, medium, large).

    Attributes:
        name: Format name (e.g., "thumbnail", "small", "medium", "large")
        hash: File hash
        ext: File extension
        mime: MIME type
        width: Image width in pixels
        height: Image height in pixels
        size: File size in KB
        path: File path (if applicable)
        url: URL to access the file
    """

    model_config = ConfigDict(extra="allow")

    name: str = Field(..., description="Format name")
    hash: str = Field(..., description="File hash")
    ext: str = Field(..., description="File extension")
    mime: str = Field(..., description="MIME type")
    width: int | None = Field(None, description="Image width")
    height: int | None = Field(None, description="Image height")
    size: float = Field(..., description="File size in KB")
    path: str | None = Field(None, description="File path")
    url: str = Field(..., description="File URL")


class MediaFile(BaseModel):
    """Media file entity from Strapi.

    Represents uploaded files with multiple format variations.

    Attributes:
        id: Numeric file ID
        document_id: Document ID (v5 only)
        name: Original filename
        alternative_text: Alt text for accessibility
        caption: Image caption
        width: Original width
        height: Original height
        formats: Available formats (thumbnail, small, medium, large)
        hash: File hash
        ext: File extension
        mime: MIME type
        size: File size in KB
        url: URL to original file
        preview_url: Preview URL
        provider: Storage provider (local, s3, etc.)
        provider_metadata: Provider-specific metadata
        created_at: Upload timestamp
        updated_at: Last update timestamp
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: int = Field(..., description="Numeric file ID")
    document_id: str | None = Field(None, alias="documentId", description="Document ID (v5)")
    name: str = Field(..., description="Original filename")
    alternative_text: str | None = Field(None, alias="alternativeText")
    caption: str | None = Field(None, description="Image caption")
    width: int | None = Field(None, description="Image width")
    height: int | None = Field(None, description="Image height")
    formats: dict[str, MediaFormat] | None = Field(None, description="Available formats")
    hash: str = Field(..., description="File hash")
    ext: str = Field(..., description="File extension")
    mime: str = Field(..., description="MIME type")
    size: float = Field(..., description="File size in KB")
    url: str = Field(..., description="File URL")
    preview_url: str | None = Field(None, alias="previewUrl")
    provider: str = Field(..., description="Storage provider")
    provider_metadata: dict[str, Any] | None = Field(
        None, alias="providerMetadata", description="Provider metadata"
    )
    created_at: datetime | None = Field(None, alias="createdAt")
    updated_at: datetime | None = Field(None, alias="updatedAt")
