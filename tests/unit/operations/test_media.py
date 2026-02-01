"""Tests for media operations utilities."""

from pathlib import Path

import pytest

from strapi_kit.exceptions import MediaError
from strapi_kit.models.response.media import MediaFile
from strapi_kit.operations.media import (
    build_media_download_url,
    build_upload_payload,
    normalize_media_response,
)


class TestBuildUploadPayload:
    """Tests for build_upload_payload function."""

    def test_build_payload_minimal(self, tmp_path: Path) -> None:
        """Test building payload with only required file_path."""
        # Create temporary file
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image data")

        with build_upload_payload(test_file) as payload:
            files_tuple = payload.files_tuple
            assert isinstance(files_tuple, tuple)
            assert files_tuple[0] == "test.jpg"  # Actual filename, not "file"
            # File handle should be readable
            assert hasattr(files_tuple[1], "read")
            # MIME type should be detected
            assert files_tuple[2] == "image/jpeg"

    def test_build_payload_with_metadata(self, tmp_path: Path) -> None:
        """Test building payload with all metadata fields."""
        import json

        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image data")

        with build_upload_payload(
            test_file,
            ref="api::article.article",
            ref_id=123,
            field="cover",
            folder="uploads",
            alternative_text="Hero image",
            caption="Article hero image",
        ) as payload:
            data = payload.data
            assert data is not None
            assert data["ref"] == "api::article.article"
            assert data["refId"] == "123"  # Converted to string
            assert data["field"] == "cover"
            assert data["folder"] == "uploads"
            assert "fileInfo" in data
            # fileInfo is JSON-encoded string for httpx multipart
            file_info = json.loads(data["fileInfo"])
            assert file_info["alternativeText"] == "Hero image"
            assert file_info["caption"] == "Article hero image"

    def test_build_payload_string_ref_id(self, tmp_path: Path) -> None:
        """Test that ref_id accepts string documentId."""
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image data")

        with build_upload_payload(
            test_file,
            ref="api::article.article",
            ref_id="abc123",  # String documentId
        ) as payload:
            assert payload.data is not None
            assert payload.data["refId"] == "abc123"

    def test_build_payload_partial_metadata(self, tmp_path: Path) -> None:
        """Test building payload with only some metadata fields."""
        import json

        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image data")

        with build_upload_payload(
            test_file,
            alternative_text="Alt text only",
        ) as payload:
            data = payload.data
            assert data is not None
            assert "fileInfo" in data
            # fileInfo is JSON-encoded string
            file_info = json.loads(data["fileInfo"])
            assert file_info["alternativeText"] == "Alt text only"
            assert "caption" not in file_info
            assert "ref" not in data

    def test_build_payload_file_not_found(self) -> None:
        """Test that FileNotFoundError is raised for non-existent file."""
        with pytest.raises(FileNotFoundError, match="File not found"):
            build_upload_payload("/nonexistent/path/to/file.jpg")

    def test_build_payload_mime_type_png(self, tmp_path: Path) -> None:
        """Test MIME type detection for PNG files."""
        test_file = tmp_path / "image.png"
        test_file.write_bytes(b"fake png data")

        with build_upload_payload(test_file) as payload:
            files_tuple = payload.files_tuple
            assert files_tuple[0] == "image.png"
            assert files_tuple[2] == "image/png"

    def test_build_payload_mime_type_pdf(self, tmp_path: Path) -> None:
        """Test MIME type detection for PDF files."""
        test_file = tmp_path / "document.pdf"
        test_file.write_bytes(b"fake pdf data")

        with build_upload_payload(test_file) as payload:
            files_tuple = payload.files_tuple
            assert files_tuple[0] == "document.pdf"
            assert files_tuple[2] == "application/pdf"

    def test_build_payload_mime_type_txt(self, tmp_path: Path) -> None:
        """Test MIME type detection for text files."""
        test_file = tmp_path / "readme.txt"
        test_file.write_bytes(b"fake text data")

        with build_upload_payload(test_file) as payload:
            files_tuple = payload.files_tuple
            assert files_tuple[0] == "readme.txt"
            assert files_tuple[2] == "text/plain"

    def test_build_payload_mime_type_unknown(self, tmp_path: Path) -> None:
        """Test MIME type fallback for unknown file extensions."""
        test_file = tmp_path / "data.unknownext123"
        test_file.write_bytes(b"fake unknown data")

        with build_upload_payload(test_file) as payload:
            files_tuple = payload.files_tuple
            assert files_tuple[0] == "data.unknownext123"
            # Unknown extensions should fallback to octet-stream
            assert files_tuple[2] == "application/octet-stream"

    def test_build_payload_accepts_path_object(self, tmp_path: Path) -> None:
        """Test that Path objects are accepted."""
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image data")

        with build_upload_payload(test_file) as payload:  # Path object
            assert payload.files_tuple is not None

    def test_build_payload_no_data_when_no_metadata(self, tmp_path: Path) -> None:
        """Test that 'data' is None when no metadata provided."""
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image data")

        with build_upload_payload(test_file) as payload:
            assert payload.data is None
            assert payload.files_tuple is not None


