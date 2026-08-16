"""Content-Type Builder API response models.

This module provides Pydantic models for parsing responses from
Strapi's Content-Type Builder API.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..utils.schema import apply_draft_and_publish_sources

_DRAFT_AND_PUBLISH_OPTION_KEYS = ("draftAndPublish", "draft_and_publish")


class ContentTypeOptions(BaseModel):
    """Content-Type Builder ``options`` (plus lifted schema-root option keys).

    ``draftAndPublish`` is **not** stored here. Use the first-class
    ``draft_and_publish`` field on the content-type models.

    Unknown keys from live ``formatContentType`` (or plugins) are kept
    via ``extra="allow"``.
    """

    populate_creator_fields: bool | None = Field(None, alias="populateCreatorFields")
    comment: str | None = None
    increments: bool | None = None
    timestamps: bool | None = None
    visible: bool | None = None
    restrict_relations_to: list[str] | None = Field(None, alias="restrictRelationsTo")
    review_workflows: bool | None = Field(None, alias="reviewWorkflows")

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    @model_validator(mode="before")
    @classmethod
    def _strip_draft_and_publish(cls, data: Any) -> Any:
        """Keep D&P off this model even when constructed directly."""
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        for key in _DRAFT_AND_PUBLISH_OPTION_KEYS:
            payload.pop(key, None)
        return payload


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

    ``draft_and_publish`` is a tri-state: ``True`` / ``False`` when Strapi
    declared Draft & Publish, ``None`` when the flag was absent. Absence is
    not ``False``.
    """

    uid: str
    kind: str = "collectionType"
    info: ContentTypeInfo
    attributes: dict[str, Any] = Field(default_factory=dict)
    plugin_options: dict[str, Any] | None = Field(None, alias="pluginOptions")
    options: ContentTypeOptions | None = None
    draft_and_publish: bool | None = Field(
        default=None,
        alias="draftAndPublish",
        description=(
            "Draft & Publish setting. True if enabled, False if explicitly "
            "disabled, None if the flag was not present. Absence is not False."
        ),
    )

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def _apply_draft_and_publish(cls, data: Any) -> Any:
        """Populate draft_and_publish and options from all known wire locations."""
        return apply_draft_and_publish_sources(data)


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

    ``draft_and_publish`` is a tri-state: ``True`` / ``False`` when Strapi
    declared Draft & Publish, ``None`` when the flag was absent. Absence is
    not ``False``.
    """

    uid: str
    kind: str = "collectionType"
    info: ContentTypeInfo
    attributes: dict[str, Any] = Field(default_factory=dict)
    plugin_options: dict[str, Any] | None = Field(None, alias="pluginOptions")
    options: ContentTypeOptions | None = None
    draft_and_publish: bool | None = Field(
        default=None,
        alias="draftAndPublish",
        description=(
            "Draft & Publish setting. True if enabled, False if explicitly "
            "disabled, None if the flag was not present. Absence is not False."
        ),
    )

    model_config = {"populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def _apply_draft_and_publish(cls, data: Any) -> Any:
        """Populate draft_and_publish and options from all known wire locations."""
        return apply_draft_and_publish_sources(data)

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
