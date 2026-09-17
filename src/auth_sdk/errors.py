class AuthError(Exception):
    """Raised when a bearer token cannot be authenticated."""


class ConfigurationError(AuthError):
    """Raised when authentication configuration is incomplete."""


class PermissionDenied(AuthError):
    """An authenticated principal lacks the required permission (HTTP 403)."""


class DependencyUnavailable(Exception):
    """An authentication/authorization dependency failed (HTTP 503)."""
