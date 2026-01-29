"""Asynchronous HTTP client for Strapi API.

This module provides non-blocking I/O operations for high-concurrency
applications and batch operations.
"""

import logging
from typing import Any

import httpx

from ..exceptions import (
    ConnectionError as StrapiConnectionError,
)
from ..exceptions import (
    TimeoutError as StrapiTimeoutError,
)
from ..models.config import StrapiConfig
from ..models.request.query import StrapiQuery
from ..models.response.normalized import NormalizedCollectionResponse, NormalizedSingleResponse
from .base import BaseClient

logger = logging.getLogger(__name__)


class AsyncClient(BaseClient):
    """Asynchronous HTTP client for Strapi API.

    This client uses non-blocking I/O and is suitable for:
    - High-concurrency applications
    - Batch operations on many documents
    - Applications using async/await patterns

    Example:
        ```python
        import asyncio
        from py_strapi import AsyncClient, StrapiConfig

        async def main():
            config = StrapiConfig(
                base_url="http://localhost:1337",
                api_token="your-token"
            )

            async with AsyncClient(config) as client:
                response = await client.get("articles")
                print(response)

        asyncio.run(main())
        ```
    """

    def __init__(self, config: StrapiConfig) -> None:
        """Initialize the asynchronous client.

        Args:
            config: Strapi configuration
        """
        super().__init__(config)

        # Create HTTPX async client with connection pooling
        self._client = httpx.AsyncClient(
            timeout=config.timeout,
            verify=config.verify_ssl,
            limits=httpx.Limits(
                max_connections=config.max_connections,
                max_keepalive_connections=config.max_connections,
            ),
        )

    async def __aenter__(self) -> "AsyncClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit - closes the client."""
        await self.close()

    async def close(self) -> None:
        """Close the HTTP client and release connections."""
        await self._client.aclose()
        logger.info("Closed asynchronous Strapi client")

    async def request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request to the Strapi API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            params: URL query parameters
            json: JSON request body
            headers: Additional headers

        Returns:
            Response JSON data

        Raises:
            StrapiError: On API errors
            ConnectionError: On connection failures
            TimeoutError: On request timeout
        """
        url = self._build_url(endpoint)
        request_headers = self._get_headers(headers)

        logger.debug(f"{method} {url} params={params}")

        try:
            response = await self._client.request(
                method=method,
                url=url,
                params=params,
                json=json,
                headers=request_headers,
            )

            # Handle error responses
            if not response.is_success:
                self._handle_error_response(response)

            # Parse and return JSON
            data: dict[str, Any] = response.json()

            # Detect API version from response
            if data and isinstance(data, dict):
                self._detect_api_version(data)

            logger.debug(f"Response: {response.status_code}")
            return data

        except httpx.ConnectError as e:
            raise StrapiConnectionError(f"Failed to connect to {self.base_url}: {e}") from e
        except httpx.TimeoutException as e:
            raise StrapiTimeoutError(
                f"Request timed out after {self.config.timeout}s: {e}"
            ) from e

    async def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make a GET request.

        Args:
            endpoint: API endpoint path
            params: URL query parameters
            headers: Additional headers

        Returns:
            Response JSON data
        """
        return await self.request("GET", endpoint, params=params, headers=headers)

    async def post(
        self,
        endpoint: str,
        json: dict[str, Any],
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make a POST request.

        Args:
            endpoint: API endpoint path
            json: JSON request body
            params: URL query parameters
            headers: Additional headers

        Returns:
            Response JSON data
        """
        return await self.request("POST", endpoint, params=params, json=json, headers=headers)

    async def put(
        self,
        endpoint: str,
        json: dict[str, Any],
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make a PUT request.

        Args:
            endpoint: API endpoint path
            json: JSON request body
            params: URL query parameters
            headers: Additional headers

        Returns:
            Response JSON data
        """
        return await self.request("PUT", endpoint, params=params, json=json, headers=headers)

    async def delete(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make a DELETE request.

        Args:
            endpoint: API endpoint path
            params: URL query parameters
            headers: Additional headers

        Returns:
            Response JSON data
        """
        return await self.request("DELETE", endpoint, params=params, headers=headers)

    # Typed methods for normalized responses

    async def get_one(
        self,
        endpoint: str,
        query: StrapiQuery | None = None,
        headers: dict[str, str] | None = None,
    ) -> NormalizedSingleResponse:
        """Get a single entity with typed, normalized response.

        Args:
            endpoint: API endpoint path (e.g., "articles/1" or "articles/abc123")
            query: Optional query configuration (populate, fields, locale, etc.)
            headers: Additional headers

        Returns:
            Normalized single entity response

        Examples:
            >>> from py_strapi.models import StrapiQuery, Populate
            >>> query = (StrapiQuery()
            ...     .populate_fields(["author", "category"])
            ...     .select(["title", "content"]))
            >>> response = await client.get_one("articles/1", query=query)
            >>> article = response.data
            >>> article.attributes["title"]
            'My Article'
        """
        params = query.to_query_params() if query else None
        raw_response = await self.get(endpoint, params=params, headers=headers)
        return self._parse_single_response(raw_response)

    async def get_many(
        self,
        endpoint: str,
        query: StrapiQuery | None = None,
        headers: dict[str, str] | None = None,
    ) -> NormalizedCollectionResponse:
        """Get multiple entities with typed, normalized response.

        Args:
            endpoint: API endpoint path (e.g., "articles")
            query: Optional query configuration (filters, sort, pagination, etc.)
            headers: Additional headers

        Returns:
            Normalized collection response

        Examples:
            >>> from py_strapi.models import StrapiQuery, FilterBuilder, SortDirection
            >>> query = (StrapiQuery()
            ...     .filter(FilterBuilder().eq("status", "published"))
            ...     .sort_by("publishedAt", SortDirection.DESC)
            ...     .paginate(page=1, page_size=25)
            ...     .populate_fields(["author"]))
            >>> response = await client.get_many("articles", query=query)
            >>> for article in response.data:
            ...     print(article.attributes["title"])
        """
        params = query.to_query_params() if query else None
        raw_response = await self.get(endpoint, params=params, headers=headers)
        return self._parse_collection_response(raw_response)

    async def create(
        self,
        endpoint: str,
        data: dict[str, Any],
        query: StrapiQuery | None = None,
        headers: dict[str, str] | None = None,
    ) -> NormalizedSingleResponse:
        """Create a new entity with typed, normalized response.

        Args:
            endpoint: API endpoint path (e.g., "articles")
            data: Entity data to create (wrapped in {"data": {...}} automatically)
            query: Optional query configuration (populate, fields, etc.)
            headers: Additional headers

        Returns:
            Normalized single entity response

        Examples:
            >>> data = {"title": "New Article", "content": "Article body"}
            >>> response = await client.create("articles", data)
            >>> created = response.data
            >>> created.id
            42
        """
        params = query.to_query_params() if query else None
        # Wrap data in Strapi format
        payload = {"data": data}
        raw_response = await self.post(endpoint, json=payload, params=params, headers=headers)
        return self._parse_single_response(raw_response)

    async def update(
        self,
        endpoint: str,
        data: dict[str, Any],
        query: StrapiQuery | None = None,
        headers: dict[str, str] | None = None,
    ) -> NormalizedSingleResponse:
        """Update an existing entity with typed, normalized response.

        Args:
            endpoint: API endpoint path (e.g., "articles/1" or "articles/abc123")
            data: Entity data to update (wrapped in {"data": {...}} automatically)
            query: Optional query configuration (populate, fields, etc.)
            headers: Additional headers

        Returns:
            Normalized single entity response

        Examples:
            >>> data = {"title": "Updated Title"}
            >>> response = await client.update("articles/1", data)
            >>> updated = response.data
            >>> updated.attributes["title"]
            'Updated Title'
        """
        params = query.to_query_params() if query else None
        # Wrap data in Strapi format
        payload = {"data": data}
        raw_response = await self.put(endpoint, json=payload, params=params, headers=headers)
        return self._parse_single_response(raw_response)

    async def remove(
        self,
        endpoint: str,
        headers: dict[str, str] | None = None,
    ) -> NormalizedSingleResponse:
        """Delete an entity with typed, normalized response.

        Args:
            endpoint: API endpoint path (e.g., "articles/1" or "articles/abc123")
            headers: Additional headers

        Returns:
            Normalized single entity response (deleted entity)

        Examples:
            >>> response = await client.remove("articles/1")
            >>> deleted = response.data
            >>> deleted.id
            1
        """
        raw_response = await self.delete(endpoint, headers=headers)
        return self._parse_single_response(raw_response)
