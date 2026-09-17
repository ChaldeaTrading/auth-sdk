import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import httpx
import pytest

import auth_sdk


def test_clients_are_public():
    assert hasattr(auth_sdk, 'ServiceTokenProvider')
    assert hasattr(auth_sdk, 'PermissionClient')


def provider(handler, **kwargs):
    return auth_sdk.ServiceTokenProvider('https://issuer/token', 'worker', 'private-secret',
                                        transport=httpx.MockTransport(handler), **kwargs)


def test_token_is_cached_and_concurrent_refresh_is_coalesced():
    calls = []
    def issue(request):
        calls.append(request)
        time.sleep(.02)
        return httpx.Response(200, json={'access_token': 'secret-token', 'token_type': 'Bearer', 'expires_in': 60})
    auth = provider(issue)
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(lambda _: auth.get_token(), range(8))) == ['secret-token'] * 8
    assert len(calls) == 1
    assert b'grant_type=client_credentials' in calls[0].content
    assert 'private-secret' not in repr(auth)
    assert 'secret-token' not in repr(auth)


def test_expired_token_not_used_when_refresh_fails():
    calls = []
    def issue(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json={'access_token': 'first', 'token_type': 'Bearer', 'expires_in': 60})
        return httpx.Response(500, text='private-secret')
    with patch('auth_sdk.clients.time.monotonic', return_value=100) as clock:
        auth = provider(issue)
        assert auth.get_token() == 'first'
        clock.return_value = 161
        with pytest.raises(auth_sdk.DependencyUnavailable) as caught:
            auth.get_token()
    assert 'private-secret' not in str(caught.value)


@pytest.mark.parametrize('body', [
    {}, {'access_token': 'x', 'token_type': 'Basic', 'expires_in': 60},
    {'access_token': 'x\nsecret', 'token_type': 'Bearer', 'expires_in': 60},
    {'access_token': 'x', 'token_type': 'Bearer', 'expires_in': True},
    {'access_token': 'x', 'token_type': 'Bearer', 'expires_in': -1},
    {'access_token': 'x', 'token_type': 'Bearer', 'expires_in': 'infinity'},
])
def test_invalid_token_response_fails_closed(body):
    auth = provider(lambda _: httpx.Response(200, json=body))
    with pytest.raises(auth_sdk.DependencyUnavailable):
        auth.get_token()


def test_http_auth_sync_async_and_origin_boundary():
    auth = provider(lambda _: httpx.Response(200, json={'access_token': 'token', 'token_type': 'bearer', 'expires_in': 60}))
    requests = []
    def target(request):
        requests.append(request)
        return httpx.Response(200)
    bound = auth.auth(allowed_origins={'https://target/api'})
    with httpx.Client(auth=bound, transport=httpx.MockTransport(target)) as client:
        client.get('https://target/api/resource')
        with pytest.raises(auth_sdk.ConfigurationError):
            client.get('https://wrong/api')
    async def run():
        async with httpx.AsyncClient(auth=bound, transport=httpx.MockTransport(target)) as client:
            await client.get('https://target/other')
    asyncio.run(run())
    assert len(requests) == 2
    assert all(r.headers['Authorization'] == 'Bearer token' for r in requests)


@pytest.mark.parametrize('status,body,error,result', [
    (200, {'allow': True}, None, True), (200, {'allow': False}, None, False),
    (200, {'allow': 'true'}, 'DependencyUnavailable', None),
    (200, {}, 'DependencyUnavailable', None),
    (503, {'allow': True}, 'DependencyUnavailable', None),
    (401, {}, 'AuthError', None), (403, {}, 'PermissionDenied', None),
])
def test_permission_contract(status, body, error, result):
    requests = []
    def decide(request):
        requests.append(request)
        return httpx.Response(status, json=body)
    client = auth_sdk.PermissionClient('https://permission', transport=httpx.MockTransport(decide))
    if error:
        with pytest.raises(getattr(auth_sdk, error)):
            client.authorize('Bearer user-token', 'shop-rag', 'admin')
    else:
        assert client.authorize('Bearer user-token', 'shop-rag', 'admin') is result
        assert asyncio.run(client.aauthorize('Bearer user-token', 'shop-rag', 'admin')) is result
    assert requests[0].url.path == '/permission-center/v1/authorize'
    assert requests[0].headers['Authorization'] == 'Bearer user-token'
    assert requests[0].read() == b'{"resource_type":"shop-rag","action":"admin"}'


@pytest.mark.parametrize('url', ['http://remote/token', 'https://user:secret@host/token', 'https://host/token?secret=x', 'file:///secret'])
def test_unsafe_endpoint_config_rejected(url):
    with pytest.raises(auth_sdk.ConfigurationError):
        auth_sdk.ServiceTokenProvider(url, 'worker', 'secret')
    with pytest.raises(auth_sdk.ConfigurationError):
        auth_sdk.PermissionClient(url)


def test_network_errors_and_redirects_do_not_forward_credentials():
    seen = []
    def redirect(request):
        seen.append(request.url.host)
        return httpx.Response(302, headers={'Location': 'https://unexpected/collect'})
    with pytest.raises(auth_sdk.DependencyUnavailable):
        provider(redirect).get_token()
    permissions = auth_sdk.PermissionClient('https://permission', transport=httpx.MockTransport(redirect))
    with pytest.raises(auth_sdk.DependencyUnavailable):
        permissions.authorize('Bearer token', 'shop', 'read')
    assert seen == ['issuer', 'permission']
    def down(request):
        raise httpx.ConnectError('private-secret', request=request)
    with pytest.raises(auth_sdk.DependencyUnavailable) as caught:
        provider(down).get_token()
    assert 'private-secret' not in str(caught.value)


def test_http_auth_requires_explicit_origins():
    auth = provider(lambda _: httpx.Response(200, json={'access_token': 'token', 'token_type': 'bearer', 'expires_in': 60}))
    with pytest.raises(TypeError):
        auth.auth()


def test_async_refresh_coalesces_and_does_not_block_event_loop():
    count = []
    def issue(request):
        count.append(1)
        time.sleep(.05)
        return httpx.Response(200, json={'access_token': 'token', 'token_type': 'bearer', 'expires_in': 60})
    auth = provider(issue)
    async def run():
        ticks = []
        async def ticker():
            await asyncio.sleep(.01)
            ticks.append(1)
        tasks = [auth.aget_token() for _ in range(5)]
        await asyncio.gather(ticker(), *tasks)
        assert ticks == [1]
    asyncio.run(run())
    assert len(count) == 1
