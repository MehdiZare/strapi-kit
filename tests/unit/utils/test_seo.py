"""Tests for SEO configuration detection utilities."""

from strapi_kit.models.schema import ContentTypeSchema, FieldSchema, FieldType
from strapi_kit.utils.seo import SEOConfiguration, detect_seo_configuration


class TestSEOConfiguration:
    """Tests for SEOConfiguration dataclass."""

    def test_default_values(self) -> None:
        """Test default values."""
        config = SEOConfiguration()
        assert config.has_seo is False
        assert config.seo_type is None
        assert config.seo_field_name is None
        assert config.seo_component_uid is None
        assert config.fields == {}

    def test_with_values(self) -> None:
        """Test with explicit values."""
        config = SEOConfiguration(
            has_seo=True,
            seo_type="component",
            seo_field_name="seo",
            seo_component_uid="shared.seo",
            fields={"title": "seo.metaTitle"},
        )
        assert config.has_seo is True
        assert config.seo_type == "component"
        assert config.seo_field_name == "seo"
        assert config.seo_component_uid == "shared.seo"
        assert config.fields == {"title": "seo.metaTitle"}


class TestDetectSEOComponentSchema:
    """Tests for component-based SEO detection using ContentTypeSchema."""

    def test_detect_seo_component_by_field_name(self) -> None:
        """Test detection of SEO component by field name."""
        schema = ContentTypeSchema(
            uid="api::article.article",
            display_name="Article",
            fields={
                "title": FieldSchema(type=FieldType.STRING),
                "seo": FieldSchema(type=FieldType.COMPONENT),
            },
        )
        config = detect_seo_configuration(schema)

        assert config.has_seo is True
        assert config.seo_type == "component"
        assert config.seo_field_name == "seo"

    def test_detect_meta_component_by_field_name(self) -> None:
        """Test detection of meta component by field name."""
        schema = ContentTypeSchema(
            uid="api::page.page",
            display_name="Page",
            fields={
                "title": FieldSchema(type=FieldType.STRING),
                "meta": FieldSchema(type=FieldType.COMPONENT),
            },
        )
        config = detect_seo_configuration(schema)

        assert config.has_seo is True
        assert config.seo_type == "component"
        assert config.seo_field_name == "meta"

    def test_detect_metadata_component(self) -> None:
        """Test detection of metadata component."""
        schema = ContentTypeSchema(
            uid="api::article.article",
            display_name="Article",
            fields={
                "metadata": FieldSchema(type=FieldType.COMPONENT),
            },
        )
        config = detect_seo_configuration(schema)

        assert config.has_seo is True
        assert config.seo_type == "component"
        assert config.seo_field_name == "metadata"

    def test_component_field_mappings(self) -> None:
        """Test that component detection provides field mappings."""
        schema = ContentTypeSchema(
            uid="api::article.article",
            display_name="Article",
            fields={
                "seo": FieldSchema(type=FieldType.COMPONENT),
            },
        )
        config = detect_seo_configuration(schema)

        assert "title" in config.fields
        assert "description" in config.fields
        assert config.fields["title"] == "seo.metaTitle"
        assert config.fields["description"] == "seo.metaDescription"


class TestDetectSEOComponentDict:
    """Tests for component-based SEO detection using dict schemas."""

    def test_detect_seo_component_by_uid(self) -> None:
        """Test detection of SEO component by component UID."""
        schema = {
            "uid": "api::article.article",
            "attributes": {
                "title": {"type": "string"},
                "meta_info": {"type": "component", "component": "shared.seo"},
            },
        }
        config = detect_seo_configuration(schema)

        assert config.has_seo is True
        assert config.seo_type == "component"
        assert config.seo_field_name == "meta_info"
        assert config.seo_component_uid == "shared.seo"

    def test_detect_seo_in_component_uid(self) -> None:
        """Test detection when 'seo' is in component UID."""
        schema = {
            "uid": "api::article.article",
            "attributes": {
                "pageInfo": {"type": "component", "component": "custom.page-seo"},
            },
        }
        config = detect_seo_configuration(schema)

        assert config.has_seo is True
        assert config.seo_type == "component"
        assert config.seo_component_uid == "custom.page-seo"

    def test_fields_format(self) -> None:
        """Test detection using 'fields' key instead of 'attributes'."""
        schema = {
            "uid": "api::article.article",
            "fields": {
                "seo": {"type": "component", "component": "shared.seo"},
            },
        }
        config = detect_seo_configuration(schema)

        assert config.has_seo is True
        assert config.seo_type == "component"


