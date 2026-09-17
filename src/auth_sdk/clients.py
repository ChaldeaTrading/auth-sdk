"""Small, fail-closed HTTP clients for actual platform authentication flows."""
import asyncio
import math
import re
import threading
import time
from urllib.parse import urlsplit

import httpx

from .core import extract_bearer
from .errors import AuthError, ConfigurationError, DependencyUnavailable, PermissionDenied


def _url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
        if (not isinstance(value, str) or not parsed.hostname or port == 0
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or "?" in value or "#" in value
                or "\\" in value or any(c.isspace() for c in value)
                or not (parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}))):
            raise ValueError
    except (TypeError, ValueError, AttributeError):
        raise ConfigurationError("invalid authentication endpoint") from None
    return value.rstrip("/")


def _timeout(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ConfigurationError("invalid authentication timeout")
    return value


def _origin(value: str) -> tuple[str, str, int]:
    parsed = urlsplit(_url(value))
    return parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)


class ServiceTokenProvider:
    """One client identity, a bounded token request, and an in-memory cache.

    Only use confidential clients with user login grants disabled. Secrets and
    token responses are deliberately excluded from repr and error messages.
    """

    def __init__(self, token_url: str, client_id: str, client_secret: str, timeout: float = 5,
                 *, transport: httpx.BaseTransport | None = None):
        self.token_url = _url(token_url)
        if any(not isinstance(v, str) or not v.strip() for v in (client_id, client_secret)):
            raise ConfigurationError("service credentials required")
        self._client_id = client_id
        self._client_secret = client_secret
        self.timeout = _timeout(timeout)
        self._transport = transport
        self._lock = threading.Lock()
        self._token = ""
        self._refresh_at = 0.0

    def get_token(self) -> str:
        # One lock per client identity also coalesces sync and async refreshes.
        with self._lock:
            started = time.monotonic()
            if self._token and started < self._refresh_at:
                return self._token
            self._token = ""
            try:
                with httpx.Client(timeout=self.timeout, follow_redirects=False, trust_env=False,
                                  transport=self._transport) as client:
                    response = client.post(self.token_url, data={
                        "grant_type": "client_credentials", "client_id": self._client_id,
                        "client_secret": self._client_secret,
                    })
                if response.status_code != 200:
                    raise ValueError
                data = response.json()
                token, kind, expires = data.get("access_token"), data.get("token_type"), data.get("expires_in")
                if (not isinstance(token, str) or not token or not token.isascii()
                        or any(c.isspace() or ord(c) < 33 or ord(c) == 127 for c in token)
                        or not isinstance(kind, str) or kind.lower() != "bearer"
                        or isinstance(expires, bool) or not isinstance(expires, (int, float))
                        or not math.isfinite(expires) or expires <= 0):
                    raise ValueError
                refresh_at = started + expires - min(30.0, expires * .1)
                if time.monotonic() >= refresh_at:
                    raise ValueError
            except Exception:
                raise DependencyUnavailable("service token unavailable") from None
            self._token, self._refresh_at = token, refresh_at
            return token

    async def aget_token(self) -> str:
        return await asyncio.to_thread(self.get_token)

    def auth(self, *, allowed_origins: set[str]) -> httpx.Auth:
        """Bind bearer injection to explicit target origins."""
        return _ServiceAuth(self, allowed_origins)


class _ServiceAuth(httpx.Auth):
    def __init__(self, provider: ServiceTokenProvider, origins: set[str]):
        if not isinstance(origins, (set, frozenset, list, tuple)) or not origins:
            raise ConfigurationError("service target origins required")
        self._provider = provider
        self._origins = {_origin(value) for value in origins}

    def _check(self, request: httpx.Request) -> None:
        # URLs can have request query parameters; these never affect origin binding.
        origin = _origin(str(request.url.copy_with(query=None, fragment=None)))
        if origin not in self._origins:
            raise ConfigurationError("untrusted service target")

    def sync_auth_flow(self, request):
        self._check(request)
        request.headers["Authorization"] = "Bearer " + self._provider.get_token()
        yield request

    async def async_auth_flow(self, request):
        self._check(request)
        request.headers["Authorization"] = "Bearer " + await self._provider.aget_token()
        yield request


class PermissionClient:
    """Forward the original user bearer token; only a strict boolean allows."""

    def __init__(self, base_url: str, timeout: float = 5, *, transport: httpx.BaseTransport | None = None):
        self.base_url = _url(base_url)
        self.timeout = _timeout(timeout)
        self._transport = transport

    def authorize(self, authorization: str | None, resource_type: str, action: str) -> bool:
        token = extract_bearer(authorization)
        if any(not isinstance(v, str) or not re.fullmatch(r"[a-z0-9_-]{1,64}", v) for v in (resource_type, action)):
            raise ConfigurationError("invalid permission request")
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=False, trust_env=False,
                              transport=self._transport) as client:
                response = client.post(self.base_url + "/permission-center/v1/authorize",
                                       headers={"Authorization": "Bearer " + token},
                                       json={"resource_type": resource_type, "action": action})
            if response.status_code == 401:
                raise AuthError("invalid user token")
            if response.status_code == 403:
                raise PermissionDenied("user permission denied")
            if response.status_code != 200:
                raise ValueError
            body = response.json()
            if not isinstance(body, dict) or type(body.get("allow")) is not bool:
                raise ValueError
            return body["allow"]
        except (AuthError, PermissionDenied):
            raise
        except Exception:
            raise DependencyUnavailable("permission service unavailable") from None

    async def aauthorize(self, authorization: str | None, resource_type: str, action: str) -> bool:
        return await asyncio.to_thread(self.authorize, authorization, resource_type, action)
