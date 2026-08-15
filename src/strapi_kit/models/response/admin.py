"""Admin information models for origin-rooted Strapi admin endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AdminInformation(BaseModel):
    """Structured result of ``GET /admin/information``.

    This endpoint is origin-rooted (``{base}/admin/information``), not under
    ``/api``. Content, Content-Type Builder, and upload endpoints remain under
    ``/api``.

    Attributes:
        strapi_version: Version string from ``strapiVersion`` or
            ``data.strapiVersion``. ``None`` when the field is absent (a
            successful probe still returns this model).
        raw: Unmodified JSON payload from the admin information endpoint.
    """

    strapi_version: str | None = Field(
        None, description="Strapi version if present on the admin information payload"
    )
    raw: dict[str, Any] = Field(..., description="Raw JSON response")

    @classmethod
    def from_response(cls, response_data: dict[str, Any]) -> AdminInformation:
        """Parse a GET /admin/information payload.

        Looks for ``strapiVersion`` at the top level first, then
        ``data.strapiVersion``. A missing version is not an error.

        Args:
            response_data: Raw JSON object from the admin information endpoint.

        Returns:
            Structured admin information including the original payload.
        """
        return cls(strapi_version=_extract_strapi_version(response_data), raw=response_data)


def _extract_strapi_version(response_data: dict[str, Any]) -> str | None:
    """Return a version string from either supported response shape."""
    version = _coerce_version(response_data.get("strapiVersion"))
    if version is not None:
        return version

    data = response_data.get("data")
    if isinstance(data, dict):
        return _coerce_version(data.get("strapiVersion"))
    return None


def _coerce_version(value: object) -> str | None:
    """Accept a non-empty string version; ignore other types."""
    if isinstance(value, str) and value:
        return value
    return None
