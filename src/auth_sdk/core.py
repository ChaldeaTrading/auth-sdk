from dataclasses import dataclass, field
from typing import Any

import jwt

from .errors import AuthError, ConfigurationError
from .jwks import get_jwks_client


@dataclass(frozen=True)
class AuthConfig:
    """Trusted issuer, audience and client allowlist for one API."""

    issuer: str
    jwks_url: str
    audience: str | tuple[str, ...]
    allowed_user_clients: frozenset[str] = field(default_factory=frozenset)
    algorithms: tuple[str, ...] = ("RS256",)

    def __post_init__(self) -> None:
        if not all(isinstance(value, str) and value.strip() for value in (self.issuer, self.jwks_url)):
            raise ConfigurationError("authentication configuration missing")
        if not (
            isinstance(self.audience, str) and self.audience.strip()
            or isinstance(self.audience, tuple) and self.audience and all(isinstance(item, str) and item.strip() for item in self.audience)
        ):
            raise ConfigurationError("authentication audience missing")
        if (
            isinstance(self.allowed_user_clients, str)
            or not isinstance(self.allowed_user_clients, (set, frozenset, tuple, list))
            or not self.allowed_user_clients
            or any(
                not isinstance(client, str) or not client.strip()
                for client in self.allowed_user_clients
            )
        ):
            raise ConfigurationError("allowed user clients required")
        if not isinstance(self.algorithms, tuple) or tuple(self.algorithms) != ("RS256",):
            raise ConfigurationError("only RS256 is supported")
        object.__setattr__(self, "allowed_user_clients", frozenset(self.allowed_user_clients))
        object.__setattr__(self, "algorithms", tuple(self.algorithms))


@dataclass(frozen=True)
class Claims:
    """Verified identity; values are omitted from repr to avoid accidental logging."""

    sub: str = field(repr=False)
    payload: dict[str, Any] = field(repr=False)


def extract_bearer(value: str | None) -> str:
    """Extract a token from an HTTP Authorization header."""
    parts = (value or "").split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise AuthError("invalid bearer token")
    return parts[1]


def verify_token(value: str | None, config: AuthConfig) -> Claims:
    """Authenticate a bearer access token or raise a sanitized AuthError."""
    token = extract_bearer(value)
    try:
        header = jwt.get_unverified_header(token)
        token_type = header.get("typ")
        if isinstance(token_type, str) and token_type.upper() == "ID":
            raise AuthError("access token required")
        if header.get("alg") not in config.algorithms:
            raise AuthError("invalid algorithm")
        key = get_jwks_client(config.jwks_url).get_signing_key_from_jwt(token).key
        payload = jwt.decode(
            token,
            key,
            algorithms=list(config.algorithms),
            audience=config.audience,
            issuer=config.issuer,
            options={"require": ["exp", "sub"]},
        )
    except AuthError:
        raise
    except Exception:
        raise AuthError("invalid token") from None

    # Enforce exact equality even on PyJWT releases with permissive issuer checks.
    if payload.get("iss") != config.issuer:
        raise AuthError("invalid issuer")
    payload_type = payload.get("typ")
    if (
        isinstance(payload_type, str) and payload_type.upper() == "ID"
        or payload.get("nonce") is not None
    ):
        raise AuthError("access token required")
    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        raise AuthError("missing subject")
    client = payload.get("azp")
    if not isinstance(client, str) or client not in config.allowed_user_clients:
        raise AuthError("invalid user client")
    return Claims(sub=sub, payload=dict(payload))
