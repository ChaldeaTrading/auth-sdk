from types import SimpleNamespace

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from auth_sdk import AuthConfig, Claims, require_user


def make_app():
    app = FastAPI()
    dependency = require_user(AuthConfig(issuer="https://issuer", jwks_url="https://issuer/certs", audience="api", allowed_user_clients={"portal"}))

    @app.get("/")
    def root(claims: Claims = Depends(dependency)):
        return {"sub": claims.sub}

    return app, dependency


def test_missing_or_invalid_authorization_returns_401():
    app, _ = make_app()
    client = TestClient(app)
    for headers in ({}, {"Authorization": "Bearer invalid"}, {"Authorization": "Basic secret"}):
        result = client.get("/", headers=headers)
        assert result.status_code == 401
        assert result.headers["www-authenticate"] == "Bearer"
        assert result.json() == {"detail": "unauthorized"}


def test_dependency_overrides_supported():
    app, dependency = make_app()
    app.dependency_overrides[dependency] = lambda: Claims("overridden", {})
    result = TestClient(app).get("/")
    assert result.status_code == 200
    assert result.json() == {"sub": "overridden"}


def test_valid_token_returns_claims(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr("jwt.PyJWKClient.get_signing_key_from_jwt", lambda self, token: SimpleNamespace(key=key.public_key()))
    token = jwt.encode(
        {"sub": "user", "iss": "https://issuer", "aud": "api", "azp": "portal", "exp": 4102444800},
        key, algorithm="RS256", headers={"kid": "test"},
    )
    app, _ = make_app()
    result = TestClient(app).get("/", headers={"Authorization": "Bearer " + token})
    assert result.status_code == 200
    assert result.json() == {"sub": "user"}
