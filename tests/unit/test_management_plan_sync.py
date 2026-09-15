import asyncio
import json
import sqlite3

from server.db_wrapper import ServerDBWrapper
from server.domain.management_plan_service import ManagementPlanService
from server.models.server_schema import ensure_server_schema
from server.sync_hub import SyncHub


def _setup(tmp_path):
    db_path = tmp_path / "management-plan-sync.db"
    conn = sqlite3.connect(db_path)
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES ('a','x','2026-08-06 02:00:00')")
    conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES ('b','x','2026-08-06 02:00:00')")
    conn.commit()
    conn.close()

    def connect():
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        return connection

    service = ManagementPlanService(connect)
    wrapper = ServerDBWrapper()
    wrapper.log_path = str(db_path)
    return db_path, service, SyncHub(wrapper)


def _payload(plan_key="sync-plan"):
    return {
        "schema_version": "1",
        "plan_key": plan_key,
        "title": "同步方案",
        "items": [
            {"logical_key": "habit.sync", "type": "local_habit", "action": "create", "expected_minutes": 5},
        ],
    }


def test_pull_contains_only_current_users_published_plan_metadata(tmp_path):
    _, service, hub = _setup(tmp_path)
    draft = service.create_draft(1, "建立同步方案", generated_payload=_payload())

    before = asyncio.run(hub.handle_pull_by_version(0, user_id=1, limit=100))
    assert before["management_plans"] == {"plans": [], "revisions": [], "bindings": [], "change_log": []}

    preview = service.preview(1, draft["draft_id"])
    applied = service.apply(1, draft["draft_id"], preview["plan_digest"], "sync-apply-1")
    revision_id = applied["result"]["revision"]["revision_id"]

    user_a = asyncio.run(hub.handle_pull_by_version(0, user_id=1, limit=100))["management_plans"]
    user_b = asyncio.run(hub.handle_pull_by_version(0, user_id=2, limit=100))["management_plans"]
    assert [row["id"] for row in user_a["revisions"]] == [revision_id]
    assert user_a["revisions"][0]["manifest_digest"] == preview["plan_digest"]
    assert user_a["bindings"][0]["logical_key"] == "habit.sync"
    assert user_a["change_log"][0]["revision_id"] == revision_id
    assert user_b == {"plans": [], "revisions": [], "bindings": [], "change_log": []}


def test_legacy_pull_exposes_same_snapshot_without_runtime_facts(tmp_path, caplog):
    _, service, hub = _setup(tmp_path)
    draft = service.create_draft(1, "建立同步方案", generated_payload=_payload("legacy-plan"))
    preview = service.preview(1, draft["draft_id"])
    service.apply(1, draft["draft_id"], preview["plan_digest"], "legacy-apply-1")

    pull = asyncio.run(hub.handle_pull(None, user_id=1))
    snapshot = pull["management_plans"]
    assert snapshot["revisions"][0]["plan_key"] == "legacy-plan"
    serialized = json.dumps(snapshot, ensure_ascii=False)
    assert "reward_ledger" not in serialized
    assert "user_wallets" not in serialized
    assert "server_management_plan_drafts" not in serialized
    assert not any("management_plan_revisions" in record.message for record in caplog.records)


def test_client_cannot_overwrite_published_management_revision(tmp_path):
    db_path, _, hub = _setup(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO server_management_plans(id,user_id,plan_key,title,active_revision_id,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                     ("plan-1", 1, "owned-plan", "方案", "revision-1", "active", "2026-08-12 18:00:00", "2026-08-12 18:00:00"))
        conn.execute("INSERT INTO server_management_plan_revisions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     ("revision-1", "plan-1", 1, "1", "published", None, "{}", "original", "published", None,
                      "2026-08-12 18:00:00", "2026-08-12 18:00:00"))

    result = asyncio.run(hub.handle_push([{
        "table": "management_plan_revisions", "change_id": "client-overwrite", "operation": "upsert",
        "payload": {"id": "revision-1", "plan_id": "invalid", "version": "999", "revision_kind": "import",
                    "manifest_json": "{}", "manifest_digest": "forged", "approval_status": "published",
                    "created_at": "2026-08-12 18:00:00"},
    }], user_id=1))

    with sqlite3.connect(db_path) as conn:
        digest = conn.execute("SELECT manifest_digest FROM server_management_plan_revisions WHERE id='revision-1'").fetchone()[0]
    assert result["rejected"][0]["reason"] == "server_owned_management_plan_revisions"
    assert digest == "original"


def test_legacy_client_cannot_write_any_management_publication_table(tmp_path):
    db_path, _, hub = _setup(tmp_path)
    tables = ("management_plans", "management_plan_revisions",
              "management_plan_bindings", "management_plan_change_log")
    for table in tables:
        result = asyncio.run(hub.handle_push([{
            "table": table, "change_id": f"blocked-{table}", "payload": {"id": "foreign", "user_id": 2},
        }], user_id=1))
        assert result["rejected"][0]["reason"] == f"server_owned_{table}"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_management_plans").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM server_management_plan_revisions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM server_management_plan_bindings").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM server_management_plan_change_log").fetchone()[0] == 0
