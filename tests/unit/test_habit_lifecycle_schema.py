import sqlite3
import pytest
from server.models.server_schema import ensure_server_schema


def test_idempotent_migration_and_durable_user_isolated_evidence(tmp_path):
    conn = sqlite3.connect(tmp_path / "schema.db")
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users VALUES(1,'a','x','2026-09-22')")
    conn.execute("INSERT INTO users VALUES(2,'b','x','2026-09-22')")
    conn.execute("INSERT INTO server_habits(id,user_id,name,is_active,created_at,updated_at) VALUES('h',1,'h',1,'old','old')")
    ensure_server_schema(conn)
    assert conn.execute("SELECT archived_at,archive_reason,lifecycle_version FROM server_habits").fetchone() == (None, 'legacy_archived', 0)
    for uid in (1, 2):
        conn.execute("INSERT INTO server_habit_tombstones VALUES(?,'h',?,'p','2026-09-22','explicit',1,1,'[]')", (uid, f'b{uid}'))
    conn.execute("DELETE FROM server_habits WHERE user_id=1")
    ensure_server_schema(conn)
    assert conn.execute("SELECT COUNT(*) FROM server_habit_tombstones").fetchone()[0] == 2
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO server_habit_checkins(id,user_id,habit_id,updated_at) VALUES('c',1,'h','now')")
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    conn.close()
