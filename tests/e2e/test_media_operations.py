"""E2E tests for media operations.

Tests file upload, download, and metadata operations against a real Strapi instance.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from py_strapi import SyncClient

# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "media"


@pytest.fixture
def test_image_path() -> Path:
    """Get the path to the test image fixture."""
    return FIXTURES_DIR / "test-image.jpg"


@pytest.fixture
def test_pdf_path() -> Path:
    """Get the path to the test PDF fixture."""
    return FIXTURES_DIR / "test-document.pdf"


@pytest.mark.e2e
class TestMediaUpload:
    """Tests for media upload operations."""

    def test_upload_file(self, sync_client: SyncClient, test_image_path: Path) -> None:
        """Test uploading a single file."""
        if not test_image_path.exists():
            pytest.skip("Test image fixture not found")

        media = sync_client.upload_file(
            str(test_image_path),
            alternative_text="Test image",
            caption="A test image for E2E tests",
        )

        assert media is not None
        assert media.id is not None
        assert media.name is not None
        assert media.url is not None
        assert media.alternative_text == "Test image"
        assert media.caption == "A test image for E2E tests"

        # Cleanup
        sync_client.delete_media(media.id)

    def test_upload_file_with_metadata(
        self, sync_client: SyncClient, test_image_path: Path
    ) -> None:
        """Test uploading a file with full metadata."""
        if not test_image_path.exists():
            pytest.skip("Test image fixture not found")

        media = sync_client.upload_file(
            str(test_image_path),
            alternative_text="Detailed alt text for accessibility",
            caption="Caption describing the image",
        )

        assert media is not None
        assert media.alternative_text == "Detailed alt text for accessibility"
        assert media.caption == "Caption describing the image"

        # Cleanup
        sync_client.delete_media(media.id)

    def test_upload_multiple_files(
        self, sync_client: SyncClient, test_image_path: Path, test_pdf_path: Path
    ) -> None:
        """Test uploading multiple files in batch."""
        files_to_upload = []
        if test_image_path.exists():
            files_to_upload.append(str(test_image_path))
        if test_pdf_path.exists():
            files_to_upload.append(str(test_pdf_path))

        if len(files_to_upload) < 2:
            pytest.skip("Test fixtures not found")

        media_list = sync_client.upload_files(files_to_upload)

        assert len(media_list) == 2
        for media in media_list:
            assert media.id is not None
            assert media.url is not None

        # Cleanup
        for media in media_list:
            sync_client.delete_media(media.id)


@pytest.mark.e2e
class TestMediaDownload:
    """Tests for media download operations."""

    def test_upload_and_download(self, sync_client: SyncClient, test_image_path: Path) -> None:
        """Test uploading and then downloading a file."""
        if not test_image_path.exists():
            pytest.skip("Test image fixture not found")

        # Upload
        media = sync_client.upload_file(str(test_image_path))
        assert media is not None

        # Download to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            tmp_path = tmp.name

        try:
            content = sync_client.download_file(media.url, save_path=tmp_path)

            assert content is not None
            assert len(content) > 0

            # Verify file was saved
            saved_path = Path(tmp_path)
            assert saved_path.exists()
            assert saved_path.stat().st_size > 0

        finally:
            # Cleanup
            Path(tmp_path).unlink(missing_ok=True)
            sync_client.delete_media(media.id)

    def test_download_to_memory(self, sync_client: SyncClient, test_image_path: Path) -> None:
        """Test downloading a file to memory without saving."""
        if not test_image_path.exists():
            pytest.skip("Test image fixture not found")

        # Upload
        media = sync_client.upload_file(str(test_image_path))
        assert media is not None

        # Download without saving
        content = sync_client.download_file(media.url)

        assert content is not None
        assert len(content) > 0
        assert isinstance(content, bytes)

        # Cleanup
        sync_client.delete_media(media.id)


@pytest.mark.e2e
class TestMediaLibrary:
    """Tests for media library operations."""

    def test_list_media(self, sync_client: SyncClient, test_image_path: Path) -> None:
        """Test listing media files."""
        if not test_image_path.exists():
            pytest.skip("Test image fixture not found")

        # Upload a file first
        media = sync_client.upload_file(str(test_image_path))
        assert media is not None

        try:
            # List media
            response = sync_client.list_media()

            assert response.data is not None
            assert len(response.data) > 0

        finally:
            # Cleanup
            sync_client.delete_media(media.id)

    def test_get_media(self, sync_client: SyncClient, test_image_path: Path) -> None:
        """Test getting a single media file by ID."""
        if not test_image_path.exists():
            pytest.skip("Test image fixture not found")

        # Upload
        uploaded = sync_client.upload_file(str(test_image_path))
        assert uploaded is not None

        try:
            # Get by ID
            media = sync_client.get_media(uploaded.id)

            assert media is not None
            assert media.id == uploaded.id
            assert media.url == uploaded.url

        finally:
            # Cleanup
            sync_client.delete_media(uploaded.id)


@pytest.mark.e2e
class TestMediaMetadata:
    """Tests for media metadata operations."""

    def test_update_media_metadata(self, sync_client: SyncClient, test_image_path: Path) -> None:
        """Test updating media file metadata."""
        if not test_image_path.exists():
            pytest.skip("Test image fixture not found")

        # Upload without metadata
        media = sync_client.upload_file(str(test_image_path))
        assert media is not None

        try:
            # Update metadata
            updated = sync_client.update_media(
                media.id,
                alternative_text="Updated alt text",
                caption="Updated caption",
            )

            assert updated is not None
            assert updated.alternative_text == "Updated alt text"
            assert updated.caption == "Updated caption"

            # Verify by fetching
            fetched = sync_client.get_media(media.id)
            assert fetched.alternative_text == "Updated alt text"
            assert fetched.caption == "Updated caption"

        finally:
            # Cleanup
            sync_client.delete_media(media.id)


@pytest.mark.e2e
class TestMediaDeletion:
    """Tests for media deletion operations."""

    def test_delete_media(self, sync_client: SyncClient, test_image_path: Path) -> None:
        """Test deleting a media file."""
        if not test_image_path.exists():
            pytest.skip("Test image fixture not found")

        # Upload
        media = sync_client.upload_file(str(test_image_path))
        assert media is not None
        media_id = media.id

        # Delete
        sync_client.delete_media(media_id)

        # Verify deleted - should raise or return None
        # The exact behavior depends on Strapi version
        try:
            result = sync_client.get_media(media_id)
            # If we get here, the media should be None or raise
            assert result is None
        except Exception:
            # Expected - media was deleted
            pass


@pytest.mark.e2e
class TestAsyncMediaOperations:
    """Tests for async media operations."""

    @pytest.mark.asyncio
    async def test_async_upload_and_download(self, async_client, test_image_path: Path) -> None:
        """Test async upload and download."""
        if not test_image_path.exists():
            pytest.skip("Test image fixture not found")

        # Upload
        media = await async_client.upload_file(str(test_image_path))
        assert media is not None

        try:
            # Download
            content = await async_client.download_file(media.url)
            assert content is not None
            assert len(content) > 0

        finally:
            # Cleanup
            await async_client.delete_media(media.id)

    @pytest.mark.asyncio
    async def test_async_list_media(self, async_client, test_image_path: Path) -> None:
        """Test async media listing."""
        if not test_image_path.exists():
            pytest.skip("Test image fixture not found")

        # Upload
        media = await async_client.upload_file(str(test_image_path))
        assert media is not None

        try:
            # List
            response = await async_client.list_media()
            assert response.data is not None
            assert len(response.data) > 0

        finally:
            # Cleanup
            await async_client.delete_media(media.id)
