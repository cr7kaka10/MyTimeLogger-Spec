import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from server.domain.atimelogger_backup_store import ATimeLoggerBackupStore, beijing_text
from server.domain.atimelogger_final_backup import (
    ATimeLoggerFinalBackupWorker,
    ATimeLoggerFinalClient,
    ATimeLoggerRemoteError,
    build_comment,
)
from server.models.server_schema import ensure_server_schema


NOW = datetime(2026, 7, 25, 18, 30, tzinfo=timezone(timedelta(hours=8)))


def _db(tmp_path):
    path = tmp_path / "backup.db"
    conn = sqlite3.connect(path)
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES (1,'u1','x','now')")
    conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES (2,'u2','x','now')")
    for user_id, session_id in ((1, "s1"), (2, "s2")):
        conn.execute(
            "INSERT INTO server_study_sessions "
            "(id,user_id,start_time,end_time,net_duration_minutes,date,updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (session_id, user_id, "2026-07-25 18:00:00+08:00",
             "2026-07-25 18:30:00+08:00", 30, "2026-07-25", beijing_text(NOW)),
        )
        ATimeLoggerBackupStore.enqueue_in_tx(conn, user_id, session_id, beijing_text(NOW))
    conn.commit()
    conn.close()
    return path


def _connect(path):
    def connect():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn
    return connect


def test_store_claims_once_and_preserves_user_isolation(tmp_path):
    path = _db(tmp_path)
    store = ATimeLoggerBackupStore(_connect(path), now=lambda: NOW)
    first = store.claim_due()
    second = store.claim_due()
    assert {first["user_id"], second["user_id"]} == {1, 2}
    assert store.claim_due() is None

    store.mark(first["id"], "auth_required", error_code="auth_required")
    assert store.retry_user(first["user_id"]) == 1
    claimed = store.claim_due()
    assert claimed["user_id"] == first["user_id"]

    store.mark(claimed["id"], "confirmed", activity_id="a1", interval_id="i1")
    conn = _connect(path)()
    row = conn.execute(
        "SELECT * FROM server_atimelogger_backups WHERE user_id=?", (first["user_id"],)
    ).fetchone()
    assert (row["sync_state"], row["remote_activity_id"], row["remote_interval_id"]) == (
        "confirmed", "a1", "i1",
    )
    conn.close()


