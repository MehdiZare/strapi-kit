"""Response parser with automatic Strapi version detection.

This module provides automatic detection and normalization of Strapi v4 and v5
API responses into a consistent format.
"""

import logging
from typing import Any, Literal

from ..models.response.normalized import (
    NormalizedCollectionResponse,
    NormalizedEntity,
    NormalizedSingleResponse,
)
from ..models.response.v4 import V4CollectionResponse, V4SingleResponse
from ..models.response.v5 import V5CollectionResponse, V5SingleResponse

logger = logging.getLogger(__name__)


class VersionDetectingParser:
    """Response parser with automatic v4/v5 version detection.

    This parser automatically detects whether responses are from Strapi v4
    or v5 based on their structure, then normalizes them to a consistent format.

    Example:
        ```python
        parser = VersionDetectingParser()
        normalized = parser.parse_single(raw_response)
        print(normalized.data.id)
        ```
    """

    def __init__(self, default_version: Literal["v4", "v5"] | None = None) -> None:
        """Initialize the parser.

        Args:
            default_version: Optional version to use if detection fails
        """
        self._detected_version: Literal["v4", "v5"] | None = default_version

    @property
    def detected_version(self) -> Literal["v4", "v5"] | None:
        """Get the detected API version.

        Returns:
            Detected version or None if not yet detected
        """
        return self._detected_version

    def detect_version(self, response_data: dict[str, Any]) -> Literal["v4", "v5"]:
        """Detect Strapi API version from response structure.

        Args:
            response_data: Raw JSON response from Strapi

        Returns:
            Detected API version ("v4" or "v5")

        Note:
            Only caches version when detection is definitive (found attributes
            or documentId). Ambiguous responses return fallback without caching,
            allowing re-detection on subsequent meaningful responses.
        """
        # If already detected, use cached version
        if self._detected_version:
            return self._detected_version

        # V4: data.attributes structure
        # V5: flattened data with documentId
        if isinstance(response_data.get("data"), dict):
            data = response_data["data"]
            if "attributes" in data:
                self._detected_version = "v4"
                logger.info("Detected Strapi v4 API format")
            elif "documentId" in data:
                self._detected_version = "v5"
                logger.info("Detected Strapi v5 API format")
            else:
                # Don't cache - return fallback without locking
                logger.warning("Could not detect API version from object data, using v4 fallback")
                return "v4"
        elif isinstance(response_data.get("data"), list) and response_data["data"]:
            # Check first item in list
            first_item = response_data["data"][0]
            if "attributes" in first_item:
                self._detected_version = "v4"
                logger.info("Detected Strapi v4 API format")
            elif "documentId" in first_item:
                self._detected_version = "v5"
                logger.info("Detected Strapi v5 API format")
            else:
                # Don't cache - return fallback without locking
                logger.warning("Could not detect API version from list data, using v4 fallback")
                return "v4"
        else:
            # Empty/no data - don't cache, return fallback
            return "v4"

        return self._detected_version

    def parse_single(self, response_data: dict[str, Any]) -> NormalizedSingleResponse:
        """Parse a single entity response into normalized format.

        Args:
            response_data: Raw JSON response from Strapi

        Returns:
            Normalized single entity response

        Examples:
            >>> parser = VersionDetectingParser()
            >>> response = {"data": {"id": 1, "documentId": "abc", ...}}
            >>> normalized = parser.parse_single(response)
            >>> normalized.data.id
            1
        """
        # Detect API version from response
        api_version = self.detect_version(response_data)

        if api_version == "v4":
            # Parse as v4 and normalize
            v4_response = V4SingleResponse(**response_data)
            if v4_response.data:
                normalized_entity = NormalizedEntity.from_v4(v4_response.data)
            else:
                normalized_entity = None

            return NormalizedSingleResponse(data=normalized_entity, meta=v4_response.meta)
        else:
            # Parse as v5 and normalize
            v5_response = V5SingleResponse(**response_data)
            if v5_response.data:
                normalized_entity = NormalizedEntity.from_v5(v5_response.data)
            else:
                normalized_entity = None

            return NormalizedSingleResponse(data=normalized_entity, meta=v5_response.meta)

    def parse_collection(self, response_data: dict[str, Any]) -> NormalizedCollectionResponse:
        """Parse a collection response into normalized format.

        Args:
            response_data: Raw JSON response from Strapi

        Returns:
            Normalized collection response

        Examples:
            >>> parser = VersionDetectingParser()
            >>> response = {"data": [{"id": 1, ...}, {"id": 2, ...}]}
            >>> normalized = parser.parse_collection(response)
            >>> len(normalized.data)
            2
        """
        # Detect API version from response
        api_version = self.detect_version(response_data)

        if api_version == "v4":
            # Parse as v4 and normalize
            v4_response = V4CollectionResponse(**response_data)
            normalized_entities = [NormalizedEntity.from_v4(entity) for entity in v4_response.data]

            return NormalizedCollectionResponse(data=normalized_entities, meta=v4_response.meta)
        else:
            # Parse as v5 and normalize
            v5_response = V5CollectionResponse(**response_data)
            normalized_entities = [NormalizedEntity.from_v5(entity) for entity in v5_response.data]

            return NormalizedCollectionResponse(data=normalized_entities, meta=v5_response.meta)
