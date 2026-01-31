"""Field selection for Strapi API queries.

Allows selecting specific fields to return in the response, reducing
payload size and improving performance.

Examples:
    Select specific fields:
        >>> fields = FieldSelection(fields=["title", "description", "publishedAt"])
        >>> fields.to_query_dict()
        {'fields': ['title', 'description', 'publishedAt']}

    Select all fields (default):
        >>> fields = FieldSelection()  # Returns all fields
        >>> fields.to_query_dict()
        {}
"""

from typing import Any

from pydantic import BaseModel, Field


class FieldSelection(BaseModel):
    """Field selection configuration.

    Specifies which fields to include in the response. If no fields are
    specified, all fields are returned by default.

    Attributes:
        fields: List of field names to return (empty = all fields)
    """

    fields: list[str] = Field(
        default_factory=list,
        description="List of field names to include in response (empty = all)",
    )

    def to_query_dict(self) -> dict[str, Any]:
        """Convert to query parameters dictionary.

        Returns:
            Dictionary with fields parameter, or empty if no fields specified

        Examples:
            >>> FieldSelection(fields=["title", "description"]).to_query_dict()
            {'fields': ['title', 'description']}

            >>> FieldSelection().to_query_dict()
            {}
        """
        if not self.fields:
            return {}
        return {"fields": self.fields}

    def to_query_list(self) -> list[str]:
        """Get list of field names.

        Returns:
            List of field names

        Examples:
            >>> FieldSelection(fields=["title", "description"]).to_query_list()
            ['title', 'description']
        """
        return self.fields
