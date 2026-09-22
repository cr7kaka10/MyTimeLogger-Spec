import asyncio
import httpx
import pytest
from server.ticktick_client import TickTickClient


def query(code=200, body=b'{"id":"h1","status":0}', error=None):
    async def run():
        def reply(request):
            assert request.url.path == "/open/v1/habit/h1"
            if error:
                raise error("transport failed", request=request)
            return httpx.Response(code, content=body)
        client = TickTickClient("test-only", verify_tls=True)
        client.set_get_attempt_limit(1)
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as transport:
            client._client = transport
            return await client.get_habit_detail("h1")
    return asyncio.run(run())


def test_present_is_evidence_not_lifecycle():
    assert query()["record"]["id"] == "h1"
    unknown = query(body=b'{"id":"h1","status":99,"archivedTime":"old"}')
    assert unknown["state"] == "present" and unknown["record"]["status"] == 99


def test_404_is_unresolved_not_deleted():
    assert query(404) == {"state": "unresolved_missing", "status_code": 404, "record": None}


@pytest.mark.parametrize("code", [401, 403, 429, 500, 503])
def test_http_failures_propagate(code):
    with pytest.raises(httpx.HTTPStatusError) as error:
        query(code)
    assert error.value.response.status_code == code


@pytest.mark.parametrize("body", [b'', b'no json', b'[]', b'{}', b'{"id":"other","status":0}', b'{"id":"h1","status":true}'])
def test_invalid_response_never_becomes_missing(body):
    with pytest.raises(ValueError):
        query(body=body)


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectError])
def test_transport_failures_propagate(error):
    with pytest.raises(error):
        query(error=error)
