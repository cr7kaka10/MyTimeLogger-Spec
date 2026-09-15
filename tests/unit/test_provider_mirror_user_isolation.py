import sqlite3

import pytest

from server.db_wrapper import ServerDBWrapper
from server.models.provider_mirror_schema_migration import migrate_provider_mirror_identity
from server.models.server_schema import ensure_server_schema
from server.sync_hub import SyncHub


def _database(tmp_path):
    path = tmp_path / "provider-isolation.db"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        ensure_server_schema(conn)
        conn.executemany(
            "INSERT INTO users(id,username,password_hash,created_at) VALUES (?,?,?,?)",
            [(1, "one", "p", "2026-09-07"), (4, "four", "p", "2026-09-07")],
        )
    wrapper = ServerDBWrapper()
    wrapper.log_path = str(path)
    return path, wrapper


def _task(title):
    return {
        "id": "shared-task", "title": title, "priority": 0, "status": 0,
        "dueDate": "2026-09-06T09:00:00+0800", "tags": [], "etag": title,
    }


def test_same_provider_task_id_is_independent_per_user(tmp_path):
    path, wrapper = _database(tmp_path)
    assert wrapper.upsert_task(1, _task("用户一")) is True
    assert wrapper.upsert_task(4, _task("用户四")) is True
    assert wrapper.upsert_task(1, _task("用户一更新")) is True
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT user_id,title FROM server_tasks WHERE id='shared-task' ORDER BY user_id"
        ).fetchall()
    assert rows == [(1, "用户一更新"), (4, "用户四")]


def test_provider_fingerprint_tombstone_and_change_log_stay_with_owner(tmp_path):
    path, wrapper = _database(tmp_path)
    wrapper.upsert_task(1, _task("用户一"))
    wrapper.upsert_task(4, _task("用户四"))
    assert wrapper.get_provider_fingerprints(1, "server_tasks")["shared-task"]["source_etag"] == "用户一"
    assert wrapper.get_provider_fingerprints(4, "server_tasks")["shared-task"]["source_etag"] == "用户四"
    assert SyncHub(wrapper)._delete_provider_task(1, "shared-task") is True
    with sqlite3.connect(path) as conn:
        states = conn.execute(
            "SELECT user_id,deleted_at IS NOT NULL FROM server_tasks WHERE id='shared-task' ORDER BY user_id"
        ).fetchall()
        changes = conn.execute(
            "SELECT DISTINCT user_id FROM server_change_log WHERE record_id='shared-task' ORDER BY user_id"
        ).fetchall()
    assert states == [(1, 1), (4, 0)]
    assert changes == [(1,), (4,)]


def test_generic_sync_accepts_same_id_per_user_and_rejects_real_sql_error(tmp_path):
    path, wrapper = _database(tmp_path)
    hub = SyncHub(wrapper)
    assert hub.upsert("tasks", {"id": "sync-shared", "title": "one", "source": "ticktick"}, 1)[0]
    assert hub.upsert("tasks", {"id": "sync-shared", "title": "four", "source": "ticktick"}, 4)[0]
    ok, rejected = hub.upsert("tasks", {"id": "missing-title", "source": "ticktick"}, 1)
    assert ok is False
    assert rejected[0]["record_id"] == "missing-title"
    with sqlite3.connect(path) as conn:
        assert conn.execute(
            "SELECT user_id,title FROM server_tasks WHERE id='sync-shared' ORDER BY user_id"
        ).fetchall() == [(1, "one"), (4, "four")]


def test_habit_and_checkin_parentage_is_user_scoped(tmp_path):
    path, _ = _database(tmp_path)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executemany(
            "INSERT INTO server_habits(id,user_id,name,created_at,updated_at) VALUES ('shared-habit',?,?,?,?)",
            [(1, "用户一习惯", "2026-09-07", "2026-09-07"), (4, "用户四习惯", "2026-09-07", "2026-09-07")],
        )
        conn.executemany(
            "INSERT INTO server_habit_checkins(id,user_id,habit_id,checkin_date,updated_at) VALUES ('shared-checkin',?,'shared-habit','2026-09-06','2026-09-07')",
            [(1,), (4,)],
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO server_habit_checkins(id,user_id,habit_id,checkin_date,updated_at) VALUES ('orphan',2,'shared-habit','2026-09-06','2026-09-07')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO server_habit_checkins(id,user_id,habit_id,checkin_date,updated_at) VALUES ('duplicate-day',1,'shared-habit','2026-09-06','2026-09-07')"
            )


