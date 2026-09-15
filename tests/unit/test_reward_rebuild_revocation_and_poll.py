import asyncio
import json
import sqlite3
from types import SimpleNamespace

import pytest

import server.domain.reward_rebuild_service as rebuild_module
import server.sync_hub as sync_module
from server.db_wrapper import ServerDBWrapper
from server.domain.reward_rebuild_service import RewardRebuildError, RewardRebuildService
from server.models.server_schema import ensure_server_schema
from server.store import ServerSleepStore
from server.sync_hub import SyncHub


def _rebuild_case(tmp_db_path, monkeypatch, event_type):
    store = ServerSleepStore(db_path=tmp_db_path)
    service = RewardRebuildService(store)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','p','2026-08-25')")
        conn.execute("INSERT INTO server_reward_ledger VALUES('old',1,2,'manual_adjustment','old','旧账','2026-08-25','2026-08-25 00:00:00','2026-08-25','2026-08-25',NULL)")
        store.reward_wallet_service.rebuild_wallet_snapshot_in_txn(conn, 1, lambda: '2026-08-25')
        snapshot = service._snapshot(conn, 1)
        frozen = service._revision(conn, 1)
        conn.execute("INSERT INTO server_reward_rebuild_jobs(id,user_id,status,statistics_start_date,preview_hash,frozen_revision,trace_id,created_at,updated_at) VALUES('job',1,'queued','2026-08-01','hash',?,'trace','2026-08-25','2026-08-25')", (frozen,))
        conn.execute("INSERT INTO server_reward_rebuild_snapshots(job_id,user_id,epoch,snapshot_json,created_at) VALUES('job',1,0,?, '2026-08-25')", (json.dumps(snapshot),))

    class FakeBuilder:
        def __init__(self, candidate_store):
            self.store = candidate_store

        def build(self, user_id, start_date):
            with self.store._transact() as conn:
                for table in ("server_backpack_events", "server_reward_fragments", "server_user_wallets", "server_external_rewards", "server_reward_ledger"):
                    conn.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
                if event_type == "revoked":
                    conn.execute("INSERT INTO server_reward_ledger VALUES('fact',1,5,'manual_adjustment','fact','事实','2026-08-25','2026-08-25 00:00:00','2026-08-25','2026-08-25',NULL)")
                    conn.execute("INSERT INTO server_user_wallets(user_id,balance,updated_at) VALUES(1,5,'2026-08-25')")
                else:
                    conn.execute("INSERT INTO server_user_wallets(user_id,balance,updated_at) VALUES(1,0,'2026-08-25')")
                conn.execute("INSERT INTO server_backpack_events(id,user_id,ledger_id,event_type,created_at) VALUES('event',1,'missing',?,'2026-08-25')", (event_type,))
            return {"ledger_rows": 1 if event_type == "revoked" else 0, "balance": 5 if event_type == "revoked" else 0, "skipped": []}

    monkeypatch.setattr(rebuild_module, "RewardCandidateBuilder", FakeBuilder)
    return store, service


def test_revoked_backpack_event_can_publish_candidate(tmp_db_path, monkeypatch):
    store, service = _rebuild_case(tmp_db_path, monkeypatch, "revoked")
    report = service.build_and_publish(1, "job", {"ok": True})
    assert report["balance"] == 5
    assert store.verify_wallet_consistency(1)["consistent"]
    with store._connect() as conn:
        assert conn.execute("SELECT event_type FROM server_backpack_events WHERE id='event'").fetchone()[0] == "revoked"


def test_orphan_backpack_event_is_rejected_and_old_ledger_restored(tmp_db_path, monkeypatch):
    store, service = _rebuild_case(tmp_db_path, monkeypatch, "acquired")
    with pytest.raises(RewardRebuildError) as failure:
        service.build_and_publish(1, "job", {"ok": True})
    service.fail_and_restore(1, "job", failure.value)
    with store._connect() as conn:
        job = conn.execute("SELECT status,failure_report_json FROM server_reward_rebuild_jobs WHERE id='job'").fetchone()
        assert job[0] == "failed"
        assert json.loads(job[1])["code"] == "candidate_reference_invalid"
        assert conn.execute("SELECT id FROM server_reward_ledger WHERE id='old'").fetchone()[0] == "old"


def test_ticktick_poll_uses_defined_client_context(tmp_path, monkeypatch):
    path = str(tmp_path / "poll.db")
    conn = sqlite3.connect(path)
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','p','2026-08-25')")
    conn.commit()
    conn.close()
    hub = SyncHub(ServerDBWrapper(db_path=path))
    settings = SimpleNamespace(enabled=True, access_token="token", host="host", verify_tls=True, timeout_seconds=3)
    calls = []

    class Client:
        def __init__(self, token, host, *, verify_tls, timeout_seconds):
            calls.append((token, host, verify_tls, timeout_seconds))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    async def pull_tasks(client, user_id):
        calls.append("tasks")

    async def pull_habits(client, user_id):
        calls.append("habits")

    monkeypatch.setattr(sync_module, "_get_ticktick_client_class", lambda: Client)
    monkeypatch.setattr(hub, "_get_ticktick_settings", lambda user_id: settings)
    monkeypatch.setattr(hub, "_pull_tasks", pull_tasks)
    monkeypatch.setattr(hub, "_pull_habits", pull_habits)
    monkeypatch.setattr(hub, "_notify_clients", lambda tables: calls.append(tuple(tables)))
    asyncio.run(hub._ticktick_sync_once_for_user(1))
    assert calls[:2] == [("token", "host", True, 3), "tasks"]
    assert "habits" in calls
