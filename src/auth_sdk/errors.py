class AuthError(Exception):
    """Raised when a bearer token cannot be authenticated."""


class ConfigurationError(AuthError):
    """Raised when authentication configuration is incomplete."""
