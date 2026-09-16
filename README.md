# auth-sdk-python

`auth-sdk` is a Python backend authentication package for services using
Keycloak. Version `0.1.0` supports Python 3.11/3.12 and provides
framework-independent JWT verification and an optional FastAPI adapter.

## Install

Configure pip to use your private Python registry, then install a fixed version:

```bash
python -m pip install 'auth-sdk==0.1.0'
# For FastAPI applications:
python -m pip install 'auth-sdk[fastapi]==0.1.0'
```

Use the private registry's `/simple/` index endpoint for installation, which may
differ from its upload URL. The index must also provide or proxy public
dependencies. Supply registry credentials through your secret manager or a
private pip configuration file; do not commit them. See the consumers' Docker
instructions for mounting pip configuration with BuildKit secrets.

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

Update the version in `pyproject.toml`, run the test suite and build checks, then
create a matching `auth-sdk-python-v<version>` tag. Publishing requires an HTTPS
private PyPI-compatible upload endpoint and externally supplied credentials.
The shared `scripts/validate_release.py` checks the tag against the package
version, rejects public PyPI endpoints and URL-embedded credentials, and reports
configuration errors without including secrets. Configure the registry to
prohibit replacing an existing version.

The repository's CodeCommit origin uses `buildspec.yml`. Configure a CodeBuild
project with this repository as its source, an image supporting Python 3.12,
and an artifact destination. Its ordinary builds test PyJWT 2.8, 2.10.0 (issuer
regression coverage), and the latest release, build and check wheel/sdist files,
and expose `dist/` as artifacts.
Publishing is disabled when `RELEASE_TAG` is empty.

For a release, start CodeBuild with its source version set to
`auth-sdk-python-v<version>` and set `RELEASE_TAG` to the same tag. The validator
also accepts a source version of `refs/tags/<tag>`; a branch or commit checkout
cannot publish merely by setting `RELEASE_TAG`. Configure
`TWINE_REPOSITORY_URL` as the private upload URL and inject `TWINE_USERNAME` /
`TWINE_PASSWORD` through CodeBuild's Secrets Manager or Parameter Store
environment settings. Do not put credentials in the buildspec or use plaintext
start-build overrides for secrets. The CodeBuild project, CodeCommit source
connection/triggers, artifact destination, registry, secret mappings and IAM
access still require external configuration; adding the buildspec creates none
of those resources and does not publish a release.

If the repository is mirrored to GitHub, `.github/workflows/publish.yml` provides
the equivalent release path and a Python 3.11/3.12 test matrix. Its
`python-packages` environment needs variable `PYTHON_PACKAGE_UPLOAD_URL` and
secrets `PYTHON_PACKAGE_USERNAME` / `PYTHON_PACKAGE_PASSWORD`. Both CI paths use
the upload URL, which may differ from the registry's pip `/simple/` index URL.

To build and validate the first release locally:

```bash
python -m pip install build twine
python -m build
python -m twine check dist/*
python -m pip install dist/auth_sdk-0.1.0-py3-none-any.whl
```

Building a local wheel does not publish it. Consumers must update their exact
version pins together with each SDK release.
