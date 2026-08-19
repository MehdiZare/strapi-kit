"""Data models for strapi-kit.

Includes configuration models and request/response models for Strapi API interactions.
"""

from .blocks import (
    BlockNode,
    CodeNode,
    HeadingNode,
    ImageAsset,
    ImageNode,
    InlineNode,
    LinkNode,
    ListItemNode,
    ListNode,
    ParagraphNode,
    QuoteNode,
    TextNode,
)
from .bulk import BulkOperationFailure, BulkOperationResult
from .config import RetryConfig, StrapiConfig
from .content_type import ComponentListItem, ContentTypeListItem, ContentTypeOptions
from .content_type import ContentTypeInfo as CTBContentTypeInfo
from .content_type import ContentTypeSchema as CTBContentTypeSchema
from .enums import (
    DocumentAction,
    DocumentStatus,
    FilterOperator,
    HttpMethod,
    PublicationFilter,
    PublicationState,
    QueryParam,
    RelationWriteOp,
    SortDirection,
)
from .export_format import (
    ExportData,
    ExportedEntity,
    ExportedMediaFile,
    ExportFormat,
    ExportMetadata,
    RelationId,
)
from .import_options import (
    ConflictResolution,
    ImportOptions,
    ImportResult,
    UnresolvedRelation,
)
from .request.fields import FieldSelection
from .request.filters import FilterBuilder, FilterCondition, FilterGroup
from .request.media_write import media_write
from .request.pagination import OffsetPagination, PagePagination, Pagination
from .request.populate import Populate, PopulateField
from .request.query import StrapiQuery
from .request.relation_write import relation_write
from .request.sort import Sort, SortField
from .response.admin import AdminInformation
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
from .response.pagination import assert_pagination_echo
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
    "ExportFormat",
    "RelationId",
    "ImportOptions",
    "ImportResult",
    "UnresolvedRelation",
    "ConflictResolution",
    # Enums
    "FilterOperator",
    "SortDirection",
    "PublicationState",
    "DocumentStatus",
    "PublicationFilter",
    "DocumentAction",
    "QueryParam",
    "HttpMethod",
    "RelationWriteOp",
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
    # Request models - Relation / media writes (Strapi 5)
    "relation_write",
    "media_write",
    # Response models - Base
    "BaseStrapiResponse",
    "StrapiSingleResponse",
    "StrapiCollectionResponse",
    # Response models - Admin
    "AdminInformation",
    # Response models - Meta
    "PaginationMeta",
    "ResponseMeta",
    "assert_pagination_echo",
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
    # Content-Type Builder models
    "CTBContentTypeInfo",
    "CTBContentTypeSchema",
    "ContentTypeListItem",
    "ContentTypeOptions",
    "ComponentListItem",
    # Blocks JSON nodes
    "BlockNode",
    "InlineNode",
    "TextNode",
    "LinkNode",
    "ImageNode",
    "ImageAsset",
    "ParagraphNode",
    "HeadingNode",
    "QuoteNode",
    "CodeNode",
    "ListNode",
    "ListItemNode",
]
