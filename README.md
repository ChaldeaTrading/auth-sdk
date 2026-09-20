# ChaldeaTrading Auth SDK

`chaldeatrading-auth-sdk` is a Python backend authentication package for services using
Keycloak. Version `0.2.0` supports Python 3.11/3.12 and provides
framework-independent JWT verification and an optional FastAPI adapter.

## Local wheel build (current integration)

Build one versioned artifact and pass that exact artifact into every consumer:

```bash
python scripts/build_wheel.py
# Record the printed AUTH_SDK_WHEEL_SHA256 value for this release.
python scripts/validate_wheel.py dist/0.2.0/chaldeatrading_auth_sdk-0.2.0-py3-none-any.whl \
  --version 0.2.0 --sha256 "$AUTH_SDK_WHEEL_SHA256"
python -m pip install dist/0.2.0/chaldeatrading_auth_sdk-0.2.0-py3-none-any.whl
```

`AUTH_SDK_WHEEL_SHA256` is the expected checksum recorded for the release.
Container publishers take a named BuildKit context `auth-sdk-wheel` containing
that wheel and `validate_wheel.py`, plus `AUTH_SDK_WHEEL_SHA256` as a build argument.
They validate metadata and digest, install the explicit wheel, and install the
application's normal dependencies with `chaldeatrading-auth-sdk==0.2.0` pinned. Missing or
mismatched artifacts fail the build. No registry or publishing credentials are
needed for this mode. Keep wheel version and checksum in the release record;
future GitHub hosting does not change the artifact validation contract.

## PyPI installation

Install the package from PyPI. Pin an exact version in applications and deployment
artifacts:

```bash
python -m pip install 'chaldeatrading-auth-sdk==0.2.0'
# For FastAPI applications:
python -m pip install 'chaldeatrading-auth-sdk[fastapi]==0.2.0'
```

## Local development

```bash
python -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest -q
```

## Usage

```python
from auth_sdk import AuthConfig, AuthError, verify_token

config = AuthConfig(
    issuer="https://auth.example/realms/example",
    jwks_url="https://auth.example/realms/example/protocol/openid-connect/certs",
    audience="permission-center-api",
    allowed_user_clients={"unified-portal"},
)
claims = verify_token(request.headers.get("Authorization"), config)
# claims.sub: verified subject; claims.payload: complete verified JWT payload.
# Catch AuthError at your framework boundary and return an authentication error.
```

The package validates an RS256 signature, issuer, audience, expiry, subject,
access-token type, and trusted `azp`. Both `exp` and a nonempty string `sub` are
required. ID token types in either the header or verified payload (`typ=ID`,
case-insensitive) and tokens with a non-null `nonce` are rejected. The verified
issuer must exactly match the configured issuer across supported PyJWT versions.
Invalid configuration raises `ConfigurationError`, an
`AuthError` subclass. Error messages omit token contents and dependency details;
`Claims` hides its fields from `repr`, but its payload still contains sensitive
data and must not be logged.

JWKS clients are cached per URL in process, with PyJWT's five-minute JWKS cache
and 30-second network timeout. An unknown `kid` triggers refresh when PyJWT's
refresh cooldown permits it (30 seconds in PyJWT 2.14). If a usable key cannot
be obtained, verification fails. Cached keys remain usable until cache expiry;
an unavailable endpoint cannot extend the cache lifetime. Keycloak rotations
should publish new public keys before issuing tokens signed by them.

## FastAPI

```python
from fastapi import Depends, FastAPI
from auth_sdk import Claims, require_user

app = FastAPI()
current_user = require_user(config)

@app.get("/me")
def me(claims: Claims = Depends(current_user)):
    return {"sub": claims.sub}
```

Missing or invalid credentials return HTTP 401 with `WWW-Authenticate: Bearer`.
The dependency runs synchronous verification in FastAPI's worker threadpool.
Tests can override `current_user` through `app.dependency_overrides`. Importing
the core package does not require or load FastAPI. In other async frameworks,
run `verify_token` in a worker thread because JWKS retrieval performs blocking IO.

