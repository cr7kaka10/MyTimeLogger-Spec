import asyncio
import sqlite3
from server.db_wrapper import ServerDBWrapper
from server.models.server_schema import ensure_server_schema
from server.sync_hub import SyncHub


def _hub(path):
    conn = sqlite3.connect(path); ensure_server_schema(conn)
    conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','p','2026-09-11 12:00:00')")
    conn.commit(); conn.close()
    db = ServerDBWrapper(); db.log_path = str(path)
    return SyncHub(db)


def _operations(suffix):
    return [
        {"change_id": f"session-{suffix}", "device_id": "pc", "table": "study_sessions", "operation": "upsert", "payload":
         {"id": f"s-{suffix}", "start_time": "2026-09-11 10:00:00", "end_time": "2026-09-11 10:01:00",
          "net_duration_minutes": 1, "date": "2026-09-11", "updated_at": "2026-09-11 10:01:00"}},
        {"change_id": f"habit-{suffix}", "device_id": "pc", "table": "habits", "operation": "upsert", "payload":
         {"id": f"h-{suffix}", "name": "provider", "source": "ticktick", "created_at": "2026-09-11 10:00:00", "updated_at": "2026-09-11 10:01:00"}},
    ]


def test_sync_push_provider_forwarding_requires_checklist_scope(tmp_path):
    hub = _hub(tmp_path / "scope.db"); provider_calls = []

    async def provider(items, *_args):
        provider_calls.append(items)
        return {"ok": True, "results": [{"ok": True, "change_id": item["change_id"]} for item in items]}

    hub._push_and_sync_ticktick = provider
    core = asyncio.run(hub.handle_push(_operations("core"), user_id=1, sync_scope="core"))
    assert core["accepted"] == 1 and provider_calls == []
    assert any(item.get("reason") == "checklist_scope_required" for item in core["rejected"])
    checklist = asyncio.run(hub.handle_push(_operations("checklist"), user_id=1, sync_scope="checklist"))
    assert checklist["accepted"] == 2 and len(provider_calls) == 1
    assert checklist["provider_executed"] is True
