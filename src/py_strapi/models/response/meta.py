"""Metadata models for Strapi API responses.

Contains pagination metadata and response metadata structures.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PaginationMeta(BaseModel):
    """Pagination metadata from Strapi responses.

    Attributes:
        page: Current page number (1-indexed)
        page_size: Number of items per page
        page_count: Total number of pages
        total: Total number of items across all pages
    """

    model_config = ConfigDict(populate_by_name=True)

    page: int | None = Field(None, description="Current page number")
    page_size: int | None = Field(None, alias="pageSize", description="Items per page")
    page_count: int | None = Field(None, alias="pageCount", description="Total pages")
    total: int | None = Field(None, description="Total items")


class ResponseMeta(BaseModel):
    """Response metadata from Strapi.

    Contains pagination information and other metadata like available locales.

    Attributes:
        pagination: Pagination metadata (if pagination was used)
        available_locales: Available locale codes (if i18n is enabled)
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    pagination: PaginationMeta | None = Field(None, description="Pagination metadata")
    available_locales: list[str] | None = Field(
        None, alias="availableLocales", description="Available locales"
    )