def test_old_backup_schema_gains_recovery_columns_idempotently(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE server_atimelogger_backups ("
        "id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,stable_session_id TEXT NOT NULL,"
        "remote_activity_id TEXT,remote_interval_id TEXT,sync_state TEXT NOT NULL,"
        "attempts INTEGER NOT NULL,last_error_code TEXT,next_retry_at TEXT,claimed_at TEXT,"
        "created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(user_id,stable_session_id))"
    )
    ensure_server_schema(conn)
    ensure_server_schema(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(server_atimelogger_backups)")}
    assert {"last_error_step", "running_baseline_json"}.issubset(columns)
    conn.close()


def test_session_and_backup_job_rollback_together(tmp_path):
    path = _db(tmp_path)
    conn = _connect(path)()
    conn.execute("BEGIN")
    conn.execute(
        "INSERT INTO server_study_sessions "
        "(id,user_id,start_time,end_time,net_duration_minutes,date,updated_at) "
        "VALUES ('rollback-session',1,'2026-07-25 19:00:00+08:00',"
        "'2026-07-25 19:30:00+08:00',30,'2026-07-25',?)",
        (beijing_text(NOW),),
    )
    ATimeLoggerBackupStore.enqueue_in_tx(conn, 1, "rollback-session", beijing_text(NOW))
    conn.rollback()
    assert conn.execute(
        "SELECT COUNT(*) FROM server_study_sessions WHERE id='rollback-session'"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM server_atimelogger_backups WHERE stable_session_id='rollback-session'"
    ).fetchone()[0] == 0
    conn.close()


def test_edit_requeues_and_delete_only_keeps_mapped_job(tmp_path):
    path = _db(tmp_path)
    conn = _connect(path)()
    ATimeLoggerBackupStore.enqueue_in_tx(conn, 1, "s1", beijing_text(NOW))
    row = conn.execute(
        "SELECT id FROM server_atimelogger_backups WHERE user_id=1 AND stable_session_id='s1'"
    ).fetchone()
    conn.execute(
        "UPDATE server_atimelogger_backups SET sync_state='confirmed',remote_activity_id='a1' WHERE id=?",
        (row["id"],),
    )
    ATimeLoggerBackupStore.enqueue_in_tx(conn, 1, "s1", beijing_text(NOW))
    assert conn.execute(
        "SELECT sync_state FROM server_atimelogger_backups WHERE id=?", (row["id"],)
    ).fetchone()[0] == "pending"
    ATimeLoggerBackupStore.delete_in_tx(conn, 1, "s1", beijing_text(NOW))
    assert conn.execute(
        "SELECT sync_state FROM server_atimelogger_backups WHERE id=?", (row["id"],)
    ).fetchone()[0] == "delete_pending"
    ATimeLoggerBackupStore.delete_in_tx(conn, 2, "s2", beijing_text(NOW))
    assert conn.execute(
        "SELECT COUNT(*) FROM server_atimelogger_backups WHERE user_id=2"
    ).fetchone()[0] == 0
    conn.close()


def test_direct_stopped_post_is_rejected_and_history_adapter_uses_full_dto():
    calls = []
    full = {
        "id": "a1", "status": "STOPPED", "typeId": "type-1",
        "start": None, "comment": "", "tags": [], "duration": 1800,
        "intervals": [{
            "id": "i1", "activityId": "a1", "typeId": "type-1",
            "start": "2026-07-25T10:00:00Z", "finish": "2026-07-25T10:30:00Z",
            "from": 1784973600, "to": 1784975400, "duration": 1800,
            "comment": "", "tags": [],
        }],
    }

    class Response:
        content = b"{}"
        def __init__(self, status_code, data): self.status_code, self.data = status_code, data
        def raise_for_status(self): return None
        def json(self): return self.data

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs.get("json")))
        if method == "POST" and url.endswith("/api/activities"):
            return Response(500, {})
        if "/start/" in url or "/stop/" in url:
            return Response(200, {"activities": [{"id": "a1"}]})
        if method == "GET":
            return Response(200, full)
        return Response(200, kwargs.get("json") or {})

    client = ATimeLoggerFinalClient("secret", requester=request)
    with pytest.raises(ATimeLoggerRemoteError) as rejected:
        client._request("POST", "/api/activities", {}, step="activity.final.start")
    assert (rejected.value.code, rejected.value.step) == (
        "remote_http_500", "activity.final.start",
    )
    assert client.start_final("type-1", "2026-07-25 18:00:00+08:00")["id"] == "a1"
    assert client.stop_final("a1", "2026-07-25 18:30:00+08:00")["id"] == "a1"
    client.update_full(
        "a1", "i1", "type-1", "2026-07-25 18:00:00+08:00",
        "2026-07-25 18:30:00+08:00", "备注",
    )
    assert [call[0] for call in calls[1:]] == ["POST", "POST", "GET", "PUT"]
    payload = calls[-1][2]
    assert payload["id"] == "a1"
    assert payload["start"] is None
    assert payload["intervals"][0]["id"] == "i1"
    assert payload["intervals"][0]["activityId"] == "a1"
    assert payload["intervals"][0]["duration"] == 1800
    assert payload["intervals"][0]["comment"] == "备注"


def test_safe_reads_retry_tls_failure_but_final_start_does_not():
    import requests

    attempts = {"types": 0, "start": 0}

    class Response:
        status_code = 200
        content = b"[]"
        def raise_for_status(self): return None
        def json(self): return []

    def requester(_method, url, **_kwargs):
        key = "start" if "/start/" in url else "types"
        attempts[key] += 1
        if attempts[key] == 1:
            raise requests.exceptions.SSLError("handshake")
        return Response()

    client = ATimeLoggerFinalClient("secret", requester=requester)
    assert client.list_types() == []
    with pytest.raises(ATimeLoggerRemoteError):
        client.start_final("t1", "2026-07-25 18:00:00+08:00")
    assert attempts == {"types": 2, "start": 1}


@pytest.mark.parametrize("category,pause_reasons", [
    ("娱乐", "[]"),
    ("输入", '["查资料"]'),
    ("输出", '["休息"]'),
])
def test_worker_creates_one_final_record_for_each_session_kind(tmp_path, category, pause_reasons):
    path = _db(tmp_path)
    conn = _connect(path)()
    conn.execute("INSERT INTO server_categories(id,user_id,name,group_name) VALUES (10,1,?,'生活')", (category,))
    conn.execute(
        "UPDATE server_study_sessions SET category_id=10,pause_reasons=? WHERE id='s1'",
        (pause_reasons,),
    )
    conn.commit()
    conn.close()
    events, remote = [], {"interval": None}

    class Client:
        def __init__(self, _token): pass
        def list_types(self): return [{"id": "t1", "name": category}]
        def list_running(self): return []
        def find_interval(self, *_args): return remote["interval"]
        def start_final(self, type_id, start):
            events.append(("start", type_id, start)); return {"id": "a1"}
        def stop_final(self, activity_id, end):
            events.append(("stop", activity_id, end))
            remote["interval"] = {"id": "i1", "activityId": "a1", "typeId": "t1"}
            return {"id": "a1"}
        def update_full(self, *args): events.append(("update", *args)); return {"id": "a1"}

    worker = ATimeLoggerFinalBackupWorker(
        ATimeLoggerBackupStore(_connect(path), now=lambda: NOW), _connect(path),
        lambda _uid: {"enabled": True, "token": "token"}, lambda _uid: None,
        client_factory=Client,
    )
    assert worker.process_once() is True
    assert [event[0] for event in events] == ["start", "stop", "update"]
    assert events[1][1] == "a1"
    assert all("official" not in event for event in events)


