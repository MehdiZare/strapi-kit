"""Tests for bulk operations."""

import httpx
import pytest
import respx

from strapi_kit import (
    AsyncClient,
    BulkOperationResult,
    StrapiConfig,
)
from strapi_kit.client.sync_client import SyncClient


@pytest.fixture
def strapi_config() -> StrapiConfig:
    """Create test configuration."""
    return StrapiConfig(
        base_url="http://localhost:1337",
        api_token="test-token",
    )


# Sync Client Tests


@pytest.mark.respx
def test_bulk_create_all_success(strapi_config: StrapiConfig, respx_mock: respx.Router) -> None:
    """Test bulk create with all successes."""
    # Mock create responses
    for i in range(1, 4):
        respx_mock.post("http://localhost:1337/api/articles").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "id": i,
                        "documentId": f"doc{i}",
                        "title": f"Article {i}",
                    }
                },
            )
        )

    items = [
        {"title": "Article 1", "content": "Content 1"},
        {"title": "Article 2", "content": "Content 2"},
        {"title": "Article 3", "content": "Content 3"},
    ]

    with SyncClient(strapi_config) as client:
        result = client.bulk_create("articles", items, batch_size=10)

        assert isinstance(result, BulkOperationResult)
        assert result.total == 3
        assert result.succeeded == 3
        assert result.failed == 0
        assert len(result.successes) == 3
        assert len(result.failures) == 0
        assert result.is_complete_success()
        assert result.success_rate() == 1.0


@pytest.mark.respx
def test_bulk_create_partial_failures(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Test bulk create with some failures."""
    # First succeeds
    respx_mock.post("http://localhost:1337/api/articles").mock(
        side_effect=[
            httpx.Response(
                200,
                json={"data": {"id": 1, "documentId": "doc1", "title": "Article 1"}},
            ),
            # Second fails with validation error
            httpx.Response(400, json={"error": {"message": "Validation failed"}}),
            # Third succeeds
            httpx.Response(
                200,
                json={"data": {"id": 3, "documentId": "doc3", "title": "Article 3"}},
            ),
        ]
    )

    items = [
        {"title": "Article 1"},
        {"title": ""},  # Invalid - empty title
        {"title": "Article 3"},
    ]

    with SyncClient(strapi_config) as client:
        result = client.bulk_create("articles", items)

        assert result.total == 3
        assert result.succeeded == 2
        assert result.failed == 1
        assert len(result.successes) == 2
        assert len(result.failures) == 1
        assert not result.is_complete_success()
        assert result.success_rate() == pytest.approx(2 / 3)

        # Check failure details
        failure = result.failures[0]
        assert failure.index == 1
        assert failure.item == {"title": ""}
        assert "Validation" in failure.error


@pytest.mark.respx
def test_bulk_create_with_progress_callback(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Test bulk create with progress callback."""
    for i in range(1, 6):
        respx_mock.post("http://localhost:1337/api/articles").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"id": i, "documentId": f"doc{i}"}},
            )
        )

    items = [{"title": f"Article {i}"} for i in range(1, 6)]
    progress_calls = []

    def progress_callback(completed: int, total: int) -> None:
        progress_calls.append((completed, total))

    with SyncClient(strapi_config) as client:
        result = client.bulk_create("articles", items, progress_callback=progress_callback)

        assert result.succeeded == 5
        assert len(progress_calls) == 5
        assert progress_calls == [(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)]


@pytest.mark.respx
def test_bulk_create_empty_list(strapi_config: StrapiConfig, respx_mock: respx.Router) -> None:
    """Test bulk create with empty list."""
    with SyncClient(strapi_config) as client:
        result = client.bulk_create("articles", [])

        assert result.total == 0
        assert result.succeeded == 0
        assert result.failed == 0
        assert result.is_complete_success()
        assert result.success_rate() == 0.0


@pytest.mark.respx
def test_bulk_update_all_success(strapi_config: StrapiConfig, respx_mock: respx.Router) -> None:
    """Test bulk update with all successes."""
    for i in range(1, 4):
        respx_mock.put(f"http://localhost:1337/api/articles/{i}").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "id": i,
                        "documentId": f"doc{i}",
                        "title": f"Updated {i}",
                    }
                },
            )
        )

    updates = [
        (1, {"title": "Updated 1"}),
        (2, {"title": "Updated 2"}),
        (3, {"title": "Updated 3"}),
    ]

    with SyncClient(strapi_config) as client:
        result = client.bulk_update("articles", updates)

        assert result.total == 3
        assert result.succeeded == 3
        assert result.failed == 0
        assert result.is_complete_success()


