from .core import AuthConfig, Claims, extract_bearer, verify_token
from .errors import AuthError, ConfigurationError, DependencyUnavailable, PermissionDenied
from .service import ServiceAuthConfig, verify_service_token
from .clients import PermissionClient, ServiceTokenProvider, ShopScope
from .fastapi import require_user

__all__ = [
    "AuthConfig",
    "ServiceAuthConfig",
    "verify_service_token",
    "PermissionClient",
    "ShopScope",
    "ServiceTokenProvider",
    "PermissionDenied",
    "DependencyUnavailable",
    "Claims",
    "AuthError",
    "ConfigurationError",
    "extract_bearer",
    "verify_token",
    "require_user",
]
