"""Tests for UID utility functions."""

from strapi_kit.utils import (
    api_id_to_singular,
    extract_model_name,
    is_api_content_type,
    uid_to_admin_url,
    uid_to_api_id,
    uid_to_endpoint,
)


class TestUidToEndpoint:
    """Tests for uid_to_endpoint function."""

    def test_standard_pluralization(self) -> None:
        """Test standard -s pluralization."""
        assert uid_to_endpoint("api::article.article") == "articles"
        assert uid_to_endpoint("api::post.post") == "posts"
        assert uid_to_endpoint("api::user.user") == "users"

    def test_y_to_ies_pluralization(self) -> None:
        """Test -y to -ies pluralization."""
        assert uid_to_endpoint("api::category.category") == "categories"
        assert uid_to_endpoint("api::company.company") == "companies"

    def test_es_pluralization(self) -> None:
        """Test -es pluralization for s, x, z, ch, sh endings."""
        assert uid_to_endpoint("api::class.class") == "classes"
        assert uid_to_endpoint("api::box.box") == "boxes"
        # Note: Current implementation adds -es for words ending in z
        # "quiz" -> "quizes" (not "quizzes" with double z)
        assert uid_to_endpoint("api::quiz.quiz") == "quizes"
        assert uid_to_endpoint("api::batch.batch") == "batches"
        assert uid_to_endpoint("api::dish.dish") == "dishes"

    def test_blog_post_pattern(self) -> None:
        """Test uid with different namespace and model name."""
        assert uid_to_endpoint("api::blog.post") == "posts"

    def test_already_plural(self) -> None:
        """Test model name that already ends with s (adds -es for s-ending words)."""
        # The current implementation adds -es to words ending in s
        # For truly plural-only words, use the schema's plural_name instead
        assert uid_to_endpoint("api::news.news") == "newses"

    def test_plugin_uid(self) -> None:
        """Test plugin content type UID."""
        assert uid_to_endpoint("plugin::users-permissions.user") == "users"

    def test_malformed_uid(self) -> None:
        """Test handling of malformed UID."""
        assert uid_to_endpoint("invalid-uid") == "invalid-uid"


class TestApiIdToSingular:
    """Tests for api_id_to_singular function."""

    def test_standard_s_removal(self) -> None:
        """Test standard -s removal."""
        assert api_id_to_singular("articles") == "article"
        assert api_id_to_singular("posts") == "post"
        assert api_id_to_singular("users") == "user"

    def test_ies_to_y(self) -> None:
        """Test -ies to -y conversion."""
        assert api_id_to_singular("categories") == "category"
        assert api_id_to_singular("companies") == "company"
        assert api_id_to_singular("libraries") == "library"

    def test_es_removal(self) -> None:
        """Test -es removal for s, x, z, ch, sh endings."""
        assert api_id_to_singular("classes") == "class"
        assert api_id_to_singular("boxes") == "box"
        assert api_id_to_singular("batches") == "batch"
        assert api_id_to_singular("dishes") == "dish"
        assert api_id_to_singular("buses") == "bus"

    def test_irregular_plurals(self) -> None:
        """Test irregular plural handling."""
        assert api_id_to_singular("people") == "person"
        assert api_id_to_singular("children") == "child"
        assert api_id_to_singular("men") == "man"
        assert api_id_to_singular("women") == "woman"
        assert api_id_to_singular("feet") == "foot"
        assert api_id_to_singular("teeth") == "tooth"
        assert api_id_to_singular("mice") == "mouse"
        assert api_id_to_singular("geese") == "goose"

    def test_latin_greek_plurals(self) -> None:
        """Test Latin/Greek irregular plurals."""
        assert api_id_to_singular("indices") == "index"
        assert api_id_to_singular("matrices") == "matrix"
        assert api_id_to_singular("vertices") == "vertex"
        assert api_id_to_singular("analyses") == "analysis"
        assert api_id_to_singular("crises") == "crisis"
        assert api_id_to_singular("phenomena") == "phenomenon"
        assert api_id_to_singular("criteria") == "criterion"

    def test_already_singular(self) -> None:
        """Test handling of already singular words."""
        assert api_id_to_singular("article") == "article"
        assert api_id_to_singular("post") == "post"

    def test_case_insensitive(self) -> None:
        """Test case insensitivity."""
        assert api_id_to_singular("Articles") == "article"
        assert api_id_to_singular("CATEGORIES") == "category"
        assert api_id_to_singular("People") == "person"


