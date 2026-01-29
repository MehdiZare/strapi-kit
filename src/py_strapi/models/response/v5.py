"""Strapi v5 response models.

Models for parsing Strapi v5 API responses with flattened structure.

V5 Structure:
{
  "data": {
    "id": 1,
    "documentId": "abc123",
    "title": "Hello",
    "createdAt": "2024-01-01T00:00:00.000Z",
    "updatedAt": "2024-01-01T00:00:00.000Z",
    "publishedAt": "2024-01-01T00:00:00.000Z",
    "locale": "en",
    ...custom fields
  }
}
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from py_strapi.models.response.base import StrapiCollectionResponse, StrapiSingleResponse


class V5Entity(BaseModel):
    """Strapi v5 entity structure.

    V5 entities have a flattened structure with both numeric ID and document ID.
    All fields (timestamps, locale, custom) are at the same level.

    Attributes:
        id: Numeric entity ID (for backward compatibility)
        document_id: String document ID (new in v5, unique identifier)
        created_at: Creation timestamp
        updated_at: Last update timestamp
        published_at: Publication timestamp (if draft & publish enabled)
        locale: Locale code (if i18n enabled)
        Additional fields are allowed and will be preserved.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: int = Field(..., description="Numeric entity ID")
    document_id: str = Field(..., alias="documentId", description="Document ID (v5)")
    created_at: datetime | None = Field(None, alias="createdAt")
    updated_at: datetime | None = Field(None, alias="updatedAt")
    published_at: datetime | None = Field(None, alias="publishedAt")
    locale: str | None = Field(None, description="Locale code")


# Type aliases for v5 responses
V5SingleResponse = StrapiSingleResponse[V5Entity]
V5CollectionResponse = StrapiCollectionResponse[V5Entity]