class TestUploadPayloadContextManager:
    """Tests for UploadPayload context manager file handle cleanup."""

    def test_file_handle_closed_after_context(self, tmp_path: Path) -> None:
        """Test that file handle is properly closed after context manager exits."""
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image data")

        upload_payload = build_upload_payload(test_file)

        # Get reference to file handle inside context
        file_handle = None
        with upload_payload as payload:
            file_handle = payload.files_tuple[1]
            assert not file_handle.closed

        # After context exit, file should be closed
        assert file_handle is not None
        assert file_handle.closed

    def test_file_handle_closed_on_exception(self, tmp_path: Path) -> None:
        """Test that file handle is closed even when exception occurs."""
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image data")

        upload_payload = build_upload_payload(test_file)

        file_handle = None
        with pytest.raises(RuntimeError, match="Test exception"):
            with upload_payload as payload:
                file_handle = payload.files_tuple[1]
                assert not file_handle.closed
                raise RuntimeError("Test exception")

        # After context exit with exception, file should still be closed
        assert file_handle is not None
        assert file_handle.closed

    def test_accessing_files_tuple_outside_context_raises(self, tmp_path: Path) -> None:
        """Test that accessing files_tuple outside context manager raises error."""
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image data")

        upload_payload = build_upload_payload(test_file)

        with pytest.raises(MediaError, match="must be used as a context manager"):
            _ = upload_payload.files_tuple

    def test_multiple_context_entries(self, tmp_path: Path) -> None:
        """Test that UploadPayload can be used multiple times."""
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image data")

        upload_payload = build_upload_payload(test_file)

        # First use
        with upload_payload as payload:
            content1 = payload.files_tuple[1].read()
            assert content1 == b"fake image data"

        # Second use (should work with fresh file handle)
        with upload_payload as payload:
            content2 = payload.files_tuple[1].read()
            assert content2 == b"fake image data"