def test_worker_recovers_lost_start_response_without_stopping_baseline(tmp_path):
    path = _db(tmp_path)
    conn = _connect(path)()
    conn.execute(
        "INSERT INTO server_categories(id,user_id,name,group_name) VALUES (10,1,'娱乐','生活')"
    )
    conn.execute("UPDATE server_study_sessions SET category_id=10 WHERE id='s1'")
    conn.commit()
    conn.close()
    remote = {"running": [],
              "interval": None, "start_attempts": 0, "stopped": []}

    class Client:
        def __init__(self, _token): pass
        def list_types(self): return [{"id": "t1", "name": "娱乐", "deleted": False}]
        def list_running(self): return list(remote["running"])
        def find_interval(self, *_args): return remote["interval"]
        def start_final(self, _type_id, start):
            remote["start_attempts"] += 1
            remote["running"].append({
                "id": "a1", "typeId": "t1", "status": "RUNNING", "start": start,
            })
            raise ATimeLoggerRemoteError("remote_timeout", "activity.final.start")
        def stop_final(self, activity_id, _end):
            remote["stopped"].append(activity_id)
            remote["interval"] = {"id": "i1", "activityId": activity_id, "typeId": "t1"}
        def update_full(self, *_args): return {"id": "a1"}

    store = ATimeLoggerBackupStore(_connect(path), now=lambda: NOW)
    worker = ATimeLoggerFinalBackupWorker(
        store, _connect(path), lambda _uid: {"enabled": True, "token": "token"},
        lambda _uid: None, client_factory=Client,
    )
    assert worker.process_once() is True
    assert store.retry_user(1) == 1
    restarted_worker = ATimeLoggerFinalBackupWorker(
        store, _connect(path), lambda _uid: {"enabled": True, "token": "token"},
        lambda _uid: None, client_factory=Client,
    )
    assert restarted_worker.process_once() is True
    conn = _connect(path)()
    row = conn.execute(
        "SELECT sync_state,remote_activity_id,remote_interval_id FROM server_atimelogger_backups WHERE user_id=1"
    ).fetchone()
    assert tuple(row) == ("confirmed", "a1", "i1")
    conn.close()
    assert remote["start_attempts"] == 1
    assert remote["stopped"] == ["a1"]
    assert build_comment("", "[]") == ""


def test_worker_defers_while_official_activity_is_running(tmp_path):
    path = _db(tmp_path)
    conn = _connect(path)()
    conn.execute("INSERT INTO server_categories(id,user_id,name,group_name) VALUES (10,1,'娱乐','生活')")
    conn.execute("UPDATE server_study_sessions SET category_id=10 WHERE id='s1'")
    conn.commit(); conn.close()
    events = []

    class Client:
        def __init__(self, _token): pass
        def list_types(self): return [{"id": "t1", "name": "娱乐"}]
        def find_interval(self, *_args): return None
        def list_running(self): return [{"id": "official", "status": "RUNNING"}]
        def start_final(self, *_args): events.append("start")
        def stop_final(self, *_args): events.append("stop")

    store = ATimeLoggerBackupStore(_connect(path), now=lambda: NOW)
    worker = ATimeLoggerFinalBackupWorker(
        store, _connect(path), lambda _uid: {"enabled": True, "token": "token"},
        lambda _uid: None, client_factory=Client,
    )
    assert worker.process_once() is True
    conn = _connect(path)()
    row = dict(conn.execute(
        "SELECT sync_state,last_error_code FROM server_atimelogger_backups WHERE user_id=1"
    ).fetchone())
    conn.close()
    assert (row["sync_state"], row["last_error_code"], events) == (
        "pending", "remote_running_active", [],
    )


