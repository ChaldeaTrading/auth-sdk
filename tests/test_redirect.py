import httpx
from auth_sdk import ServiceTokenProvider


def test_business_redirect_does_not_leak_token_to_other_origin():
    seen = []
    def target(request):
        seen.append((request.url.host, request.headers.get('authorization')))
        if request.url.host == 'target':
            return httpx.Response(302, headers={'Location': 'https://other/path'})
        return httpx.Response(200)
    token = ServiceTokenProvider('https://issuer/token', 'worker', 'secret',
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={'access_token':'sensitive', 'token_type':'Bearer','expires_in':60})))
    with httpx.Client(auth=token.auth(allowed_origins={'https://target'}),
                      transport=httpx.MockTransport(target), follow_redirects=True) as client:
        client.get('https://target/path')
    assert seen == [('target', 'Bearer sensitive'), ('other', None)]
