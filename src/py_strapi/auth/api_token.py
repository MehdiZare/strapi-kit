"""API Token authentication for Strapi.

This module provides bearer token authentication for Strapi API requests.
"""



class APITokenAuth:
    """API Token authentication handler.

    Manages bearer token authentication for Strapi API requests.
    Tokens can be created in Strapi admin panel under Settings > API Tokens.

    Example:
        ```python
        auth = APITokenAuth("your-api-token")
        headers = auth.get_headers()
        # {"Authorization": "Bearer your-api-token"}
        ```
    """

    def __init__(self, token: str) -> None:
        """Initialize API token authentication.

        Args:
            token: The API token from Strapi
        """
        self.token = token

    def get_headers(self) -> dict[str, str]:
        """Get authentication headers for requests.

        Returns:
            Dictionary with Authorization header
        """
        return {"Authorization": f"Bearer {self.token}"}

    def validate_token(self) -> bool:
        """Validate that the token is not empty.

        Returns:
            True if token is valid (non-empty), False otherwise
        """
        return bool(self.token and self.token.strip())

    def __repr__(self) -> str:
        """Return string representation (token masked for security)."""
        masked = f"{self.token[:4]}...{self.token[-4:]}" if len(self.token) > 8 else "****"
        return f"APITokenAuth(token={masked})"
