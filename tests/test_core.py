import json
import subprocess
import sys
from dataclasses import replace
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import URLError

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from auth_sdk import AuthConfig, AuthError, Claims, ConfigurationError, extract_bearer, verify_token
from auth_sdk.jwks import get_jwks_client


@pytest.fixture(scope="session")
def private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def config():
    return AuthConfig(
        issuer="https://issuer", jwks_url="https://issuer/certs",
        audience="api", allowed_user_clients={"portal"},
    )


@pytest.fixture
def payload():
    return {"sub": "u1", "iss": "https://issuer", "aud": "api", "azp": "portal", "exp": 4102444800}


@pytest.fixture
def signed(private_key, payload):
    def token(updates=None, *, missing=(), headers=None, key=None, algorithm="RS256"):
        claims = {**payload, **(updates or {})}
        for claim in missing:
            claims.pop(claim, None)
        return "Bearer " + jwt.encode(claims, private_key if key is None else key, algorithm=algorithm, headers={"kid": "k1", **(headers or {})})
    return token


@pytest.fixture(autouse=True)
def clear_cache():
    get_jwks_client.cache_clear()
    yield
    get_jwks_client.cache_clear()


@pytest.fixture
def key_lookup(private_key):
    with patch("jwt.PyJWKClient.get_signing_key_from_jwt", return_value=SimpleNamespace(key=private_key.public_key())) as lookup:
        yield lookup


@pytest.mark.parametrize("value", [None, "", "Basic abc", "Bearer", "Bearer a b"])
def test_invalid_bearer(value):
    with pytest.raises(AuthError):
        extract_bearer(value)


@pytest.mark.parametrize("value", ["Bearer abc", "bearer abc", "BEARER abc", " Bearer  abc "])
def test_extract_bearer(value):
    assert extract_bearer(value) == "abc"


def test_valid_token(config, payload, signed, key_lookup):
    claims = verify_token(signed(), config)
    assert isinstance(claims, Claims)
    assert claims.sub == "u1"
    assert claims.payload == payload


@pytest.mark.parametrize("changes", [
    {"exp": 1}, {"exp": None}, {"sub": ""}, {"sub": 1}, {"iss": "other"},
    {"aud": "other"}, {"azp": "unknown"}, {"azp": None}, {"azp": []},
    {"nonce": "n"}, {"nbf": 4102444800},
])
def test_invalid_claims(changes, config, signed, key_lookup):
    with pytest.raises(AuthError):
        verify_token(signed(changes), config)


@pytest.mark.parametrize("claim", ["exp", "sub", "iss", "aud", "azp"])
def test_missing_claim(claim, config, signed, key_lookup):
    with pytest.raises(AuthError):
        verify_token(signed(missing=(claim,)), config)


def test_valid_audience_array(config, signed, key_lookup):
    assert verify_token(signed({"aud": ["other", "api"]}), config).sub == "u1"


def test_keycloak_bearer_payload_is_accepted(config, signed, key_lookup):
    assert verify_token(signed({"typ": "Bearer"}), config).sub == "u1"


@pytest.mark.parametrize("headers", [{"typ": "ID"}, {"typ": "id"}, {"typ": "Id"}])
def test_reject_id_header(headers, config, signed, key_lookup):
    with pytest.raises(AuthError):
        verify_token(signed(headers=headers), config)
    key_lookup.assert_not_called()


@pytest.mark.parametrize("token_type", ["ID", "id", "Id"])
def test_reject_id_payload(token_type, config, signed, key_lookup):
    with pytest.raises(AuthError):
        verify_token(signed({"typ": token_type}), config)


def test_issuer_must_equal_the_whole_configured_url(config, signed, key_lookup):
    with pytest.raises(AuthError):
        verify_token(signed({"iss": "issuer"}), config)


def test_reject_wrong_signature(config, signed, key_lookup):
    wrong = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(AuthError):
        verify_token(signed(key=wrong), config)


def test_reject_unsigned_token_before_key_fetch(config, signed, key_lookup):
    with pytest.raises(AuthError):
        verify_token(signed(algorithm="none", key=""), config)
    key_lookup.assert_not_called()


