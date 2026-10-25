import sqlite3

from server.store import ServerSleepStore


def test_failed_sleep_job_lookup_is_user_and_date_scoped(tmp_path):
    path = tmp_path / "jobs.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE server_sleep_jobs "
                     "(request_id TEXT, user_id INTEGER, date TEXT, status TEXT, "
                     "image_path TEXT, updated_at TEXT, result_json TEXT)")
        conn.executemany("INSERT INTO server_sleep_jobs VALUES (?,?,?,?,?,?,?)", [
            ("owner-error", 1, "2026-10-24", "error", "retained.jpg", "2026-10-24 16:00:00", None),
            ("other-user", 2, "2026-10-24", "error", "secret.jpg", "2026-10-24 17:00:00", None),
            ("no-image", 1, "2026-10-24", "error", None, "2026-10-24 18:00:00", None),
            ("wrong-day", 1, "2026-10-23", "error", "yesterday.jpg", "2026-10-24 19:00:00", None),
        ])
    store = object.__new__(ServerSleepStore)
    store.db_path = str(path)
    assert store.get_failed_job_by_date("2026-10-24", 1)["request_id"] == "owner-error"
    assert store.get_failed_job_by_date("2026-10-24", 2)["request_id"] == "other-user"
    assert store.get_failed_job_by_date("2026-10-25", 1) is None
