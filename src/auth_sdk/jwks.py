from functools import lru_cache

from jwt import PyJWKClient


@lru_cache(maxsize=16)
def get_jwks_client(url: str) -> PyJWKClient:
    """Return a cached JWKS client; PyJWT refreshes keys when kid is unknown."""
    return PyJWKClient(url)