def test_reject_wrong_algorithm_before_key_fetch(config, payload, key_lookup):
    token = jwt.encode(payload, "x" * 32, algorithm="HS256")
    with pytest.raises(AuthError):
        verify_token("Bearer " + token, config)
    key_lookup.assert_not_called()


@pytest.mark.parametrize("value", ["Bearer not-a-jwt", "Bearer ..", "Bearer a.b.c"])
def test_malformed_token(value, config):
    with pytest.raises(AuthError):
        verify_token(value, config)


@pytest.mark.parametrize("updates", [
    {"issuer": ""}, {"jwks_url": ""}, {"audience": ""},
    {"issuer": 1}, {"jwks_url": None}, {"audience": ("api", 1)},
    {"audience": ("",)}, {"audience": ()},
    {"allowed_user_clients": set()}, {"allowed_user_clients": {""}},
    {"allowed_user_clients": "portal"}, {"allowed_user_clients": None},
    {"allowed_user_clients": 1}, {"allowed_user_clients": {1}},
    {"algorithms": None}, {"algorithms": ()}, {"algorithms": ("HS256",)},
])
def test_invalid_config(updates, config):
    with pytest.raises(ConfigurationError):
        replace(config, **updates)


def test_normalize_config(config):
    assert config.allowed_user_clients == frozenset({"portal"})
    assert isinstance(config.allowed_user_clients, frozenset)


def test_claims_repr_is_sanitized():
    claims = Claims("sensitive-subject", {"email": "secret@example.com"})
    assert "sensitive" not in repr(claims)
    assert "secret" not in repr(claims)


def test_error_does_not_leak_dependency_error(config, signed):
    with patch("jwt.PyJWKClient.get_signing_key_from_jwt", side_effect=ValueError("secret token")):
        with pytest.raises(AuthError) as caught:
            verify_token(signed(), config)
    assert "secret" not in str(caught.value)
    assert caught.value.__suppress_context__


def jwks_document(key, kid):
    public = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    return {"keys": [{**public, "kid": kid, "use": "sig", "alg": "RS256"}]}


def response(data):
    return BytesIO(json.dumps(data).encode())


def test_jwks_cache(config, signed, private_key):
    with patch("urllib.request.OpenerDirector.open", return_value=response(jwks_document(private_key, "k1"))) as request:
        assert verify_token(signed(), config).sub == "u1"
        assert verify_token(signed(), config).sub == "u1"
    assert request.call_count == 1


def test_unknown_kid_refreshes_keys(config, signed, private_key):
    rotated = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rotated_started = False
    with patch("urllib.request.OpenerDirector.open", side_effect=[response(jwks_document(private_key, "k1")), response(jwks_document(rotated, "k2"))]) as request, patch("time.monotonic", side_effect=lambda: (request.call_count + int(rotated_started)) * 31):
        assert verify_token(signed(), config).sub == "u1"
        rotated_started = True
        assert verify_token(signed(key=rotated, headers={"kid": "k2"}), config).sub == "u1"
    assert request.call_count == 2


def test_unknown_kid_after_refresh_is_rejected(config, signed, private_key):
    with patch("urllib.request.OpenerDirector.open", side_effect=lambda *a, **k: response(jwks_document(private_key, "k1"))):
        with pytest.raises(AuthError):
            verify_token(signed(headers={"kid": "missing"}), config)


def test_jwks_unavailable(config, signed):
    with patch("urllib.request.OpenerDirector.open", side_effect=URLError("cannot connect")):
        with pytest.raises(AuthError):
            verify_token(signed(), config)


def test_expired_jwks_cache_cannot_bypass_unavailable_endpoint(config, signed, private_key):
    with patch("time.monotonic", return_value=1000) as clock, patch(
        "urllib.request.OpenerDirector.open",
        side_effect=[response(jwks_document(private_key, "k1")), URLError("cannot connect")],
    ) as request:
        assert verify_token(signed(), config).sub == "u1"
        clock.return_value = 1400
        with pytest.raises(AuthError):
            verify_token(signed(), config)
    assert request.call_count == 2


def test_core_import_does_not_load_fastapi():
    subprocess.run([sys.executable, "-c", "import sys; import auth_sdk; assert 'fastapi' not in sys.modules"], check=True)
