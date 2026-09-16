from collections.abc import Callable

from .core import AuthConfig, Claims, verify_token
from .errors import AuthError


def require_user(config: AuthConfig) -> Callable:
    """Build a FastAPI dependency that authenticates the request bearer token."""
    try:
        from fastapi import Header, HTTPException
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("FastAPI is required for require_user") from exc

    def dependency(authorization: str | None = Header(default=None)) -> Claims:
        try:
            return verify_token(authorization, config)
        except AuthError as exc:
            raise HTTPException(
                status_code=401,
                detail="unauthorized",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    return dependency