def _legacy_provider_tables(conn):
    conn.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at TEXT NOT NULL)")
    conn.execute("CREATE TABLE server_categories(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, name TEXT, group_name TEXT, sort_order INTEGER DEFAULT 0)")
    conn.execute("CREATE TABLE server_tasks(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,title TEXT NOT NULL,priority INTEGER DEFAULT 0,status INTEGER DEFAULT 0,category_id INTEGER,due_date TEXT,tags TEXT,raw_json TEXT,source_etag TEXT,source_modified_time TEXT,deleted_at TEXT,updated_at TEXT NOT NULL,pushed_at TEXT)")
    conn.execute("CREATE TABLE server_habits(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,name TEXT NOT NULL,icon TEXT,color TEXT,sort_order INTEGER DEFAULT 0,category_id INTEGER,difficulty TEXT,repeat_rule TEXT,is_active INTEGER DEFAULT 0,raw_json TEXT,source_etag TEXT,source_modified_time TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,pushed_at TEXT)")
    conn.execute("CREATE TABLE server_habit_checkins(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,habit_id TEXT NOT NULL,habit_name TEXT,date TEXT,created_at TEXT,checkin_date TEXT,checkin_time TEXT,status INTEGER,note TEXT,raw_json TEXT,source_modified_time TEXT,updated_at TEXT NOT NULL,pushed_at TEXT,UNIQUE(user_id,habit_id,checkin_date),FOREIGN KEY(habit_id) REFERENCES server_habits(id))")


def test_legacy_provider_tables_migrate_without_losing_owner_counts(tmp_path):
    path = tmp_path / "legacy-provider.db"
    with sqlite3.connect(path) as conn:
        _legacy_provider_tables(conn)
        conn.executemany("INSERT INTO users VALUES (?,?,?,?)", [(1, "one", "p", "now"), (4, "four", "p", "now")])
        conn.execute("INSERT INTO server_tasks(id,user_id,title,updated_at) VALUES ('a',1,'A','now')")
        conn.execute("INSERT INTO server_habits(id,user_id,name,created_at,updated_at) VALUES ('h1',4,'H','now','now')")
        conn.execute("INSERT INTO server_habit_checkins(id,user_id,habit_id,checkin_date,updated_at) VALUES ('c1',4,'h1','2026-09-06','now')")
        assert migrate_provider_mirror_identity(conn) is True
        assert migrate_provider_mirror_identity(conn) is False
        assert conn.execute("SELECT user_id,COUNT(*) FROM server_tasks GROUP BY user_id").fetchall() == [(1, 1)]
        assert conn.execute("SELECT user_id,COUNT(*) FROM server_habits GROUP BY user_id").fetchall() == [(4, 1)]
        conn.execute("INSERT INTO server_tasks(id,user_id,title,updated_at) VALUES ('a',4,'A4','now')")
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_failed_joint_parent_migration_rolls_back_old_tables(tmp_path):
    path = tmp_path / "legacy-orphan.db"
    with sqlite3.connect(path) as conn:
        _legacy_provider_tables(conn)
        conn.executemany("INSERT INTO users VALUES (?,?,?,?)", [(1, "one", "p", "now"), (4, "four", "p", "now")])
        conn.execute("INSERT INTO server_habits(id,user_id,name,created_at,updated_at) VALUES ('h1',4,'H','now','now')")
        conn.execute("INSERT INTO server_habit_checkins(id,user_id,habit_id,updated_at) VALUES ('c1',1,'h1','now')")
        with pytest.raises(RuntimeError, match="provider_mirror_foreign_key_check_failed"):
            migrate_provider_mirror_identity(conn)
        assert conn.execute("SELECT sql FROM sqlite_master WHERE name='server_habits'").fetchone()[0].count("PRIMARY KEY") == 1
        assert conn.execute("SELECT user_id,habit_id FROM server_habit_checkins").fetchall() == [(1, "h1")]
