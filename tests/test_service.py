from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

import auth_sdk


def test_service_api_is_public():
    assert hasattr(auth_sdk, 'verify_service_token')


@pytest.fixture
def setup_service():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    config = auth_sdk.ServiceAuthConfig(
        issuer='https://issuer', jwks_url='https://issuer/certs', audience='target-api',
        allowed_service_clients={'worker'}, required_roles={'read', 'write'},
    )
    payload = dict(iss='https://issuer', aud='target-api', sub='service-sub', azp='worker',
                   exp=4102444800, resource_access={'target-api': {'roles': ['read', 'write']}})
    def sign(**updates):
        return 'Bearer ' + jwt.encode({**payload, **updates}, key, algorithm='RS256', headers={'kid': 'one'})
    with patch('jwt.PyJWKClient.get_signing_key_from_jwt', return_value=SimpleNamespace(key=key.public_key())):
        yield config, sign


def test_service_roles_require_all_and_correct_resource(setup_service):
    config, sign = setup_service
    assert auth_sdk.verify_service_token(sign(), config).sub == 'service-sub'
    for access in [{'target-api': {'roles': ['read']}}, {'other-api': {'roles': ['read', 'write']}}, {'target-api': {'roles': 'read write'}}]:
        with pytest.raises(auth_sdk.PermissionDenied):
            auth_sdk.verify_service_token(sign(resource_access=access), config)


@pytest.mark.parametrize('changes', [{'azp': 'portal-web'}, {'aud': 'other'}, {'exp': 1}, {'typ': 'ID'}, {'nonce': 'n'}])
def test_invalid_service_token(setup_service, changes):
    config, sign = setup_service
    with pytest.raises(auth_sdk.AuthError):
        auth_sdk.verify_service_token(sign(**changes), config)


def test_invalid_service_policy(setup_service):
    config, sign = setup_service
    for changes in [{'required_roles': 'read'}, {'required_roles': {''}}, {'allowed_service_clients': set()}, {'audience': ('a', 'b')}]:
        with pytest.raises(auth_sdk.ConfigurationError):
            replace(config, **changes)
    assert auth_sdk.verify_service_token(sign(), replace(config, required_roles={'read'}))
