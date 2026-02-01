"""Strapi v4 response models.

Models for parsing Strapi v4 API responses with nested attributes structure.

V4 Structure:
{
  "data": {
    "id": 1,
    "attributes": {
      "title": "Hello",
      "createdAt": "2024-01-01T00:00:00.000Z",
      "updatedAt": "2024-01-01T00:00:00.000Z",
      "publishedAt": "2024-01-01T00:00:00.000Z",
      "locale": "en",
      ...custom fields
    }
  }
}
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from strapi_kit.models.response.base import StrapiCollectionResponse, StrapiSingleResponse


class V4Attributes(BaseModel):
    """Attributes container for v4 entities.

    In v4, all entity data is nested under the 'attributes' key.
    This includes timestamps, locale, and all custom fields.

    Attributes:
        created_at: Creation timestamp
        updated_at: Last update timestamp
        published_at: Publication timestamp (if draft & publish enabled)
        locale: Locale code (if i18n enabled)
        Additional fields are allowed and will be preserved.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    created_at: datetime | None = Field(None, alias="createdAt")
    updated_at: datetime | None = Field(None, alias="updatedAt")
    published_at: datetime | None = Field(None, alias="publishedAt")
    locale: str | None = Field(None, description="Locale code")


class V4Entity(BaseModel):
    """Strapi v4 entity structure.

    V4 entities have a numeric ID and nested attributes.

    Attributes:
        id: Numeric entity ID
        attributes: All entity data (timestamps + custom fields)
    """

    model_config = ConfigDict(extra="allow")

    id: int = Field(..., description="Numeric entity ID")
    attributes: V4Attributes = Field(..., description="Entity attributes")


# Type aliases for v4 responses
V4SingleResponse = StrapiSingleResponse[V4Entity]
V4CollectionResponse = StrapiCollectionResponse[V4Entity]