class TestUidToAdminUrl:
    """Tests for uid_to_admin_url function."""

    def test_collection_type_url(self) -> None:
        """Test admin URL for collection types."""
        url = uid_to_admin_url("api::article.article", "http://localhost:1337")
        assert url == (
            "http://localhost:1337/admin/content-manager/collection-types/api::article.article"
        )

    def test_single_type_url(self) -> None:
        """Test admin URL for single types."""
        url = uid_to_admin_url(
            "api::homepage.homepage",
            "http://localhost:1337",
            kind="singleType",
        )
        assert url == (
            "http://localhost:1337/admin/content-manager/single-types/api::homepage.homepage"
        )

    def test_trailing_slash_removal(self) -> None:
        """Test that trailing slash is removed from base URL."""
        url = uid_to_admin_url("api::article.article", "http://localhost:1337/")
        assert url == (
            "http://localhost:1337/admin/content-manager/collection-types/api::article.article"
        )

    def test_plugin_uid(self) -> None:
        """Test admin URL for plugin content types."""
        url = uid_to_admin_url(
            "plugin::users-permissions.user",
            "http://localhost:1337",
        )
        assert url == (
            "http://localhost:1337/admin/content-manager/"
            "collection-types/plugin::users-permissions.user"
        )

    def test_with_https(self) -> None:
        """Test with HTTPS URL."""
        url = uid_to_admin_url("api::article.article", "https://strapi.example.com")
        assert url == (
            "https://strapi.example.com/admin/content-manager/collection-types/api::article.article"
        )


class TestUidToApiId:
    """Tests for uid_to_api_id alias."""

    def test_is_alias_for_uid_to_endpoint(self) -> None:
        """Test that uid_to_api_id is an alias for uid_to_endpoint."""
        assert uid_to_api_id is uid_to_endpoint

    def test_produces_same_results(self) -> None:
        """Test that results are identical."""
        test_uids = [
            "api::article.article",
            "api::category.category",
            "api::class.class",
            "plugin::users-permissions.user",
        ]
        for uid in test_uids:
            assert uid_to_api_id(uid) == uid_to_endpoint(uid)


class TestExtractModelName:
    """Tests for extract_model_name function."""

    def test_api_content_type(self) -> None:
        """Test extraction from API content type."""
        assert extract_model_name("api::article.article") == "article"
        assert extract_model_name("api::blog.post") == "post"

    def test_plugin_content_type(self) -> None:
        """Test extraction from plugin content type."""
        assert extract_model_name("plugin::users-permissions.user") == "user"

    def test_malformed_uid(self) -> None:
        """Test handling of malformed UID."""
        assert extract_model_name("invalid") == "invalid"


class TestIsApiContentType:
    """Tests for is_api_content_type function."""

    def test_api_content_type(self) -> None:
        """Test detection of API content types."""
        assert is_api_content_type("api::article.article") is True
        assert is_api_content_type("api::blog.post") is True

    def test_plugin_content_type(self) -> None:
        """Test detection of plugin content types."""
        assert is_api_content_type("plugin::users-permissions.user") is False
        assert is_api_content_type("plugin::upload.file") is False

    def test_other_prefixes(self) -> None:
        """Test other UID prefixes."""
        assert is_api_content_type("admin::user") is False
        assert is_api_content_type("invalid") is False
