"""Base response models for Strapi API.

Provides generic response containers for single and collection responses.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from py_strapi.models.response.meta import ResponseMeta

# Generic type for entity data
T = TypeVar("T")


class BaseStrapiResponse(BaseModel):
    """Base class for all Strapi responses.

    Attributes:
        meta: Response metadata (pagination, locales, etc.)
    """

    model_config = ConfigDict(extra="allow")

    meta: ResponseMeta | None = Field(None, description="Response metadata")


class StrapiSingleResponse(BaseStrapiResponse, Generic[T]):
    """Response for a single entity.

    Generic response container for GET /api/articles/1 endpoints.

    Attributes:
        data: The entity data (or None if not found)
        meta: Response metadata

    Examples:
        >>> from pydantic import BaseModel
        >>> class Article(BaseModel):
        ...     id: int
        ...     title: str
        >>> response = StrapiSingleResponse[Article](
        ...     data=Article(id=1, title="Test")
        ... )
        >>> response.data.title
        'Test'
    """

    data: T | None = Field(None, description="Single entity data")


class StrapiCollectionResponse(BaseStrapiResponse, Generic[T]):
    """Response for a collection of entities.

    Generic response container for GET /api/articles endpoints.

    Attributes:
        data: List of entities
        meta: Response metadata (includes pagination)

    Examples:
        >>> from pydantic import BaseModel
        >>> class Article(BaseModel):
        ...     id: int
        ...     title: str
        >>> response = StrapiCollectionResponse[Article](
        ...     data=[Article(id=1, title="Test")]
        ... )
        >>> len(response.data)
        1
    """

    data: list[T] = Field(default_factory=list, description="Collection of entities")
