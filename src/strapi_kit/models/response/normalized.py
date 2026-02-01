"""Normalized response models providing version-agnostic interface.

The normalization layer abstracts the differences between Strapi v4 and v5,
providing a consistent interface for working with entities regardless of version.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from strapi_kit.models.response.base import StrapiCollectionResponse, StrapiSingleResponse
from strapi_kit.models.response.v4 import V4Entity
from strapi_kit.models.response.v5 import V5Entity


class NormalizedEntity(BaseModel):
    """Version-agnostic entity representation.

    Provides a consistent interface abstracting v4/v5 differences:
    - V4: nested attributes → flattened in NormalizedEntity
    - V5: already flat → preserved in NormalizedEntity
    - Document ID: v5 only, None for v4
    - Timestamps: extracted to top level
    - Custom fields: grouped in 'attributes' dict

    Attributes:
        id: Numeric entity ID (present in both v4 and v5)
        document_id: String document ID (v5 only, None for v4)
        created_at: Creation timestamp
        updated_at: Last update timestamp
        published_at: Publication timestamp
        locale: Locale code
        attributes: All custom fields (non-timestamp, non-system fields)

    Examples:
        >>> # From v4
        >>> v4_entity = V4Entity(
        ...     id=1,
        ...     attributes=V4Attributes(
        ...         createdAt=datetime.now(),
        ...         title="Test",
        ...         content="Body"
        ...     )
        ... )
        >>> normalized = NormalizedEntity.from_v4(v4_entity)
        >>> normalized.attributes["title"]
        'Test'
        >>> normalized.document_id  # None for v4
        None

        >>> # From v5
        >>> v5_entity = V5Entity(
        ...     id=1,
        ...     documentId="abc123",
        ...     createdAt=datetime.now(),
        ...     title="Test",
        ...     content="Body"
        ... )
        >>> normalized = NormalizedEntity.from_v5(v5_entity)
        >>> normalized.document_id
        'abc123'
        >>> normalized.attributes["title"]
        'Test'
    """

    id: int = Field(..., description="Numeric entity ID")
    document_id: str | None = Field(None, description="Document ID (v5 only)")
    created_at: datetime | None = Field(None, description="Creation timestamp")
    updated_at: datetime | None = Field(None, description="Last update timestamp")
    published_at: datetime | None = Field(None, description="Publication timestamp")
    locale: str | None = Field(None, description="Locale code")
    attributes: dict[str, Any] = Field(default_factory=dict, description="All custom entity fields")

    @classmethod
    def from_v4(cls, entity: V4Entity) -> NormalizedEntity:
        """Create normalized entity from v4 entity.

        Extracts attributes from the nested 'attributes' object and
        promotes timestamps to top level.

        Args:
            entity: V4 entity to normalize

        Returns:
            Normalized entity with flattened structure

        Examples:
            >>> v4 = V4Entity(
            ...     id=1,
            ...     attributes=V4Attributes(title="Test", content="Body")
            ... )
            >>> normalized = NormalizedEntity.from_v4(v4)
            >>> normalized.id
            1
        """
        # Get all attributes as dict
        attrs_dict = entity.attributes.model_dump(by_alias=False, exclude_none=False)

        # Extract system fields
        created_at = attrs_dict.pop("created_at", None)
        updated_at = attrs_dict.pop("updated_at", None)
        published_at = attrs_dict.pop("published_at", None)
        locale = attrs_dict.pop("locale", None)

        # Remaining fields are custom attributes
        return cls(
            id=entity.id,
            document_id=None,  # v4 doesn't have document_id
            created_at=created_at,
            updated_at=updated_at,
            published_at=published_at,
            locale=locale,
            attributes=attrs_dict,
        )

    @classmethod
    def from_v5(cls, entity: V5Entity) -> NormalizedEntity:
        """Create normalized entity from v5 entity.

        Extracts timestamps and system fields, grouping remaining fields
        as custom attributes.

        Args:
            entity: V5 entity to normalize

        Returns:
            Normalized entity

        Examples:
            >>> v5 = V5Entity(
            ...     id=1,
            ...     documentId="abc123",
            ...     title="Test",
            ...     content="Body"
            ... )
            >>> normalized = NormalizedEntity.from_v5(v5)
            >>> normalized.document_id
            'abc123'
        """
        # Get all fields as dict
        entity_dict = entity.model_dump(by_alias=False, exclude_none=False)

        # Extract system fields
        entity_id = entity_dict.pop("id")
        document_id = entity_dict.pop("document_id")
        created_at = entity_dict.pop("created_at", None)
        updated_at = entity_dict.pop("updated_at", None)
        published_at = entity_dict.pop("published_at", None)
        locale = entity_dict.pop("locale", None)

        # Remaining fields are custom attributes
        return cls(
            id=entity_id,
            document_id=document_id,
            created_at=created_at,
            updated_at=updated_at,
            published_at=published_at,
            locale=locale,
            attributes=entity_dict,
        )


# Type aliases for normalized responses
NormalizedSingleResponse = StrapiSingleResponse[NormalizedEntity]
NormalizedCollectionResponse = StrapiCollectionResponse[NormalizedEntity]
