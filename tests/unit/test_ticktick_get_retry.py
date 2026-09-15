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
