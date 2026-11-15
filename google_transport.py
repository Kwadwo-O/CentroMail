"""Google HTTPS transport for networks with an unusable IPv6 route."""

import requests
from requests.adapters import HTTPAdapter
from authlib.integrations.flask_client.apps import FlaskOAuth2App
from authlib.integrations.requests_client import OAuth2Session


class GoogleIPv4Adapter(HTTPAdapter):
    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        # Binding an IPv4 source makes urllib3 skip IPv6 addresses. The URL
        # hostname is retained for TLS verification, SNI and the Host header.
        pool_kwargs['source_address'] = ('0.0.0.0', 0)
        return super().init_poolmanager(connections, maxsize, block, **pool_kwargs)

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        proxy_kwargs['source_address'] = ('0.0.0.0', 0)
        return super().proxy_manager_for(proxy, **proxy_kwargs)


class GoogleOAuth2Session(OAuth2Session):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mount('https://', GoogleIPv4Adapter())


class GoogleOAuthApp(FlaskOAuth2App):
    client_cls = GoogleOAuth2Session


class GoogleRequests:
    """Use separate sessions so accounts never share authentication or cookies."""

    @staticmethod
    def request(method, url, **kwargs):
        kwargs.setdefault('timeout', (5, 15))
        with requests.Session() as session:
            session.mount('https://', GoogleIPv4Adapter())
            return session.request(method, url, **kwargs)

    @classmethod
    def get(cls, url, **kwargs):
        return cls.request('GET', url, **kwargs)

    @classmethod
    def post(cls, url, **kwargs):
        return cls.request('POST', url, **kwargs)


google_requests = GoogleRequests()
