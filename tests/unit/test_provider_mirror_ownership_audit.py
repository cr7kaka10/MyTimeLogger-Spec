import json
import sqlite3

from server.models.server_schema import ensure_server_schema
from server.scripts.audit_provider_mirror_ownership import audit_provider_mirror_ownership


def test_audit_reports_owner_counts_and_only_masked_shared_credentials(tmp_path):
    path = tmp_path / "audit.db"
    token = "secret-provider-token"
    with sqlite3.connect(path) as conn:
        ensure_server_schema(conn)
        conn.executemany(
            "INSERT INTO users(id,username,password_hash,created_at) VALUES (?,?,?,?)",
            [(1, "one", "p", "now"), (4, "four", "p", "now")],
        )
        config = json.dumps({"access_token": token})
        conn.executemany(
            "INSERT INTO server_system_config(user_id,key,value,updated_at) VALUES (?,'ticktick_config',?,'now')",
            [(1, config), (4, config)],
        )
        conn.executemany(
            "INSERT INTO server_tasks(id,user_id,title,due_date,updated_at) VALUES ('shared',?,?,?,'now')",
            [(1, "one", "2026-09-06 09:00:00"), (4, "four", "2026-09-07 09:00:00")],
        )
        conn.executemany(
            "INSERT INTO server_habits(id,user_id,name,created_at,updated_at) VALUES ('habit',?,?,'now','now')",
            [(1, "one"), (4, "four")],
        )
        conn.execute(
            "INSERT INTO server_habit_checkins(id,user_id,habit_id,checkin_date,updated_at) VALUES ('check',1,'habit','2026-09-06','now')"
        )
    result = audit_provider_mirror_ownership(str(path), "2026-09-06")
    assert result["users"]["1"] == {
        "server_tasks": 1, "server_habits": 1, "server_habit_checkins": 1, "target_date_tasks": 1,
    }
    assert result["users"]["4"]["target_date_tasks"] == 0
    assert result["credential_fingerprints"][0]["user_ids"] == [1, 4]
    assert result["credential_fingerprints"][0]["shared"] is True
    assert token not in json.dumps(result)
