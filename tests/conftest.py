"""Pytest configuration and shared fixtures."""

import pytest

from py_strapi import StrapiConfig


@pytest.fixture
def strapi_config() -> StrapiConfig:
    """Create a test Strapi configuration.

    Returns:
        Test configuration with mock values
    """
    return StrapiConfig(
        base_url="http://localhost:1337",
        api_token="test-token-12345678",
    )


@pytest.fixture
def mock_v4_response() -> dict:
    """Create a mock Strapi v4 API response.

    Returns:
        Mock v4 response with nested attributes
    """
    return {
        "data": {
            "id": 1,
            "attributes": {
                "title": "Test Article",
                "content": "Test content",
                "createdAt": "2024-01-01T00:00:00.000Z",
                "updatedAt": "2024-01-01T00:00:00.000Z",
                "publishedAt": "2024-01-01T00:00:00.000Z",
            },
        },
        "meta": {},
    }


@pytest.fixture
def mock_v5_response() -> dict:
    """Create a mock Strapi v5 API response.

    Returns:
        Mock v5 response with flattened structure
    """
    return {
        "data": {
            "id": 1,
            "documentId": "abc123def456",
            "title": "Test Article",
            "content": "Test content",
            "createdAt": "2024-01-01T00:00:00.000Z",
            "updatedAt": "2024-01-01T00:00:00.000Z",
            "publishedAt": "2024-01-01T00:00:00.000Z",
        },
        "meta": {},
    }


@pytest.fixture
def mock_v4_list_response() -> dict:
    """Create a mock Strapi v4 list response.

    Returns:
        Mock v4 list response
    """
    return {
        "data": [
            {
                "id": 1,
                "attributes": {
                    "title": "Article 1",
                    "content": "Content 1",
                },
            },
            {
                "id": 2,
                "attributes": {
                    "title": "Article 2",
                    "content": "Content 2",
                },
            },
        ],
        "meta": {
            "pagination": {
                "page": 1,
                "pageSize": 25,
                "pageCount": 1,
                "total": 2,
            }
        },
    }


@pytest.fixture
def mock_v5_list_response() -> dict:
    """Create a mock Strapi v5 list response.

    Returns:
        Mock v5 list response
    """
    return {
        "data": [
            {
                "id": 1,
                "documentId": "abc123",
                "title": "Article 1",
                "content": "Content 1",
            },
            {
                "id": 2,
                "documentId": "def456",
                "title": "Article 2",
                "content": "Content 2",
            },
        ],
        "meta": {
            "pagination": {
                "page": 1,
                "pageSize": 25,
                "pageCount": 1,
                "total": 2,
            }
        },
    }