@pytest.mark.respx
def test_bulk_update_partial_failures(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Test bulk update with some failures."""
    respx_mock.put("http://localhost:1337/api/articles/1").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": 1, "documentId": "doc1", "title": "Updated 1"}},
        )
    )
    respx_mock.put("http://localhost:1337/api/articles/999").mock(
        return_value=httpx.Response(404, json={"error": {"message": "Not found"}})
    )
    respx_mock.put("http://localhost:1337/api/articles/3").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": 3, "documentId": "doc3", "title": "Updated 3"}},
        )
    )

    updates = [
        (1, {"title": "Updated 1"}),
        (999, {"title": "Does not exist"}),
        (3, {"title": "Updated 3"}),
    ]

    with SyncClient(strapi_config) as client:
        result = client.bulk_update("articles", updates)

        assert result.total == 3
        assert result.succeeded == 2
        assert result.failed == 1
        assert result.failures[0].index == 1
        assert result.failures[0].item["id"] == 999


@pytest.mark.respx
def test_bulk_delete_all_success(strapi_config: StrapiConfig, respx_mock: respx.Router) -> None:
    """Test bulk delete with all successes."""
    for i in range(1, 4):
        respx_mock.delete(f"http://localhost:1337/api/articles/{i}").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"id": i, "documentId": f"doc{i}"}},
            )
        )

    ids = [1, 2, 3]

    with SyncClient(strapi_config) as client:
        result = client.bulk_delete("articles", ids)

        assert result.total == 3
        assert result.succeeded == 3
        assert result.failed == 0
        assert result.is_complete_success()


@pytest.mark.respx
def test_bulk_delete_partial_failures(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Test bulk delete with some failures."""
    respx_mock.delete("http://localhost:1337/api/articles/1").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"id": 1, "documentId": "doc1"}},
        )
    )
    respx_mock.delete("http://localhost:1337/api/articles/999").mock(
        return_value=httpx.Response(404, json={"error": {"message": "Not found"}})
    )

    ids = [1, 999]

    with SyncClient(strapi_config) as client:
        result = client.bulk_delete("articles", ids)

        assert result.total == 2
        assert result.succeeded == 1
        assert result.failed == 1
        assert result.failures[0].item["id"] == 999


# Async Client Tests


@pytest.mark.respx
async def test_async_bulk_create_all_success(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Test async bulk create with all successes."""
    for i in range(1, 6):
        respx_mock.post("http://localhost:1337/api/articles").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"id": i, "documentId": f"doc{i}"}},
            )
        )

    items = [{"title": f"Article {i}"} for i in range(1, 6)]

    async with AsyncClient(strapi_config) as client:
        result = await client.bulk_create("articles", items, max_concurrency=3)

        assert result.total == 5
        assert result.succeeded == 5
        assert result.failed == 0
        assert result.is_complete_success()


@pytest.mark.respx
async def test_async_bulk_create_partial_failures(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Test async bulk create with some failures."""
    respx_mock.post("http://localhost:1337/api/articles").mock(
        side_effect=[
            httpx.Response(200, json={"data": {"id": 1, "documentId": "doc1"}}),
            httpx.Response(400, json={"error": {"message": "Validation failed"}}),
            httpx.Response(200, json={"data": {"id": 3, "documentId": "doc3"}}),
        ]
    )

    items = [
        {"title": "Article 1"},
        {"title": ""},  # Invalid
        {"title": "Article 3"},
    ]

    async with AsyncClient(strapi_config) as client:
        result = await client.bulk_create("articles", items)

        assert result.total == 3
        assert result.succeeded == 2
        assert result.failed == 1


@pytest.mark.respx
async def test_async_bulk_update_all_success(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Test async bulk update with all successes."""
    for i in range(1, 4):
        respx_mock.put(f"http://localhost:1337/api/articles/{i}").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"id": i, "documentId": f"doc{i}"}},
            )
        )

    updates = [(i, {"title": f"Updated {i}"}) for i in range(1, 4)]

    async with AsyncClient(strapi_config) as client:
        result = await client.bulk_update("articles", updates)

        assert result.total == 3
        assert result.succeeded == 3
        assert result.failed == 0


@pytest.mark.respx
async def test_async_bulk_delete_all_success(
    strapi_config: StrapiConfig, respx_mock: respx.Router
) -> None:
    """Test async bulk delete with all successes."""
    for i in range(1, 4):
        respx_mock.delete(f"http://localhost:1337/api/articles/{i}").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"id": i, "documentId": f"doc{i}"}},
            )
        )

    ids = [1, 2, 3]

    async with AsyncClient(strapi_config) as client:
        result = await client.bulk_delete("articles", ids)

        assert result.total == 3
        assert result.succeeded == 3
        assert result.failed == 0


# BulkOperationResult Tests


def test_bulk_operation_result_is_complete_success() -> None:
    """Test is_complete_success method."""
    from strapi_kit.models.response.normalized import NormalizedEntity

    # Complete success
    result = BulkOperationResult(
        successes=[NormalizedEntity(id=1, attributes={})],
        failures=[],
        total=1,
        succeeded=1,
        failed=0,
    )
    assert result.is_complete_success()

    # Partial success
    result2 = BulkOperationResult(
        successes=[NormalizedEntity(id=1, attributes={})],
        failures=[],
        total=2,
        succeeded=1,
        failed=1,
    )
    assert not result2.is_complete_success()


def test_bulk_operation_result_success_rate() -> None:
    """Test success_rate calculation."""
    result = BulkOperationResult(
        successes=[],
        failures=[],
        total=10,
        succeeded=7,
        failed=3,
    )
    assert result.success_rate() == 0.7

    # Empty result
    empty_result = BulkOperationResult(
        successes=[],
        failures=[],
        total=0,
        succeeded=0,
        failed=0,
    )
    assert empty_result.success_rate() == 0.0