The SDK does not query application databases, decide resource ownership, or
filter business data. Those rules remain in each service. Directory identifiers
such as `feishu_union_id` are optional claims; Permission Center checks them only
when required by its own routes. Permission Center also retains service-role
checks and administrator authorization. Service credentials and Permission Center calls are supported in version 0.2.0
using the clients below; resource ownership remains a business concern.

## Release

Releases follow the standard Python packaging flow: the source tree and
`pyproject.toml` are built into both an sdist and a wheel, the distributions are
checked and installed in clean CI environments, and the verified artifacts are
published to PyPI.

Update the version in `pyproject.toml`, run the test and build checks, then create
a matching `auth-sdk-python-v<version>` tag:

```bash
python -m pytest -q
python -m build
python -m twine check dist/*
git tag auth-sdk-python-v0.2.0
git push origin auth-sdk-python-v0.2.0
```

`.github/workflows/publish.yml` tests Python 3.11/3.12 and supported PyJWT
versions, builds the sdist and wheel once, installs each distribution in a clean
job, and publishes the same artifacts through PyPI Trusted Publishing. The
`pypi` GitHub environment and the PyPI Trusted Publisher must both identify
`ChaldeaTrading/auth-sdk`, `.github/workflows/publish.yml`, and environment
`pypi`, with PyPI project name `chaldeatrading-auth-sdk`. The publish job uses a short-lived OIDC identity and needs no PyPI API
token in GitHub secrets. PyPI releases are immutable, so every release needs a
new version.

The repository's CodeCommit origin uses `buildspec.yml`. Configure a CodeBuild
project with this repository as its source, an image supporting Python 3.12,
and an artifact destination. Its ordinary builds test PyJWT 2.8, 2.10.0 (issuer
regression coverage), and the latest release, build and check wheel/sdist files,
and expose `dist/` as artifacts.
CodeBuild does not publish; GitHub Actions is the only release path.

To build and validate the first release locally:

```bash
python -m pip install build twine
python -m build
python -m twine check dist/*
python -m pip install dist/chaldeatrading_auth_sdk-0.2.0-py3-none-any.whl
```

Building a local wheel does not publish it. Consumers must update their exact
version pins together with each SDK release.

## Service APIs and outbound calls

```python
from auth_sdk import ServiceAuthConfig, verify_service_token

service_config = ServiceAuthConfig(
    issuer=issuer, jwks_url=jwks_url, audience="tool-gateway-api",
    allowed_service_clients={"shop-rag"}, required_roles={"product:read"},
)
claims = verify_service_token(authorization, service_config)
```

The target role list must contain **all** configured required roles. Service
clients must be exclusive confidential clients with user grants disabled in
Keycloak, and must never appear in user client allowlists. A valid token with
missing roles raises `PermissionDenied` (403); an invalid token raises
`AuthError` (401). Configuration failure must block startup or return 503.
Catch `PermissionDenied` before `AuthError` because it is a subclass.

```python
import httpx
from auth_sdk import PermissionClient, ServiceTokenProvider

permissions = PermissionClient("https://permission.test.example")
allowed = await permissions.aauthorize(user_authorization, "shop-rag", "admin")
# Only allowed is True permits the business operation.

provider = ServiceTokenProvider(token_url, client_id, client_secret)
async with httpx.AsyncClient(
    base_url=target_url,
    auth=provider.auth(allowed_origins={target_url}),
    follow_redirects=False, timeout=10,
) as client:
    response = await client.get("/api/v1/tool/shop/list")
```

Reuse the provider per configured client identity. Cache refreshes are coalesced
across threads and asynchronous tasks; failures never reuse an expired token.
Origins are validated before fetching or attaching credentials. Without explicit
`allowed_origins`, auth construction fails. Keep redirect following disabled.
Permission and token endpoints require HTTPS, with
HTTP allowed only for loopback development. `DependencyUnavailable` maps to
503, and contains no upstream body, token or secret. The SDK never retries a
business request or replays a non-idempotent write.

## License

Licensed under the [Apache License 2.0](LICENSE).
