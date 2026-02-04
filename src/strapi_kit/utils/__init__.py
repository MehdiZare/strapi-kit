"""Utility modules for strapi-kit.

This package contains helper utilities including:
- Rate limiting
- UID handling
- SEO detection
"""

from strapi_kit.utils.rate_limiter import AsyncTokenBucketRateLimiter, TokenBucketRateLimiter
from strapi_kit.utils.schema import extract_info_from_schema
from strapi_kit.utils.seo import SEOConfiguration, detect_seo_configuration
from strapi_kit.utils.uid import (
    api_id_to_singular,
    extract_model_name,
    is_api_content_type,
    uid_to_admin_url,
    uid_to_api_id,
    uid_to_endpoint,
)

__all__ = [
    # Rate limiting
    "TokenBucketRateLimiter",
    "AsyncTokenBucketRateLimiter",
    # UID utilities
    "uid_to_endpoint",
    "uid_to_api_id",
    "api_id_to_singular",
    "uid_to_admin_url",
    "extract_model_name",
    "is_api_content_type",
    # SEO utilities
    "detect_seo_configuration",
    "SEOConfiguration",
    # Schema utilities
    "extract_info_from_schema",
]
