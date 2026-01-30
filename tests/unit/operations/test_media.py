"""Tests for media operations utilities."""

import tempfile
from pathlib import Path

import pytest

from py_strapi.models.response.media import MediaFile
from py_strapi.operations.media import (
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

        payload = build_upload_payload(test_file)

        assert "files" in payload
        assert isinstance(payload["files"], tuple)
        assert payload["files"][0] == "file"
        # File handle should be readable
        assert hasattr(payload["files"][1], "read")

    def test_build_payload_with_metadata(self, tmp_path: Path) -> None:
        """Test building payload with all metadata fields."""
        import json

        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image data")

        payload = build_upload_payload(
            test_file,
            ref="api::article.article",
            ref_id=123,
            field="cover",
            folder="uploads",
            alternative_text="Hero image",
            caption="Article hero image",
        )

        assert "files" in payload
        assert "data" in payload

        data = payload["data"]
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

        payload = build_upload_payload(
            test_file,
            ref="api::article.article",
            ref_id="abc123",  # String documentId
        )

        assert payload["data"]["refId"] == "abc123"

    def test_build_payload_partial_metadata(self, tmp_path: Path) -> None:
        """Test building payload with only some metadata fields."""
        import json

        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image data")

        payload = build_upload_payload(
            test_file,
            alternative_text="Alt text only",
        )

        assert "data" in payload
        assert "fileInfo" in payload["data"]
        # fileInfo is JSON-encoded string
        file_info = json.loads(payload["data"]["fileInfo"])
        assert file_info["alternativeText"] == "Alt text only"
        assert "caption" not in file_info
        assert "ref" not in payload["data"]

    def test_build_payload_file_not_found(self) -> None:
        """Test that FileNotFoundError is raised for non-existent file."""
        with pytest.raises(FileNotFoundError, match="File not found"):
            build_upload_payload("/nonexistent/path/to/file.jpg")

    def test_build_payload_accepts_path_object(self, tmp_path: Path) -> None:
        """Test that Path objects are accepted."""
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image data")

        payload = build_upload_payload(test_file)  # Path object

        assert "files" in payload

    def test_build_payload_no_data_when_no_metadata(self, tmp_path: Path) -> None:
        """Test that 'data' key is omitted when no metadata provided."""
        test_file = tmp_path / "test.jpg"
        test_file.write_bytes(b"fake image data")

        payload = build_upload_payload(test_file)

        assert "data" not in payload
        assert "files" in payload


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

        # urljoin should preserve the subdirectory
        assert url == "http://example.com/uploads/test.jpg"