class TestDetectFlatSEOFields:
    """Tests for flat SEO field detection."""

    def test_detect_meta_title_field(self) -> None:
        """Test detection of metaTitle field."""
        schema = {
            "uid": "api::page.page",
            "attributes": {
                "title": {"type": "string"},
                "metaTitle": {"type": "string"},
            },
        }
        config = detect_seo_configuration(schema)

        assert config.has_seo is True
        assert config.seo_type == "flat"
        assert config.fields.get("title") == "metaTitle"

    def test_detect_multiple_flat_fields(self) -> None:
        """Test detection of multiple flat SEO fields."""
        schema = {
            "uid": "api::page.page",
            "attributes": {
                "title": {"type": "string"},
                "metaTitle": {"type": "string"},
                "metaDescription": {"type": "text"},
                "metaKeywords": {"type": "string"},
                "canonicalUrl": {"type": "string"},
            },
        }
        config = detect_seo_configuration(schema)

        assert config.has_seo is True
        assert config.seo_type == "flat"
        assert config.fields.get("title") == "metaTitle"
        assert config.fields.get("description") == "metaDescription"
        assert config.fields.get("keywords") == "metaKeywords"
        assert config.fields.get("canonical_url") == "canonicalUrl"

    def test_detect_underscore_variant(self) -> None:
        """Test detection of underscore variant field names."""
        schema = {
            "uid": "api::page.page",
            "attributes": {
                "meta_title": {"type": "string"},
                "meta_description": {"type": "text"},
            },
        }
        config = detect_seo_configuration(schema)

        assert config.has_seo is True
        assert config.seo_type == "flat"
        assert config.fields.get("title") == "meta_title"
        assert config.fields.get("description") == "meta_description"

    def test_detect_seo_prefix_variant(self) -> None:
        """Test detection of SEO-prefixed field names."""
        schema = {
            "uid": "api::page.page",
            "attributes": {
                "seoTitle": {"type": "string"},
                "seoDescription": {"type": "text"},
            },
        }
        config = detect_seo_configuration(schema)

        assert config.has_seo is True
        assert config.seo_type == "flat"
        assert config.fields.get("title") == "seoTitle"
        assert config.fields.get("description") == "seoDescription"

    def test_detect_og_fields(self) -> None:
        """Test detection of Open Graph fields."""
        schema = {
            "uid": "api::page.page",
            "attributes": {
                "ogTitle": {"type": "string"},
                "ogDescription": {"type": "text"},
                "ogImage": {"type": "media"},
            },
        }
        config = detect_seo_configuration(schema)

        assert config.has_seo is True
        assert config.seo_type == "flat"
        assert config.fields.get("og_title") == "ogTitle"
        assert config.fields.get("og_description") == "ogDescription"
        assert config.fields.get("og_image") == "ogImage"

    def test_detect_robots_fields(self) -> None:
        """Test detection of robots/noindex fields."""
        schema = {
            "uid": "api::page.page",
            "attributes": {
                "noIndex": {"type": "boolean"},
                "noFollow": {"type": "boolean"},
                "robots": {"type": "string"},
            },
        }
        config = detect_seo_configuration(schema)

        assert config.has_seo is True
        assert config.seo_type == "flat"
        assert config.fields.get("no_index") == "noIndex"
        assert config.fields.get("no_follow") == "noFollow"
        assert config.fields.get("robots") == "robots"


class TestNoSEODetection:
    """Tests for schemas without SEO configuration."""

    def test_no_seo_fields(self) -> None:
        """Test schema without any SEO fields."""
        schema = {
            "uid": "api::article.article",
            "attributes": {
                "title": {"type": "string"},
                "content": {"type": "richtext"},
                "publishedAt": {"type": "datetime"},
            },
        }
        config = detect_seo_configuration(schema)

        assert config.has_seo is False
        assert config.seo_type is None
        assert config.seo_field_name is None
        assert config.fields == {}

    def test_empty_schema(self) -> None:
        """Test empty schema."""
        schema: dict = {}
        config = detect_seo_configuration(schema)

        assert config.has_seo is False

    def test_schema_with_unrelated_component(self) -> None:
        """Test schema with non-SEO component."""
        schema = {
            "uid": "api::article.article",
            "attributes": {
                "gallery": {"type": "component", "component": "shared.gallery"},
                "author": {"type": "relation"},
            },
        }
        config = detect_seo_configuration(schema)

        assert config.has_seo is False

    def test_content_type_schema_no_seo(self) -> None:
        """Test ContentTypeSchema without SEO."""
        schema = ContentTypeSchema(
            uid="api::article.article",
            display_name="Article",
            fields={
                "title": FieldSchema(type=FieldType.STRING),
                "content": FieldSchema(type=FieldType.RICH_TEXT),
            },
        )
        config = detect_seo_configuration(schema)

        assert config.has_seo is False


class TestCaseInsensitivity:
    """Tests for case-insensitive matching."""

    def test_uppercase_field_name(self) -> None:
        """Test uppercase field name detection."""
        schema = {
            "uid": "api::page.page",
            "attributes": {
                "SEO": {"type": "component", "component": "shared.seo"},
            },
        }
        config = detect_seo_configuration(schema)

        assert config.has_seo is True
        assert config.seo_type == "component"

    def test_mixed_case_flat_fields(self) -> None:
        """Test mixed case flat field detection."""
        schema = {
            "uid": "api::page.page",
            "attributes": {
                "METATITLE": {"type": "string"},
                "MetaDescription": {"type": "text"},
            },
        }
        config = detect_seo_configuration(schema)

        assert config.has_seo is True
        assert config.seo_type == "flat"

    def test_uppercase_component_uid(self) -> None:
        """Test uppercase component UID detection."""
        schema = {
            "uid": "api::article.article",
            "attributes": {
                "info": {"type": "component", "component": "Shared.SEO"},
            },
        }
        config = detect_seo_configuration(schema)

        assert config.has_seo is True
        assert config.seo_type == "component"


class TestComponentPreferenceOverFlat:
    """Tests for component detection taking precedence over flat fields."""

    def test_component_preferred_over_flat(self) -> None:
        """Test that component detection is preferred over flat fields."""
        schema = {
            "uid": "api::page.page",
            "attributes": {
                "seo": {"type": "component", "component": "shared.seo"},
                "metaTitle": {"type": "string"},  # Also has flat field
            },
        }
        config = detect_seo_configuration(schema)

        # Should detect component, not flat
        assert config.has_seo is True
        assert config.seo_type == "component"
        assert config.seo_field_name == "seo"
