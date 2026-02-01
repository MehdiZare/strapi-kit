"""Component and dynamic zone models for Strapi responses.

Models for handling components and dynamic zones which have special structure.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Component(BaseModel):
    """Strapi component.

    Components are reusable data structures that can be used across content types.
    They have a special '__component' field identifying their type.

    Attributes:
        id: Component instance ID
        document_id: Document ID (v5 only)
        component_type: Component type identifier (from __component field)
        Additional fields are allowed based on component schema.

    Examples:
        >>> component = Component(
        ...     id=1,
        ...     component_type="shared.seo",
        ...     title="SEO Title",
        ...     description="SEO Description"
        ... )
        >>> component.component_type
        'shared.seo'
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: int | None = Field(None, description="Component instance ID")
    document_id: str | None = Field(None, alias="documentId", description="Document ID (v5)")
    component_type: str = Field(..., alias="__component", description="Component type")


class DynamicZoneBlock(BaseModel):
    """Dynamic zone block.

    Dynamic zones are arrays of components of different types.
    Each block has a '__component' field identifying its type.

    Attributes:
        id: Block instance ID
        document_id: Document ID (v5 only)
        component_type: Block type identifier (from __component field)
        Additional fields are allowed based on block schema.

    Examples:
        >>> block = DynamicZoneBlock(
        ...     id=1,
        ...     component_type="content.rich-text",
        ...     body="<p>Rich text content</p>"
        ... )
        >>> block.component_type
        'content.rich-text'
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: int | None = Field(None, description="Block instance ID")
    document_id: str | None = Field(None, alias="documentId", description="Document ID (v5)")
    component_type: str = Field(..., alias="__component", description="Block type")
