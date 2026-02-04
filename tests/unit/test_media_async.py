"""Tests for AsyncClient media operations."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import httpx
import pytest
import respx

from strapi_kit.client.async_client import AsyncClient
from strapi_kit.exceptions import MediaError, NotFoundError

if TYPE_CHECKING:
    from strapi_kit import StrapiConfig


@pytest.fixture
def mock_media_response() -> dict:
    """Mock media file response."""
    return {
        "id": 1,
        "documentId": "media_abc123",
        "name": "test-image.jpg",
        "alternativeText": "Test image",
        "caption": "Test caption",
        "width": 1920,
        "height": 1080,
        "formats": {
            "thumbnail": {
                "name": "thumbnail",
                "hash": "hash_abc",
                "ext": ".jpg",
                "mime": "image/jpeg",
                "url": "/uploads/thumbnail_test.jpg",
                "width": 150,
                "height": 150,
                "size": 15.5,
            },
        },
        "hash": "hash_abc123",
        "ext": ".jpg",
        "mime": "image/jpeg",
        "size": 250.75,
        "url": "/uploads/test-image.jpg",
        "provider": "local",
        "createdAt": "2024-01-01T00:00:00.000Z",
        "updatedAt": "2024-01-01T00:00:00.000Z",
    }


class TestUploadFile:
    """Tests for upload_file method."""

    @respx.mock
    async def test_upload_file_minimal(
        self, strapi_config: StrapiConfig, mock_media_response: dict, tmp_path: Path
    ) -> None:
        """Test uploading a file with minimal parameters."""
        # Create test file
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image data")

        # Mock upload endpoint (returns array with single file)
        respx.post("http://localhost:1337/api/upload").mock(
            return_value=httpx.Response(200, json=[mock_media_response])
        )

        async with AsyncClient(strapi_config) as client:
            media = await client.upload_file(test_file)

            assert media.id == 1
            assert media.name == "test-image.jpg"
            assert media.mime == "image/jpeg"

    @respx.mock
    async def test_upload_file_with_metadata(
        self, strapi_config: StrapiConfig, mock_media_response: dict, tmp_path: Path
    ) -> None:
        """Test uploading a file with metadata."""
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image data")

        # Mock with updated metadata
        response_data = {**mock_media_response, "alternativeText": "Custom alt text"}
        respx.post("http://localhost:1337/api/upload").mock(
            return_value=httpx.Response(200, json=[response_data])
        )

        async with AsyncClient(strapi_config) as client:
            media = await client.upload_file(
                test_file,
                alternative_text="Custom alt text",
                caption="Custom caption",
            )

            assert media.alternative_text == "Custom alt text"

    @respx.mock
    async def test_upload_file_with_reference(
        self, strapi_config: StrapiConfig, mock_media_response: dict, tmp_path: Path
    ) -> None:
        """Test uploading a file with entity reference."""
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image data")

        respx.post("http://localhost:1337/api/upload").mock(
            return_value=httpx.Response(200, json=[mock_media_response])
        )

        async with AsyncClient(strapi_config) as client:
            media = await client.upload_file(
                test_file,
                ref="api::article.article",
                ref_id="abc123",
                field="cover",
            )

            assert media.id == 1

    async def test_upload_file_not_found(self, strapi_config: StrapiConfig) -> None:
        """Test uploading a non-existent file."""
        async with AsyncClient(strapi_config) as client:
            with pytest.raises(FileNotFoundError):
                await client.upload_file("/nonexistent/file.jpg")

    @respx.mock
    async def test_upload_file_api_error(self, strapi_config: StrapiConfig, tmp_path: Path) -> None:
        """Test handling upload API errors."""
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image data")

        # Mock 413 - file too large
        respx.post("http://localhost:1337/api/upload").mock(
            return_value=httpx.Response(413, json={"error": {"message": "File too large"}})
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(MediaError):
                await client.upload_file(test_file)


class TestUploadFiles:
    """Tests for upload_files method."""

    @respx.mock
    async def test_upload_multiple_files(
        self, strapi_config: StrapiConfig, mock_media_response: dict, tmp_path: Path
    ) -> None:
        """Test uploading multiple files."""
        # Create test files
        files = []
        for i in range(3):
            test_file = tmp_path / f"test{i}.jpg"
            test_file.write_bytes(b"fake image data")
            files.append(test_file)

        # Mock upload for each file
        for i, _ in enumerate(files):
            response = {**mock_media_response, "id": i + 1, "name": f"test{i}.jpg"}
            respx.post("http://localhost:1337/api/upload").mock(
                return_value=httpx.Response(200, json=[response])
            )

        async with AsyncClient(strapi_config) as client:
            media_list = await client.upload_files(files)

            assert len(media_list) == 3
            assert all(isinstance(m.id, int) for m in media_list)

    @respx.mock
    async def test_upload_files_partial_failure(
        self, strapi_config: StrapiConfig, mock_media_response: dict, tmp_path: Path
    ) -> None:
        """Test upload_files with partial failure."""
        # Create test files
        files = [tmp_path / f"test{i}.jpg" for i in range(3)]
        for f in files:
            f.write_bytes(b"fake image data")

        # First upload succeeds, second fails
        respx.post("http://localhost:1337/api/upload").mock(
            side_effect=[
                httpx.Response(200, json=[mock_media_response]),
                httpx.Response(413, json={"error": {"message": "File too large"}}),
            ]
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(MediaError, match="Batch upload failed at file 1"):
                await client.upload_files(files)


class TestDownloadFile:
    """Tests for download_file method."""

    @respx.mock
    async def test_download_file_to_bytes(self, strapi_config: StrapiConfig) -> None:
        """Test downloading a file to bytes."""
        file_content = b"fake image data"
        respx.get("http://localhost:1337/uploads/test.jpg").mock(
            return_value=httpx.Response(200, content=file_content)
        )

        async with AsyncClient(strapi_config) as client:
            content = await client.download_file("/uploads/test.jpg")

            assert content == file_content

    @respx.mock
    async def test_download_file_and_save(
        self, strapi_config: StrapiConfig, tmp_path: Path
    ) -> None:
        """Test downloading a file and saving to disk."""
        file_content = b"fake image data"
        respx.get("http://localhost:1337/uploads/test.jpg").mock(
            return_value=httpx.Response(200, content=file_content)
        )

        save_path = tmp_path / "downloaded.jpg"

        async with AsyncClient(strapi_config) as client:
            content = await client.download_file("/uploads/test.jpg", save_path=save_path)

            assert content == file_content
            assert save_path.exists()
            assert save_path.read_bytes() == file_content

    @respx.mock
    async def test_download_file_absolute_url(self, strapi_config: StrapiConfig) -> None:
        """Test downloading from absolute URL."""
        file_content = b"fake image data"
        respx.get("https://cdn.example.com/uploads/test.jpg").mock(
            return_value=httpx.Response(200, content=file_content)
        )

        async with AsyncClient(strapi_config) as client:
            content = await client.download_file("https://cdn.example.com/uploads/test.jpg")

            assert content == file_content

    @respx.mock
    async def test_download_file_not_found(self, strapi_config: StrapiConfig) -> None:
        """Test downloading non-existent file."""
        respx.get("http://localhost:1337/uploads/missing.jpg").mock(
            return_value=httpx.Response(404, json={"error": {"message": "Not found"}})
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(MediaError):
                await client.download_file("/uploads/missing.jpg")


class TestListMedia:
    """Tests for list_media method."""

    @respx.mock
    async def test_list_media_all(
        self, strapi_config: StrapiConfig, mock_media_response: dict
    ) -> None:
        """Test listing all media files."""
        response_data = {
            "data": [
                mock_media_response,
                {**mock_media_response, "id": 2, "name": "test2.jpg"},
            ],
            "meta": {"pagination": {"page": 1, "pageSize": 25, "total": 2}},
        }

        respx.get("http://localhost:1337/api/upload/files").mock(
            return_value=httpx.Response(200, json=response_data)
        )

        async with AsyncClient(strapi_config) as client:
            result = await client.list_media()

            assert len(result.data) == 2
            assert result.meta is not None
            assert result.meta.pagination is not None
            assert result.meta.pagination.total == 2

    @respx.mock
    async def test_list_media_with_filters(
        self, strapi_config: StrapiConfig, mock_media_response: dict
    ) -> None:
        """Test listing media with query filters."""
        from strapi_kit.models import FilterBuilder, StrapiQuery

        response_data = {
            "data": [mock_media_response],
            "meta": {"pagination": {"page": 1, "pageSize": 10, "total": 1}},
        }

        respx.get("http://localhost:1337/api/upload/files").mock(
            return_value=httpx.Response(200, json=response_data)
        )

        async with AsyncClient(strapi_config) as client:
            query = (
                StrapiQuery()
                .filter(FilterBuilder().eq("mime", "image/jpeg"))
                .paginate(page=1, page_size=10)
            )
            result = await client.list_media(query)

            assert len(result.data) == 1


class TestGetMedia:
    """Tests for get_media method."""

    @respx.mock
    async def test_get_media_by_id(
        self, strapi_config: StrapiConfig, mock_media_response: dict
    ) -> None:
        """Test getting media by ID."""
        respx.get("http://localhost:1337/api/upload/files/1").mock(
            return_value=httpx.Response(200, json=mock_media_response)
        )

        async with AsyncClient(strapi_config) as client:
            media = await client.get_media(1)

            assert media.id == 1
            assert media.name == "test-image.jpg"

    @respx.mock
    async def test_get_media_not_found(self, strapi_config: StrapiConfig) -> None:
        """Test getting non-existent media."""
        respx.get("http://localhost:1337/api/upload/files/999").mock(
            return_value=httpx.Response(404, json={"error": {"message": "Not found"}})
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError):
                await client.get_media(999)


class TestDeleteMedia:
    """Tests for delete_media method."""

    @respx.mock
    async def test_delete_media_success(self, strapi_config: StrapiConfig) -> None:
        """Test deleting media successfully."""
        respx.delete("http://localhost:1337/api/upload/files/1").mock(
            return_value=httpx.Response(200, json={})
        )

        async with AsyncClient(strapi_config) as client:
            # Should not raise
            await client.delete_media(1)

    @respx.mock
    async def test_delete_media_not_found(self, strapi_config: StrapiConfig) -> None:
        """Test deleting non-existent media raises NotFoundError."""
        respx.delete("http://localhost:1337/api/upload/files/999").mock(
            return_value=httpx.Response(404, json={"error": {"message": "Not found"}})
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError):
                await client.delete_media(999)


class TestUpdateMedia:
    """Tests for update_media method."""

    @respx.mock
    async def test_update_media_alt_text(
        self, strapi_config: StrapiConfig, mock_media_response: dict
    ) -> None:
        """Test updating media alt text."""
        updated_response = {**mock_media_response, "alternativeText": "Updated alt text"}
        # Version detection: get_media is called first when _api_version is None
        respx.get("http://localhost:1337/api/upload/files/1").mock(
            return_value=httpx.Response(200, json=mock_media_response)
        )
        # Strapi v5 uses POST /api/upload?id=x for updates
        respx.post(url__regex=r".*/api/upload\?id=1$").mock(
            return_value=httpx.Response(200, json=updated_response)
        )

        async with AsyncClient(strapi_config) as client:
            media = await client.update_media(1, alternative_text="Updated alt text")

            assert media.alternative_text == "Updated alt text"

    @respx.mock
    async def test_update_media_multiple_fields(
        self, strapi_config: StrapiConfig, mock_media_response: dict
    ) -> None:
        """Test updating multiple media fields."""
        updated_response = {
            **mock_media_response,
            "alternativeText": "New alt",
            "caption": "New caption",
            "name": "new-name.jpg",
        }
        # Version detection: get_media is called first when _api_version is None
        respx.get("http://localhost:1337/api/upload/files/1").mock(
            return_value=httpx.Response(200, json=mock_media_response)
        )
        # Strapi v5 uses POST /api/upload?id=x for updates
        respx.post(url__regex=r".*/api/upload\?id=1$").mock(
            return_value=httpx.Response(200, json=updated_response)
        )

        async with AsyncClient(strapi_config) as client:
            media = await client.update_media(
                1,
                alternative_text="New alt",
                caption="New caption",
                name="new-name.jpg",
            )

            assert media.alternative_text == "New alt"
            assert media.caption == "New caption"

    @respx.mock
    async def test_update_media_not_found(self, strapi_config: StrapiConfig) -> None:
        """Test updating non-existent media raises NotFoundError."""
        # Version detection: get_media is called first and returns 404
        respx.get("http://localhost:1337/api/upload/files/999").mock(
            return_value=httpx.Response(404, json={"error": {"message": "Not found"}})
        )

        async with AsyncClient(strapi_config) as client:
            with pytest.raises(NotFoundError):
                await client.update_media(999, alternative_text="New alt")