class TestNormalizeMediaResponse:
    """Tests for normalize_media_response function."""

    def test_normalize_v5_response(self) -> None:
        """Test normalizing v5 flattened response."""
        v5_data = {
            "id": 1,
            "documentId": "abc123",
            "name": "test.jpg",
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
            "hash": "hash_abc",
            "ext": ".jpg",
            "mime": "image/jpeg",
            "size": 250.75,
            "url": "/uploads/test.jpg",
            "provider": "local",
            "createdAt": "2024-01-01T00:00:00.000Z",
            "updatedAt": "2024-01-01T00:00:00.000Z",
        }

        media = normalize_media_response(v5_data, "v5")

        assert isinstance(media, MediaFile)
        assert media.id == 1
        assert media.document_id == "abc123"
        assert media.name == "test.jpg"
        assert media.alternative_text == "Test image"
        assert media.mime == "image/jpeg"

    def test_normalize_v4_response(self) -> None:
        """Test normalizing v4 nested response."""
        v4_data = {
            "id": 1,
            "attributes": {
                "name": "test.jpg",
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
                "hash": "hash_abc",
                "ext": ".jpg",
                "mime": "image/jpeg",
                "size": 250.75,
                "url": "/uploads/test.jpg",
                "provider": "local",
                "createdAt": "2024-01-01T00:00:00.000Z",
                "updatedAt": "2024-01-01T00:00:00.000Z",
            },
        }

        media = normalize_media_response(v4_data, "v4")

        assert isinstance(media, MediaFile)
        assert media.id == 1
        assert media.document_id is None  # v4 doesn't have documentId
        assert media.name == "test.jpg"
        assert media.alternative_text == "Test image"
        assert media.mime == "image/jpeg"

    def test_normalize_v4_already_flattened(self) -> None:
        """Test v4 normalization when response is already flattened."""
        # Some v4 endpoints may return flattened data
        v4_flat = {
            "id": 1,
            "name": "test.jpg",
            "mime": "image/jpeg",
            "url": "/uploads/test.jpg",
            "size": 100.5,
            "ext": ".jpg",
            "hash": "hash_abc",
            "provider": "local",
            "createdAt": "2024-01-01T00:00:00.000Z",
            "updatedAt": "2024-01-01T00:00:00.000Z",
        }

        media = normalize_media_response(v4_flat, "v4")

        assert isinstance(media, MediaFile)
        assert media.id == 1
        assert media.name == "test.jpg"

    def test_normalize_minimal_response(self) -> None:
        """Test normalization with minimal required fields."""
        minimal_data = {
            "id": 1,
            "name": "test.jpg",
            "mime": "image/jpeg",
            "url": "/uploads/test.jpg",
            "size": 100.5,
            "ext": ".jpg",
            "hash": "hash_abc",
            "provider": "local",
            "createdAt": "2024-01-01T00:00:00.000Z",
            "updatedAt": "2024-01-01T00:00:00.000Z",
        }

        media = normalize_media_response(minimal_data, "v5")

        assert isinstance(media, MediaFile)
        assert media.id == 1
        assert media.name == "test.jpg"
        assert media.alternative_text is None
        assert media.caption is None


class TestBuildMediaDownloadUrl:
    """Tests for build_media_download_url function."""

    def test_build_url_relative_path(self) -> None:
        """Test building URL from relative path."""
        url = build_media_download_url(
            "http://localhost:1337",
            "/uploads/test.jpg",
        )

        assert url == "http://localhost:1337/uploads/test.jpg"

    def test_build_url_with_trailing_slash(self) -> None:
        """Test that trailing slash in base_url is handled correctly."""
        url = build_media_download_url(
            "http://localhost:1337/",  # Trailing slash
            "/uploads/test.jpg",
        )

        assert url == "http://localhost:1337/uploads/test.jpg"

    def test_build_url_absolute_http(self) -> None:
        """Test that absolute HTTP URLs are returned as-is."""
        absolute_url = "http://cdn.example.com/uploads/test.jpg"
        url = build_media_download_url(
            "http://localhost:1337",
            absolute_url,
        )

        assert url == absolute_url

    def test_build_url_absolute_https(self) -> None:
        """Test that absolute HTTPS URLs are returned as-is."""
        absolute_url = "https://cdn.example.com/uploads/test.jpg"
        url = build_media_download_url(
            "http://localhost:1337",
            absolute_url,
        )

        assert url == absolute_url

    def test_build_url_relative_without_leading_slash(self) -> None:
        """Test building URL from relative path without leading slash."""
        url = build_media_download_url(
            "http://localhost:1337",
            "uploads/test.jpg",  # No leading slash
        )

        # urljoin should handle this correctly
        assert "test.jpg" in url

    def test_build_url_with_port(self) -> None:
        """Test building URL with custom port."""
        url = build_media_download_url(
            "http://localhost:8080",
            "/uploads/test.jpg",
        )

        assert url == "http://localhost:8080/uploads/test.jpg"

    def test_build_url_with_subdirectory(self) -> None:
        """Test building URL when base_url has subdirectory."""
        url = build_media_download_url(
            "http://example.com/strapi",
            "/uploads/test.jpg",
        )

        # urljoin replaces path when media_url starts with "/" (absolute path)
        # This is expected behavior - Strapi media URLs are absolute paths from root
        assert url == "http://example.com/uploads/test.jpg"
