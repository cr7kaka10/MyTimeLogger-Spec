import asyncio
from pathlib import Path
from starlette.requests import Request
import server.server as server_module


def _request():
    return Request({"type": "http", "method": "GET", "path": "/api/sync/pull", "headers": [], "query_string": b""})


def _pull_result():
    return {"changes": [], "tables": {}, "from_version": 0, "to_version": 0, "has_more": False,
            "server_time": "2026-09-11 12:00:00", "wallet": None, "ledger_snapshot": None, "diagnostics": {}}


def test_sync_pull_only_refreshes_provider_in_checklist_scope(monkeypatch):
    provider_calls = []

    async def provider(*args, **kwargs):
        provider_calls.append(kwargs)
        return {"ok": True, "status": "success", "errors": []}

    async def pull(*args, **kwargs):
        return _pull_result()

    monkeypatch.setattr(server_module.sync_hub, "force_pull_ticktick", provider)
    monkeypatch.setattr(server_module.sync_hub, "handle_pull_by_version", pull)
    core = asyncio.run(server_module.sync_pull(_request(), refresh=True, sync_scope="core", since_version=0, user={"id": 1}))
    assert provider_calls == []
    assert core["diagnostics"]["scope"] == "core"
    assert core["diagnostics"]["provider_executed"] is False
    checklist = asyncio.run(server_module.sync_pull(_request(), refresh=True, provider_manual=True,
                                                     sync_scope="checklist", since_version=0, user={"id": 1}))
    assert len(provider_calls) == 1 and provider_calls[0]["manual"] is True
    assert checklist["diagnostics"]["scope"] == "checklist"
    assert checklist["diagnostics"]["provider_executed"] is True


def test_server_lifespan_does_not_start_ticktick_poll():
    source = Path(server_module.__file__).read_text(encoding="utf-8")
    lifespan = source[source.index("async def lifespan"):source.index("# --- 2.", source.index("async def lifespan"))]
    assert "start_ticktick_poll(" not in lifespan
