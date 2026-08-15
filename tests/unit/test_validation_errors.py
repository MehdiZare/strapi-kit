"""Tests for uniqueness classification and validation error flattening."""

from strapi_kit.exceptions import (
    ValidationError,
    format_validation_errors,
    is_uniqueness_violation,
)


class TestIsUniquenessViolation:
    """Tests for is_uniqueness_violation()."""

    def test_uniqueness_in_details_errors(self) -> None:
        """True when a details.errors message contains 'must be unique'."""
        exc = ValidationError(
            "2 errors occurred",
            details={
                "errors": [
                    {
                        "path": ["slug"],
                        "message": "This attribute must be unique",
                        "name": "ValidationError",
                    },
                    {
                        "path": ["name"],
                        "message": "This attribute must be unique",
                        "name": "ValidationError",
                    },
                ]
            },
        )

        assert is_uniqueness_violation(exc) is True

    def test_uniqueness_only_in_exception_message(self) -> None:
        """True when only str(exc) contains 'must be unique' (no nested errors)."""
        exc = ValidationError("This attribute must be unique")

        assert exc.details == {}
        assert "must be unique" in str(exc)
        assert is_uniqueness_violation(exc) is True

    def test_non_uniqueness_is_false(self) -> None:
        """False for other 400s such as required-field or type errors."""
        exc = ValidationError(
            "body is required",
            details={
                "errors": [
                    {
                        "path": ["title"],
                        "message": "title is a required field",
                        "name": "ValidationError",
                    }
                ]
            },
        )

        assert is_uniqueness_violation(exc) is False

    def test_case_insensitive_details_message(self) -> None:
        """Substring match on nested messages is case-insensitive."""
        exc = ValidationError(
            "Validation error",
            details={"errors": [{"path": ["email"], "message": "This attribute MUST BE UNIQUE"}]},
        )

        assert is_uniqueness_violation(exc) is True


class TestFormatValidationErrors:
    """Tests for format_validation_errors()."""

    def test_flatten_list_path(self) -> None:
        """List paths flatten to dotted path: message lines."""
        exc = ValidationError(
            "2 errors occurred",
            details={
                "errors": [
                    {"path": ["slug"], "message": "This attribute must be unique"},
                    {"path": ["name"], "message": "This attribute must be unique"},
                ]
            },
        )

        assert format_validation_errors(exc) == (
            "slug: This attribute must be unique\nname: This attribute must be unique"
        )

    def test_flatten_string_path(self) -> None:
        """String paths are used as-is."""
        exc = ValidationError(
            "Validation error",
            details={"errors": [{"path": "slug", "message": "This attribute must be unique"}]},
        )

        assert format_validation_errors(exc) == "slug: This attribute must be unique"

    def test_skip_empty_messages(self) -> None:
        """Entries with empty or missing messages are omitted."""
        exc = ValidationError(
            "Validation error",
            details={
                "errors": [
                    {"path": ["slug"], "message": ""},
                    {"path": ["name"], "message": "   "},
                    {"path": ["email"]},
                    {"path": ["title"], "message": "title is a required field"},
                ]
            },
        )

        assert format_validation_errors(exc) == "title: title is a required field"

    def test_none_when_no_nested_errors(self) -> None:
        """Return None when there are no usable nested field errors."""
        assert format_validation_errors(ValidationError("body is required")) is None
        assert format_validation_errors(ValidationError("Invalid", details={})) is None
        assert format_validation_errors(ValidationError("Invalid", details={"errors": []})) is None
        assert (
            format_validation_errors(
                ValidationError("Invalid", details={"errors": [{"path": ["slug"], "message": ""}]})
            )
            is None
        )

    def test_nested_list_path_is_dotted(self) -> None:
        """Nested list paths join with dots."""
        exc = ValidationError(
            "Validation error",
            details={
                "errors": [
                    {"path": ["seo", "slug"], "message": "This attribute must be unique"},
                ]
            },
        )

        assert format_validation_errors(exc) == "seo.slug: This attribute must be unique"


class TestFieldErrorsProperty:
    """Tests for ValidationError.field_errors."""

    def test_parses_path_message_pairs(self) -> None:
        """field_errors exposes the parsed (path, message) pairs."""
        exc = ValidationError(
            "2 errors occurred",
            details={
                "errors": [
                    {"path": ["slug"], "message": "This attribute must be unique"},
                    {"path": "name", "message": "This attribute must be unique"},
                ]
            },
        )

        assert exc.field_errors == [
            ("slug", "This attribute must be unique"),
            ("name", "This attribute must be unique"),
        ]

    def test_empty_when_no_nested_errors(self) -> None:
        """field_errors is empty when details.errors is missing."""
        assert ValidationError("body is required").field_errors == []