def test_worker_recovers_lost_stop_response_without_starting_again(tmp_path):
    path = _db(tmp_path)
    conn = _connect(path)()
    conn.execute("INSERT INTO server_categories(id,user_id,name,group_name) VALUES (10,1,'娱乐','生活')")
    conn.execute("UPDATE server_study_sessions SET category_id=10 WHERE id='s1'")
    conn.commit(); conn.close()
    remote = {"interval": None, "starts": 0, "stops": 0}

    class Client:
        def __init__(self, _token): pass
        def list_types(self): return [{"id": "t1", "name": "娱乐"}]
        def list_running(self): return []
        def find_interval(self, *_args): return remote["interval"]
        def start_final(self, *_args): remote["starts"] += 1; return {"id": "a1"}
        def stop_final(self, activity_id, _end):
            remote["stops"] += 1
            remote["interval"] = {"id": "i1", "activityId": activity_id, "typeId": "t1"}
            raise ATimeLoggerRemoteError("remote_timeout", "activity.final.stop")
        def update_full(self, *_args): return {"id": "a1"}

    store = ATimeLoggerBackupStore(_connect(path), now=lambda: NOW)
    worker = ATimeLoggerFinalBackupWorker(
        store, _connect(path), lambda _uid: {"enabled": True, "token": "token"},
        lambda _uid: None, client_factory=Client,
    )
    assert worker.process_once() is True
    assert store.retry_user(1) == 1
    assert worker.process_once() is True
    assert (remote["starts"], remote["stops"]) == (1, 1)


def test_reconciliation_is_cutover_scoped_and_idempotent(tmp_path):
    path = _db(tmp_path)
    conn = _connect(path)()
    conn.execute("DELETE FROM server_atimelogger_backups")
    conn.commit(); conn.close()
    store = ATimeLoggerBackupStore(_connect(path), now=lambda: NOW)
    assert store.reconcile_user(1, cutover="2026-07-25 18:15:00+08:00") == 1
    assert store.reconcile_user(1, cutover="2026-07-25 18:15:00+08:00") == 0
    assert store.reconcile_user(2, cutover="2026-07-25 19:00:00+08:00") == 0
    assert store.reconcile_user(2, session_ids=["s2"]) == 1


def test_worker_deleted_source_cleans_job_without_remote_request(tmp_path):
    path = _db(tmp_path)
    conn = _connect(path)()
    conn.execute(
        "UPDATE server_atimelogger_backups SET sync_state='delete_pending',"
        "remote_activity_id='owned-a',remote_interval_id='owned-i' "
        "WHERE user_id=1 AND stable_session_id='s1'"
    )
    conn.execute("DELETE FROM server_study_sessions WHERE user_id=1 AND id='s1'")
    conn.commit(); conn.close()
    deleted = []

    class Client:
        def __init__(self, _token): pass
        def delete_mapped(self, *args): deleted.append(args)

    worker = ATimeLoggerFinalBackupWorker(
        ATimeLoggerBackupStore(_connect(path), now=lambda: NOW), _connect(path),
        lambda _uid: {"enabled": True, "token": "token"}, lambda _uid: None,
        client_factory=Client,
    )
    assert worker.process_once() is True
    conn = _connect(path)()
    count = conn.execute("SELECT COUNT(*) FROM server_atimelogger_backups WHERE user_id=1").fetchone()[0]
    conn.close()
    assert deleted == []
    assert count == 0


def test_worker_rechecks_known_activity_without_creating_or_stopping_again(tmp_path):
    path = _db(tmp_path)
    conn = _connect(path)()
    conn.execute("INSERT INTO server_categories(id,user_id,name,group_name) VALUES (10,1,'娱乐','生活')")
    conn.execute("UPDATE server_study_sessions SET category_id=10 WHERE user_id=1")
    conn.execute("UPDATE server_atimelogger_backups SET remote_activity_id='a1' WHERE user_id=1")
    category_name = "娱乐"
    conn.commit(); conn.close()
    remote = {"visible": False, "activity_lookups": 0}

    class Client:
        def __init__(self, _token): pass
        def list_types(self): return [{"id": "t1", "name": category_name}]
        def find_interval(self, *_args): return None
        def find_interval_for_activity(self, *_args):
            remote["activity_lookups"] += 1
            return {"id": "i1", "activityId": "a1", "typeId": "t1"} if remote["visible"] else None
        def start_final(self, *_args): raise AssertionError("must not create another activity")
        def stop_final(self, *_args): raise AssertionError("must not stop an already-known activity again")
        def update_full(self, *_args): return {"id": "a1"}

    store = ATimeLoggerBackupStore(_connect(path), now=lambda: NOW)
    worker = ATimeLoggerFinalBackupWorker(store, _connect(path), lambda _uid: {"enabled": True, "token": "token"}, lambda _uid: None, client_factory=Client)
    assert worker.process_once() is True
    conn = _connect(path)(); row = conn.execute("SELECT sync_state,last_error_code FROM server_atimelogger_backups WHERE user_id=1").fetchone(); conn.close()
    assert tuple(row) == ("failed", "remote_interval_not_ready")
    remote["visible"] = True
    assert store.retry_user(1) == 1
    assert worker.process_once() is True
    conn = _connect(path)(); row = conn.execute("SELECT sync_state,remote_activity_id,remote_interval_id FROM server_atimelogger_backups WHERE user_id=1").fetchone(); conn.close()
    assert tuple(row) == ("confirmed", "a1", "i1")
    assert remote["activity_lookups"] >= 3
