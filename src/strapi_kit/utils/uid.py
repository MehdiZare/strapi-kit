"""Content type UID utilities.

This module provides centralized functions for handling Strapi content type UIDs,
including conversion to API endpoints with proper pluralization.
"""

# Irregular plurals mapping (plural -> singular)
_IRREGULAR_PLURALS: dict[str, str] = {
    "people": "person",
    "children": "child",
    "men": "man",
    "women": "woman",
    "feet": "foot",
    "teeth": "tooth",
    "geese": "goose",
    "mice": "mouse",
    "oxen": "ox",
    "indices": "index",
    "matrices": "matrix",
    "vertices": "vertex",
    "analyses": "analysis",
    "crises": "crisis",
    "theses": "thesis",
    "phenomena": "phenomenon",
    "criteria": "criterion",
    "data": "datum",
    "media": "medium",
}


def uid_to_endpoint(uid: str) -> str:
    """Convert content type UID to API endpoint.

    Handles common English pluralization patterns. For custom pluralization
    (e.g., "person" -> "people"), use the schema's plural_name instead.

    Args:
        uid: Content type UID (e.g., "api::article.article", "api::blog.post")

    Returns:
        API endpoint (e.g., "articles", "posts")

    Examples:
        >>> uid_to_endpoint("api::article.article")
        'articles'
        >>> uid_to_endpoint("api::category.category")
        'categories'
        >>> uid_to_endpoint("api::class.class")
        'classes'
        >>> uid_to_endpoint("api::blog.post")
        'posts'
    """
    # Extract the model name (after the dot) and pluralize it
    # For "api::blog.post", we want "post" -> "posts", not "blog" -> "blogs"
    parts = uid.split("::")
    if len(parts) == 2:
        api_model = parts[1]
        # Get model name (after the dot if present)
        if "." in api_model:
            name = api_model.split(".")[1]
        else:
            name = api_model
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


def api_id_to_singular(api_id: str) -> str:
    """Convert plural API ID to singular form.

    Handles common English pluralization patterns and irregular plurals.
    For custom pluralization, you may need to handle edge cases manually.

    Args:
        api_id: Plural API ID (e.g., "articles", "categories", "people")

    Returns:
        Singular form (e.g., "article", "category", "person")

    Examples:
        >>> api_id_to_singular("articles")
        'article'
        >>> api_id_to_singular("categories")
        'category'
        >>> api_id_to_singular("classes")
        'class'
        >>> api_id_to_singular("people")
        'person'
        >>> api_id_to_singular("children")
        'child'
    """
    # Normalize to lowercase for comparison
    name = api_id.lower()

    # Check irregular plurals first
    if name in _IRREGULAR_PLURALS:
        return _IRREGULAR_PLURALS[name]

    # Handle -ies -> -y (categories -> category)
    if name.endswith("ies"):
        return name[:-3] + "y"

    # Handle -zzes specifically
    # Words with single z double it when pluralized: quiz -> quizzes (remove -zes, keep 1 z)
    # Words with double z just add es: buzz -> buzzes, fizz -> fizzes (remove -es, keep zz)
    if name.endswith("zzes"):
        # Common double-z words: buzz, fizz, fuzz, jazz, razz, etc. (pattern: consonant + vowel + zz)
        # Common single-z words that double: quiz, whiz (pattern: vowel + i + z or similar)
        # Heuristic: 4-letter bases (buzz, fizz, jazz, fuzz) become 6-letter plurals
        #            4-letter bases like quiz become 7-letter plurals
        # So length 6 -> likely double-z base (remove -es)
        #    length 7+ -> likely single-z base that was doubled (remove -zes)
        if len(name) <= 6:
            return name[:-2]  # buzzes -> buzz, fizzes -> fizz
        else:
            return name[:-3]  # quizzes -> quiz, whizzes -> whiz

    # Handle -es for words ending in s, x, z, ch, sh (classes -> class, buses -> bus)
    if name.endswith("es"):
        base = name[:-2]
        if base.endswith(("s", "x", "z", "ch", "sh")):
            return base

    # Handle standard -s removal (articles -> article)
    if name.endswith("s") and len(name) > 1:
        return name[:-1]

    # Already singular or unrecognized
    return name


def uid_to_admin_url(
    uid: str,
    base_url: str,
    kind: str = "collectionType",
) -> str:
    """Build Strapi admin panel URL from content type UID.

    Args:
        uid: Content type UID (e.g., "api::article.article")
        base_url: Strapi base URL (e.g., "http://localhost:1337")
        kind: Content type kind - "collectionType" or "singleType"

    Returns:
        Admin panel URL for the content type

    Examples:
        >>> uid_to_admin_url("api::article.article", "http://localhost:1337")
        'http://localhost:1337/admin/content-manager/collection-types/api::article.article'

        >>> uid_to_admin_url(
        ...     "api::homepage.homepage",
        ...     "http://localhost:1337",
        ...     kind="singleType"
        ... )
        'http://localhost:1337/admin/content-manager/single-types/api::homepage.homepage'
    """
    # Remove trailing slash from base_url
    base_url = base_url.rstrip("/")

    # Determine the path segment based on kind
    if kind == "singleType":
        type_segment = "single-types"
    else:
        type_segment = "collection-types"

    return f"{base_url}/admin/content-manager/{type_segment}/{uid}"


# Alias for clarity - uid_to_endpoint already exists, this makes the intent explicit
uid_to_api_id = uid_to_endpoint
