"""Relation data models for Strapi responses.

Models for handling relation fields which are wrapped in a 'data' key.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# Generic type for relation data
T = TypeVar("T")


class RelationData(BaseModel, Generic[T]):
    """Wrapper for relation fields.

    In Strapi, populated relations are wrapped in a 'data' key:
    - Single relation: {"data": {...}}
    - Multiple relations: {"data": [{...}, {...}]}

    Attributes:
        data: The actual relation data (entity or list of entities)

    Examples:
        >>> # Single relation
        >>> from strapi_kit.models.response.v5 import V5Entity
        >>> relation = RelationData[V5Entity](
        ...     data=V5Entity(id=1, documentId="abc", title="Related")
        ... )
        >>> relation.data.title
        'Related'

        >>> # Multiple relations
        >>> relation = RelationData[list[V5Entity]](
        ...     data=[
        ...         V5Entity(id=1, documentId="abc", title="First"),
        ...         V5Entity(id=2, documentId="def", title="Second")
        ...     ]
        ... )
        >>> len(relation.data)
        2
    """

    model_config = ConfigDict(extra="allow")

    data: T | None = Field(None, description="Relation data")
