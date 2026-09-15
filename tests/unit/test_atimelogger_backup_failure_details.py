import sqlite3

from fastapi.testclient import TestClient

from server.domain.atimelogger_backup_store import ATimeLoggerBackupStore


def test_failed_details_are_limited_to_current_user_and_keep_deleted_session(tmp_path):
    path = tmp_path / "backup.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE server_categories (id INTEGER, user_id INTEGER, name TEXT);
        CREATE TABLE server_study_sessions (id TEXT, user_id INTEGER, date TEXT, start_time TEXT, end_time TEXT, session_summary TEXT, category_id INTEGER);
        CREATE TABLE server_atimelogger_backups (id INTEGER PRIMARY KEY, user_id INTEGER, stable_session_id TEXT, sync_state TEXT, attempts INTEGER, last_error_code TEXT, last_error_step TEXT, next_retry_at TEXT, updated_at TEXT);
        INSERT INTO server_categories VALUES (1,1,'写作');
        INSERT INTO server_study_sessions VALUES ('session-1',1,'2026-08-25','09:00','10:00','周报',1);
        INSERT INTO server_atimelogger_backups VALUES (1,1,'session-1','failed',2,'remote_timeout','activity.final.stop','2026-08-25 11:00','2026-08-25 10:00');
        INSERT INTO server_atimelogger_backups VALUES (2,1,'deleted-session','unmapped',1,'category_unmapped','type.list',NULL,'2026-08-25 09:00');
        INSERT INTO server_atimelogger_backups VALUES (3,1,'login-needed','auth_required',1,'token_expired','auth.refresh',NULL,'2026-08-25 08:00');
        INSERT INTO server_atimelogger_backups VALUES (4,2,'other-user','failed',1,'hidden','hidden',NULL,'2026-08-25 12:00');
    """)
    conn.commit(); conn.close()

    def connect():
        db = sqlite3.connect(path); db.row_factory = sqlite3.Row; return db

    details = ATimeLoggerBackupStore(connect).failed_details(1)

    assert [item["stable_session_id"] for item in details] == ["session-1", "deleted-session", "login-needed"]
    assert details[0]["session_summary"] == "周报"
    assert details[1]["session_id"] is None


def test_failed_details_return_at_most_fifty_latest_rows(tmp_path):
    path = tmp_path / "backup-limit.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE server_categories (id INTEGER, user_id INTEGER, name TEXT);
        CREATE TABLE server_study_sessions (id TEXT, user_id INTEGER, date TEXT, start_time TEXT, end_time TEXT, session_summary TEXT, category_id INTEGER);
        CREATE TABLE server_atimelogger_backups (id INTEGER PRIMARY KEY, user_id INTEGER, stable_session_id TEXT, sync_state TEXT, attempts INTEGER, last_error_code TEXT, last_error_step TEXT, next_retry_at TEXT, updated_at TEXT);
    """)
    conn.executemany(
        "INSERT INTO server_atimelogger_backups VALUES (?,?,?,?,?,?,?,?,?)",
        [(index, 1, f"session-{index}", "failed", 1, "timeout", "stop", None, f"2026-08-25 12:{index:02d}") for index in range(1, 52)],
    )
    conn.commit(); conn.close()

    def connect():
        db = sqlite3.connect(path); db.row_factory = sqlite3.Row; return db

    details = ATimeLoggerBackupStore(connect).failed_details(1)

    assert len(details) == 50
    assert details[0]["stable_session_id"] == "session-51"


def test_failure_details_endpoint_rejects_anonymous_request():
    from server.server import app

    response = TestClient(app).get("/admin/provider-bindings/atimelogger/failures")

    assert response.status_code in {401, 403}
