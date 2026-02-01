"""Content-Type Builder API response models.

This module provides Pydantic models for parsing responses from
Strapi's Content-Type Builder API.
"""

from typing import Any

from pydantic import BaseModel, Field


class ContentTypeInfo(BaseModel):
    """Content type info metadata.

    Contains display and naming information for a content type.
    """

    display_name: str = Field(alias="displayName")
    singular_name: str | None = Field(None, alias="singularName")
    plural_name: str | None = Field(None, alias="pluralName")
    description: str | None = None

    model_config = {"populate_by_name": True}


class ContentTypeListItem(BaseModel):
    """Content type list item from Content-Type Builder API.

    Represents a single content type in the list response.
    """

    uid: str
    kind: str = "collectionType"
    info: ContentTypeInfo
    attributes: dict[str, Any] = Field(default_factory=dict)
    plugin_options: dict[str, Any] | None = Field(None, alias="pluginOptions")

    model_config = {"populate_by_name": True}


class ComponentListItem(BaseModel):
    """Component list item from Content-Type Builder API.

    Represents a single component in the list response.
    """

    uid: str
    category: str
    info: ContentTypeInfo
    attributes: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class ContentTypeSchema(BaseModel):
    """Full content type schema from Content-Type Builder API.

    Contains complete schema information including all attributes
    and their configurations.
    """

    uid: str
    kind: str = "collectionType"
    info: ContentTypeInfo
    attributes: dict[str, Any] = Field(default_factory=dict)
    plugin_options: dict[str, Any] | None = Field(None, alias="pluginOptions")
    options: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}

    @property
    def display_name(self) -> str:
        """Get the display name from info."""
        return self.info.display_name

    @property
    def singular_name(self) -> str | None:
        """Get the singular name from info."""
        return self.info.singular_name

    @property
    def plural_name(self) -> str | None:
        """Get the plural name from info."""
        return self.info.plural_name

    def get_field_type(self, field_name: str) -> str | None:
        """Get the type of a specific field.

        Args:
            field_name: Name of the field

        Returns:
            Field type string or None if not found
        """
        field = self.attributes.get(field_name)
        if isinstance(field, dict):
            return field.get("type")
        return None

    def is_relation_field(self, field_name: str) -> bool:
        """Check if a field is a relation.

        Args:
            field_name: Name of the field

        Returns:
            True if field is a relation
        """
        return self.get_field_type(field_name) == "relation"

    def is_component_field(self, field_name: str) -> bool:
        """Check if a field is a component.

        Args:
            field_name: Name of the field

        Returns:
            True if field is a component
        """
        return self.get_field_type(field_name) == "component"

    def get_relation_target(self, field_name: str) -> str | None:
        """Get the target content type for a relation field.

        Args:
            field_name: Name of the relation field

        Returns:
            Target content type UID or None
        """
        field = self.attributes.get(field_name)
        if isinstance(field, dict) and field.get("type") == "relation":
            return field.get("target")
        return None

    def get_component_uid(self, field_name: str) -> str | None:
        """Get the component UID for a component field.

        Args:
            field_name: Name of the component field

        Returns:
            Component UID or None
        """
        field = self.attributes.get(field_name)
        if isinstance(field, dict) and field.get("type") == "component":
            return field.get("component")
        return None
