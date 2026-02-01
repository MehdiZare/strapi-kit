"""Content type UID utilities.

This module provides centralized functions for handling Strapi content type UIDs,
including conversion to API endpoints with proper pluralization.
"""


def uid_to_endpoint(uid: str) -> str:
    """Convert content type UID to API endpoint.

    Handles common English pluralization patterns. For custom pluralization
    (e.g., "person" -> "people"), use the schema's plural_name instead.

    Args:
        uid: Content type UID (e.g., "api::article.article")

    Returns:
        API endpoint (e.g., "articles")

    Examples:
        >>> uid_to_endpoint("api::article.article")
        'articles'
        >>> uid_to_endpoint("api::category.category")
        'categories'
        >>> uid_to_endpoint("api::class.class")
        'classes'
    """
    # Extract the last part after "::" and make it plural
    parts = uid.split("::")
    if len(parts) == 2:
        name = parts[1].split(".")[0]
        # Handle common irregular plurals
        if name.endswith("y") and not name.endswith(("ay", "ey", "oy", "uy")):
            return name[:-1] + "ies"  # category -> categories
        if name.endswith(("s", "x", "z", "ch", "sh")):
            return name + "es"  # class -> classes
        if not name.endswith("s"):
            return name + "s"
        return name
    return uid


def extract_model_name(uid: str) -> str:
    """Extract the model name from a content type UID.

    Args:
        uid: Content type UID (e.g., "api::article.article")

    Returns:
        Model name (e.g., "article")

    Examples:
        >>> extract_model_name("api::article.article")
        'article'
        >>> extract_model_name("plugin::users-permissions.user")
        'user'
    """
    parts = uid.split("::")
    if len(parts) == 2:
        model_parts = parts[1].split(".")
        return model_parts[-1] if model_parts else parts[1]
    return uid


def is_api_content_type(uid: str) -> bool:
    """Check if UID is an API content type (vs plugin).

    Args:
        uid: Content type UID

    Returns:
        True if API content type, False if plugin or other

    Examples:
        >>> is_api_content_type("api::article.article")
        True
        >>> is_api_content_type("plugin::users-permissions.user")
        False
    """
    return uid.startswith("api::")
