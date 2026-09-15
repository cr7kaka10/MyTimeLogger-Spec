import asyncio
import sqlite3
from types import SimpleNamespace
from fastapi import BackgroundTasks

import server.server as server_module
from server.db_wrapper import ServerDBWrapper
from server.models.server_schema import ensure_server_schema
from server.sync_hub import SyncHub


def test_flash_push_claims_analysis_once_and_result_is_pullable(tmp_path):
    db_path = tmp_path / "flash-sync.db"
    conn = sqlite3.connect(db_path)
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','x','2026-08-12 18:00:00')")
    conn.commit(); conn.close()
    wrapper = ServerDBWrapper(); wrapper.log_path = str(db_path)
    hub = SyncHub(wrapper)
    payload = {"id": "flash-1", "occurred_at": "2026-08-12 18:00:00", "original_text": "记得写总结",
               "analysis_status": "pending", "created_at": "2026-08-12 18:00:00", "updated_at": "2026-08-12 18:00:00"}

    first = asyncio.run(hub.handle_push([{"table": "flash_cards", "change_id": "flash-change-1", "payload": payload}], 1))
    second = asyncio.run(hub.handle_push([{"table": "flash_cards", "change_id": "flash-change-2", "payload": payload}], 1))

    assert first["analysis_claims"] == ["flash-1"]
    assert second["analysis_claims"] == []
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE server_flash_cards SET polished_text='记得写总结。',analysis_status='done' WHERE id='flash-1' AND user_id=1")
        conn.commit()
    rows = hub.get_changes_since("flash_cards", None, 1)
    assert rows[0]["polished_text"] == "记得写总结。"


def test_flash_push_notifies_only_current_account(tmp_path):
    db_path = tmp_path / "flash-notify.db"
    conn = sqlite3.connect(db_path); ensure_server_schema(conn)
    conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'a','x','2026-08-12 18:00:00')")
    conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(2,'b','x','2026-08-12 18:00:00')")
    conn.commit(); conn.close()
    wrapper = ServerDBWrapper(); wrapper.log_path = str(db_path); hub = SyncHub(wrapper)
    own, other = asyncio.Queue(), asyncio.Queue()
    hub.subscribe(own, 1); hub.subscribe(other, 2)
    payload = {"id":"isolated","occurred_at":"2026-08-12 18:00:00","original_text":"隔离通知"}
    asyncio.run(hub.handle_push([{"table":"flash_cards","change_id":"isolated-1","payload":payload}], 1))
    assert own.get_nowait()["event"] == "changed"
    assert other.empty()


def test_flash_push_ignores_client_ai_fields_and_preserves_done_result(tmp_path):
    db_path = tmp_path / "flash-authority.db"; conn = sqlite3.connect(db_path); ensure_server_schema(conn)
    conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','x','2026-08-12 18:00:00')")
    conn.execute("INSERT INTO server_flash_cards(id,user_id,occurred_at,original_text,polished_text,analysis_status,created_at,updated_at) VALUES('f',1,'2026-08-12 18:00:00','原文','服务端结果','done','2026-08-12 18:00:00','2026-08-12 18:00:00')")
    conn.commit(); conn.close(); wrapper = ServerDBWrapper(); wrapper.log_path = str(db_path); hub = SyncHub(wrapper)
    result = asyncio.run(hub.handle_push([{"table":"flash_cards","change_id":"forged","payload":{
        "id":"f","occurred_at":"2026-08-12 18:00:00","original_text":"原文","polished_text":"伪造","analysis_status":"pending"}}], 1))
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT polished_text,analysis_status FROM server_flash_cards WHERE id='f'").fetchone()
    assert result["analysis_claims"] == []
    assert row == ("服务端结果", "done")


def test_sync_push_schedules_claimed_analysis_without_running_model(monkeypatch):
    class Request:
        headers = {}; state = SimpleNamespace()
        async def json(self): return {"operations": [{"table": "flash_cards", "payload": {"id": "f"}}]}
    async def handle_push(*_args, **_kwargs):
        return {"accepted": 1, "server_time": "2026-08-12 20:00:00", "changed_tables": ["flash_cards"], "rejected": [], "operation_results": [], "analysis_claims": ["f"]}
    monkeypatch.setattr(server_module.sync_hub, "handle_push", handle_push)
    background = BackgroundTasks()
    result = asyncio.run(server_module.sync_push(Request(), background, {"id": 1}))
    assert result["accepted"] == 1
    assert len(background.tasks) == 1


def test_background_flash_failure_audits_only_sanitized_attempts(monkeypatch):
    error = server_module.FlashCardError("flash_insight_analysis_failed", "失败", 502)
    error.attempts = [{"slot": "主模型", "stage": "provider", "code": "ReadTimeout", "secret": "do-not-store"}]
    finished = []
    monkeypatch.setattr(server_module, "flash_card_service", SimpleNamespace(
        get=lambda *_: {"original_text": "原文"}, mark_analysis_failed=lambda *_: None))
    monkeypatch.setattr(server_module, "flash_processing_log_service", SimpleNamespace(
        start=lambda *_: "audit-1", finish=lambda *args, **kwargs: finished.append((args, kwargs))))
    monkeypatch.setattr(server_module, "_flash_todo_diary_skill", lambda *_: "skill")
    monkeypatch.setattr(server_module, "_flash_todo_diary_analysis", lambda *_: (_ for _ in ()).throw(error))
    monkeypatch.setattr(server_module.sync_hub, "_notify_clients", lambda *_: None)

    server_module._process_synced_flash_card(1, "flash-1")

    assert finished[0][1]["normalized"] == {"attempts": [{"slot": "主模型", "stage": "provider", "code": "ReadTimeout"}]}


def test_flash_insight_audit_keeps_proofreading_summary_without_raw_fields():
    normalized = server_module._flash_insight_log_normalized({
        "polished_text": "今天好烦。",
        "todos": [],
        "diary": None,
        "_polish_code": "polish_edit_budget",
        "_polish_edit_count": 3,
        "attempts": [{"stage": "polish_retry", "code": "accepted", "raw_output": "不得记录"}],
        "raw_output": "不得记录",
    })

    assert normalized["proofreading"] == {"code": "polish_edit_budget", "edit_count": 3}
    assert normalized["attempts"] == [{"stage": "polish_retry", "code": "accepted"}]
    assert "raw_output" not in normalized
