"""Tests for uniqueness classification and validation error flattening."""

import strapi_kit
from strapi_kit import exceptions
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
        """True when only exc.message contains 'must be unique' (no nested errors)."""
        exc = ValidationError("This attribute must be unique")

        assert exc.details == {}
        assert "must be unique" in exc.message
        assert is_uniqueness_violation(exc) is True

    def test_case_insensitive_exception_message(self) -> None:
        """Substring match on exc.message is case-insensitive."""
        exc = ValidationError("This attribute MUST BE UNIQUE")

        assert is_uniqueness_violation(exc) is True

    def test_details_dump_does_not_false_positive(self) -> None:
        """Unrelated details keys mentioning uniqueness do not classify."""
        exc = ValidationError(
            "body is required",
            details={"docs": "This attribute must be unique"},
        )

        assert "must be unique" in str(exc)
        assert "must be unique" not in exc.message.lower()
        assert is_uniqueness_violation(exc) is False

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

    def test_v4_data_attributes_path_is_dotted(self) -> None:
        """v4 request-body paths keep the data.attributes prefix."""
        exc = ValidationError(
            "Validation error",
            details={
                "errors": [
                    {
                        "path": ["data", "attributes", "slug"],
                        "message": "This attribute must be unique",
                    }
                ]
            },
        )

        assert format_validation_errors(exc) == (
            "data.attributes.slug: This attribute must be unique"
        )
        assert is_uniqueness_violation(exc) is True

    def test_numeric_path_segment(self) -> None:
        """Numeric dynamic-zone indexes stringify in the dotted path."""
        exc = ValidationError(
            "Validation error",
            details={
                "errors": [{"path": ["blocks", 0, "title"], "message": "title is a required field"}]
            },
        )

        assert format_validation_errors(exc) == "blocks.0.title: title is a required field"

    def test_empty_path_emits_message_only(self) -> None:
        """Missing or empty paths do not produce a leading ': '."""
        exc = ValidationError(
            "Validation error",
            details={
                "errors": [
                    {"message": "This attribute must be unique"},
                    {"path": None, "message": "This attribute must be unique"},
                    {"path": [], "message": "This attribute must be unique"},
                ]
            },
        )

        assert format_validation_errors(exc) == (
            "This attribute must be unique\n"
            "This attribute must be unique\n"
            "This attribute must be unique"
        )


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

    def test_non_dict_details_does_not_raise(self) -> None:
        """Non-dict details (malformed HTTP payloads) yield no field errors."""
        exc = ValidationError("Invalid")
        exc.details = "This attribute must be unique"  # type: ignore[assignment]

        assert exc.field_errors == []
        assert format_validation_errors(exc) is None
        assert is_uniqueness_violation(exc) is False

    def test_non_list_errors_yields_empty(self) -> None:
        """Dict-shaped details.errors is not parsed (REST uses a list)."""
        exc = ValidationError(
            "Validation error",
            details={"errors": {"slug": ["This attribute must be unique"]}},
        )

        assert exc.field_errors == []
        assert format_validation_errors(exc) is None
        assert is_uniqueness_violation(exc) is False


class TestValidationErrorCompatibility:
    """Existing ValidationError callers keep constructor / str / catch behavior."""

    def test_constructor_details_str_and_status_code(self) -> None:
        """Constructor, details, str(), and status_code stay additive."""
        exc = ValidationError(
            "body is required",
            details={"field": "title"},
            status_code=400,
        )

        assert exc.message == "body is required"
        assert exc.details == {"field": "title"}
        assert exc.status_code == 400
        assert "body is required" in str(exc)
        assert isinstance(exc, exceptions.StrapiError)
        assert is_uniqueness_violation(exc) is False
        assert format_validation_errors(exc) is None
        assert exc.field_errors == []

    def test_helpers_exported_from_package_and_exceptions(self) -> None:
        """Helpers are public on strapi_kit and strapi_kit.exceptions."""
        assert strapi_kit.is_uniqueness_violation is exceptions.is_uniqueness_violation
        assert strapi_kit.format_validation_errors is exceptions.format_validation_errors
        assert "is_uniqueness_violation" in strapi_kit.__all__
        assert "format_validation_errors" in strapi_kit.__all__
        assert "is_uniqueness_violation" in exceptions.__all__
        assert "format_validation_errors" in exceptions.__all__
