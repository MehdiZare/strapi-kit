"""Data models for py-strapi.

Includes configuration models and request/response models for Strapi API interactions.
"""

from .bulk import BulkOperationFailure, BulkOperationResult
from .config import RetryConfig, StrapiConfig
from .enums import FilterOperator, PublicationState, SortDirection
from .export_format import ExportData, ExportedEntity, ExportedMediaFile, ExportMetadata
from .import_options import ConflictResolution, ImportOptions, ImportResult
from .request.fields import FieldSelection
from .request.filters import FilterBuilder, FilterCondition, FilterGroup
from .request.pagination import OffsetPagination, PagePagination, Pagination
from .request.populate import Populate, PopulateField
from .request.query import StrapiQuery
from .request.sort import Sort, SortField
from .response.base import (
    BaseStrapiResponse,
    StrapiCollectionResponse,
    StrapiSingleResponse,
)
from .response.component import Component, DynamicZoneBlock
from .response.media import MediaFile, MediaFormat
from .response.meta import PaginationMeta, ResponseMeta
from .response.normalized import (
    NormalizedCollectionResponse,
    NormalizedEntity,
    NormalizedSingleResponse,
)
from .response.relation import RelationData
from .response.v4 import V4Attributes, V4CollectionResponse, V4Entity, V4SingleResponse
from .response.v5 import V5CollectionResponse, V5Entity, V5SingleResponse
from .schema import ContentTypeSchema, FieldSchema, FieldType, RelationType

__all__ = [
    # Configuration
    "StrapiConfig",
    "RetryConfig",
    # Bulk Operations
    "BulkOperationResult",
    "BulkOperationFailure",
    # Export/Import
    "ExportData",
    "ExportMetadata",
    "ExportedEntity",
    "ExportedMediaFile",
    "ImportOptions",
    "ImportResult",
    "ConflictResolution",
    # Enums
    "FilterOperator",
    "SortDirection",
    "PublicationState",
    # Request models - Filters
    "FilterBuilder",
    "FilterCondition",
    "FilterGroup",
    # Request models - Sort
    "Sort",
    "SortField",
    # Request models - Pagination
    "PagePagination",
    "OffsetPagination",
    "Pagination",
    # Request models - Fields
    "FieldSelection",
    # Request models - Populate
    "Populate",
    "PopulateField",
    # Request models - Query (Main API)
    "StrapiQuery",
    # Response models - Base
    "BaseStrapiResponse",
    "StrapiSingleResponse",
    "StrapiCollectionResponse",
    # Response models - Meta
    "PaginationMeta",
    "ResponseMeta",
    # Response models - V4
    "V4Attributes",
    "V4Entity",
    "V4SingleResponse",
    "V4CollectionResponse",
    # Response models - V5
    "V5Entity",
    "V5SingleResponse",
    "V5CollectionResponse",
    # Response models - Normalized
    "NormalizedEntity",
    "NormalizedSingleResponse",
    "NormalizedCollectionResponse",
    # Response models - Media
    "MediaFile",
    "MediaFormat",
    # Response models - Relations & Components
    "RelationData",
    "Component",
    "DynamicZoneBlock",
    # Schema models
    "ContentTypeSchema",
    "FieldSchema",
    "FieldType",
    "RelationType",
]
