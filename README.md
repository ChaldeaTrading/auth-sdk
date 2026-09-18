# auth-sdk-python

`auth-sdk` is a Python backend authentication package for services using
Keycloak. Version `0.1.0` supports Python 3.11/3.12 and provides
framework-independent JWT verification and an optional FastAPI adapter.

## Install

Install the package from PyPI. Pin an exact version in applications and deployment
artifacts:

```bash
python -m pip install 'auth-sdk==0.1.0'
# For FastAPI applications:
python -m pip install 'auth-sdk[fastapi]==0.1.0'
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
checks and administrator authorization. Outgoing service credentials and the
permission-center HTTP client are outside version 0.1.0.

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
git tag auth-sdk-python-v0.1.0
git push origin auth-sdk-python-v0.1.0
```

`.github/workflows/publish.yml` tests Python 3.11/3.12 and supported PyJWT
versions, builds the sdist and wheel once, installs each distribution in a clean
job, and publishes the same artifacts through PyPI Trusted Publishing. The
`pypi` GitHub environment and the PyPI Trusted Publisher must both identify
`ChaldeaTrading/auth-sdk`, `.github/workflows/publish.yml`, and environment
`pypi`. The publish job uses a short-lived OIDC identity and needs no PyPI API
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
python -m pip install dist/auth_sdk-0.1.0-py3-none-any.whl
```

Building a local wheel does not publish it. Consumers must update their exact
version pins together with each SDK release.

## License

Licensed under the [Apache License 2.0](LICENSE).
