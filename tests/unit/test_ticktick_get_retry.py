# -*- coding: utf-8 -*-
import asyncio

import httpx
import pytest

from server.ticktick_client import TickTickClient


class _Responses:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    async def get(self, *_args, **_kwargs):
        self.calls += 1
        item = next(self.responses)
        if isinstance(item, Exception):
            raise item
        return item


def _response(status=200, body='{}'):
    return httpx.Response(status, content=body, request=httpx.Request('GET', 'https://ticktick.test'))


def test_get_retries_a_read_timeout_once_and_reports_actual_attempts():
    client = TickTickClient('token')
    client._client = _Responses([httpx.ReadTimeout('timeout'), _response()])

    assert asyncio.run(client._get('/project')) == {}
    assert client._client.calls == client.last_get_attempts == 2
    assert client.get_request_attempts == 2


def test_get_does_not_retry_http_status_failures():
    client = TickTickClient('token')
    client._client = _Responses([_response(500)])

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(client._get('/project'))
    assert client._client.calls == client.last_get_attempts == 1


def test_client_ignores_environment_proxy_unless_private_proxy_is_explicit(monkeypatch, caplog):
    captured = []
    class AsyncClient:
        def __init__(self, **options): captured.append(options)
        async def aclose(self): pass
    monkeypatch.setattr(httpx, "AsyncClient", AsyncClient)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")

    direct = TickTickClient("token")
    asyncio.run(direct.__aenter__()); asyncio.run(direct.__aexit__())
    proxied = TickTickClient("token", proxy_url="http://private:secret@127.0.0.1:8899")
    asyncio.run(proxied.__aenter__()); asyncio.run(proxied.__aexit__())

    assert captured[0]["trust_env"] is False and "proxy" not in captured[0]
    assert captured[1]["trust_env"] is False and captured[1]["proxy"].endswith("@127.0.0.1:8899")
    assert "private:secret" not in caplog.text and "token" not in caplog.text
