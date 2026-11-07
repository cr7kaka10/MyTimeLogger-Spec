import asyncio
import json
import server.server as module


def test_reconnect_and_heartbeat_deliver_persisted_user_version(monkeypatch):
    current = [12]
    users = []
    class Connection:
        def execute(self, sql, args):
            users.append(args[0]); return self
        def fetchone(self): return (current[0],)
        def close(self): pass
    class Request:
        async def is_disconnected(self): return False
    monkeypatch.setattr(module.sync_hub, '_conn', Connection)
    monkeypatch.setattr(module, 'SSE_KEEPALIVE_INTERVAL_SEC', 0.001)
    async def run():
        response = await module.sync_events(Request(), user={'id': 7})
        stream = response.body_iterator
        assert await anext(stream) == 'data: connected\n\n'
        first = await anext(stream)
        assert json.loads(first.split('data: ')[1]) == {'server_version': 12}
        current[0] = 15
        second = await anext(stream)
        assert json.loads(second.split('data: ')[1]) == {'server_version': 15}
        assert await anext(stream) == ': heartbeat\n\n'
        assert await anext(stream) == ': heartbeat\n\n'
        await stream.aclose()
    asyncio.run(run())
    assert users and set(users) == {7}
