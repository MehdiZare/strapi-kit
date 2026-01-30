"""Tests for media file models."""



from py_strapi.models.response.media import MediaFile, MediaFormat


class TestMediaFormat:
    """Tests for MediaFormat model."""

    def test_basic_format(self) -> None:
        """Test basic media format."""
        fmt = MediaFormat(
            name="thumbnail",
            hash="abc123",
            ext=".jpg",
            mime="image/jpeg",
            width=150,
            height=150,
            size=10.5,
            url="/uploads/thumbnail_image.jpg",
        )

        assert fmt.name == "thumbnail"
        assert fmt.width == 150
        assert fmt.height == 150
        assert fmt.size == 10.5

    def test_format_from_api(self) -> None:
        """Test parsing format from API response."""
        api_data = {
            "name": "small",
            "hash": "def456",
            "ext": ".png",
            "mime": "image/png",
            "width": 500,
            "height": 500,
            "size": 50.25,
            "path": None,
            "url": "/uploads/small_image.png",
        }

        fmt = MediaFormat(**api_data)

        assert fmt.name == "small"
        assert fmt.size == 50.25


class TestMediaFile:
    """Tests for MediaFile model."""

    def test_basic_media_file(self) -> None:
        """Test basic media file."""
        media = MediaFile(
            id=1,
            name="test-image.jpg",
            hash="abc123",
            ext=".jpg",
            mime="image/jpeg",
            size=100.5,
            url="/uploads/test-image.jpg",
            provider="local",
        )

        assert media.id == 1
        assert media.name == "test-image.jpg"
        assert media.size == 100.5
        assert media.provider == "local"

    def test_media_with_formats(self) -> None:
        """Test media file with multiple formats."""
        media = MediaFile(
            id=1,
            name="image.jpg",
            hash="abc",
            ext=".jpg",
            mime="image/jpeg",
            size=200.0,
            url="/uploads/image.jpg",
            provider="local",
            formats={
                "thumbnail": MediaFormat(
                    name="thumbnail",
                    hash="abc",
                    ext=".jpg",
                    mime="image/jpeg",
                    width=150,
                    height=150,
                    size=10.0,
                    url="/uploads/thumbnail_image.jpg",
                ),
                "small": MediaFormat(
                    name="small",
                    hash="abc",
                    ext=".jpg",
                    mime="image/jpeg",
                    width=500,
                    height=500,
                    size=50.0,
                    url="/uploads/small_image.jpg",
                ),
            },
        )

        assert media.formats is not None
        assert "thumbnail" in media.formats
        assert "small" in media.formats
        assert media.formats["thumbnail"].width == 150
        assert media.formats["small"].width == 500

    def test_media_from_api_v5(self) -> None:
        """Test parsing media file from v5 API response."""
        api_data = {
            "id": 42,
            "documentId": "media_abc123",
            "name": "hero-image.jpg",
            "alternativeText": "Hero image",
            "caption": "Main hero image",
            "width": 1920,
            "height": 1080,
            "hash": "hero_123",
            "ext": ".jpg",
            "mime": "image/jpeg",
            "size": 250.75,
            "url": "/uploads/hero-image.jpg",
            "previewUrl": None,
            "provider": "local",
            "providerMetadata": None,
            "createdAt": "2024-01-01T00:00:00.000Z",
            "updatedAt": "2024-01-02T00:00:00.000Z",
        }

        media = MediaFile(**api_data)

        assert media.id == 42
        assert media.document_id == "media_abc123"
        assert media.name == "hero-image.jpg"
        assert media.alternative_text == "Hero image"
        assert media.caption == "Main hero image"
        assert media.width == 1920
        assert media.height == 1080

    def test_media_without_image_dimensions(self) -> None:
        """Test media file without image dimensions (e.g., PDF)."""
        media = MediaFile(
            id=1,
            name="document.pdf",
            hash="pdf123",
            ext=".pdf",
            mime="application/pdf",
            size=500.0,
            url="/uploads/document.pdf",
            provider="local",
        )

        assert media.width is None
        assert media.height is None
        assert media.mime == "application/pdf"
