"""Service account validation; role policies belong to the receiving API."""
from dataclasses import dataclass, field

from .core import AuthConfig, Claims, verify_token
from .errors import ConfigurationError, PermissionDenied


@dataclass(frozen=True)
class ServiceAuthConfig:
    issuer: str
    jwks_url: str
    audience: str
    allowed_service_clients: frozenset[str]
    required_roles: frozenset[str] = field(default_factory=frozenset)
    algorithms: tuple[str, ...] = ("RS256",)

    def __post_init__(self) -> None:
        if not isinstance(self.audience, str) or not self.audience.strip():
            raise ConfigurationError("service audience required")
        AuthConfig(self.issuer, self.jwks_url, self.audience, self.allowed_service_clients, self.algorithms)
        if (not isinstance(self.required_roles, (set, frozenset, tuple, list))
                or any(not isinstance(role, str) or not role.strip() for role in self.required_roles)):
            raise ConfigurationError("invalid service roles")
        object.__setattr__(self, "allowed_service_clients", frozenset(self.allowed_service_clients))
        object.__setattr__(self, "required_roles", frozenset(self.required_roles))


def verify_service_token(value: str | None, config: ServiceAuthConfig) -> Claims:
    """Verify an access token from an exclusively service-account client."""
    claims = verify_token(value, AuthConfig(
        config.issuer, config.jwks_url, config.audience,
        config.allowed_service_clients, config.algorithms,
    ))
    access = claims.payload.get("resource_access")
    resource = access.get(config.audience) if isinstance(access, dict) else None
    roles = resource.get("roles") if isinstance(resource, dict) else None
    if config.required_roles and (
        not isinstance(roles, list) or any(not isinstance(role, str) for role in roles)
        or not config.required_roles.issubset(roles)
    ):
        raise PermissionDenied("service permission denied")
    return claims
