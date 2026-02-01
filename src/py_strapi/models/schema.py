"""Content type schema models."""

from enum import Enum

from pydantic import BaseModel, Field


class FieldType(str, Enum):
    """Field types in Strapi."""

    STRING = "string"
    TEXT = "text"
    RICH_TEXT = "richtext"
    EMAIL = "email"
    PASSWORD = "password"  # nosec B105 - This is a field type enum, not a hardcoded password
    INTEGER = "integer"
    BIG_INTEGER = "biginteger"
    FLOAT = "float"
    DECIMAL = "decimal"
    DATE = "date"
    TIME = "time"
    DATETIME = "datetime"
    TIMESTAMP = "timestamp"
    BOOLEAN = "boolean"
    ENUMERATION = "enumeration"
    JSON = "json"
    MEDIA = "media"
    RELATION = "relation"
    COMPONENT = "component"
    DYNAMIC_ZONE = "dynamiczone"
    UID = "uid"


class RelationType(str, Enum):
    """Relation types in Strapi."""

    ONE_TO_ONE = "oneToOne"
    ONE_TO_MANY = "oneToMany"
    MANY_TO_ONE = "manyToOne"
    MANY_TO_MANY = "manyToMany"


class FieldSchema(BaseModel):
    """Schema for a single field."""

    type: FieldType
    required: bool = False
    unique: bool = False

    # Relation-specific
    relation: RelationType | None = None
    target: str | None = None  # Target content type UID
    mapped_by: str | None = None
    inversed_by: str | None = None


class ContentTypeSchema(BaseModel):
    """Complete schema for a content type."""

    uid: str
    display_name: str
    kind: str = "collectionType"
    singular_name: str | None = Field(None, description="Singular name from Strapi schema")
    plural_name: str | None = Field(
        None, description="Plural name from Strapi schema (API endpoint)"
    )
    fields: dict[str, FieldSchema] = Field(default_factory=dict)

    def get_field_target(self, field_name: str) -> str | None:
        """Get target content type for a relation field.

        Args:
            field_name: Name of the field to check

        Returns:
            Target content type UID if field is a relation, None otherwise
        """
        field = self.fields.get(field_name)
        if field and field.type == FieldType.RELATION:
            return field.target
        return None

    def is_relation_field(self, field_name: str) -> bool:
        """Check if a field is a relation.

        Args:
            field_name: Name of the field to check

        Returns:
            True if field is a relation, False otherwise
        """
        field = self.fields.get(field_name)
        return field is not None and field.type == FieldType.RELATION
