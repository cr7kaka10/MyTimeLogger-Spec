import sqlite3

from server.domain.sample_data_initialization_service import SampleDataInitializationService
from server.store import ServerSleepStore


def _user_with_categories(db_path, email):
    store = ServerSleepStore(db_path)
    assert store.create_user(email, "password")
    user_id = store.verify_user(email, "password")
    service = SampleDataInitializationService(db_path)
    assert not service.ensure_user_sample_data(user_id)
    return user_id, service


def _marker(conn, user_id):
    return conn.execute("SELECT COUNT(*) FROM server_sample_data_initializations WHERE user_id=? AND module='store_rewards'", (user_id,)).fetchone()[0]


def test_existing_store_is_preserved_and_missing_or_ambiguous_habits_stay_pending(tmp_db_path):
    existing, service = _user_with_categories(tmp_db_path, "existing@example.com")
    pending, _ = _user_with_categories(tmp_db_path, "pending@example.com")
    with sqlite3.connect(tmp_db_path) as conn:
        conn.execute("INSERT INTO server_rewards (id, user_id, title, price, created_at, updated_at) VALUES ('existing', ?, '自定义商品', 1, '2026-08-04', '2026-08-04')", (existing,))
        conn.execute("INSERT INTO server_habits (id, user_id, name, is_active, created_at, updated_at) VALUES ('brush', ?, '刷牙', 0, '2026-08-04', '2026-08-04')", (pending,))
    assert not service.ensure_user_sample_data(existing)
    assert not service.ensure_user_sample_data(pending)
    with sqlite3.connect(tmp_db_path) as conn:
        conn.executemany("INSERT INTO server_habits (id, user_id, name, is_active, created_at, updated_at) VALUES (?, ?, '洗脸', 0, '2026-08-04', '2026-08-04')", [("face-a", pending), ("face-b", pending)])
    assert not service.ensure_user_sample_data(pending)
    with sqlite3.connect(tmp_db_path) as conn:
        assert _marker(conn, existing) == 1 and conn.execute("SELECT COUNT(*) FROM server_rewards WHERE user_id=?", (existing,)).fetchone()[0] == 1
        assert _marker(conn, pending) == 0 and conn.execute("SELECT COUNT(*) FROM server_rewards WHERE user_id=?", (pending,)).fetchone()[0] == 0
        conn.execute("DELETE FROM server_habits WHERE id='face-b'")
    assert service.ensure_user_sample_data(pending)
    with sqlite3.connect(tmp_db_path) as conn:
        assert _marker(conn, pending) == 1 and conn.execute("SELECT COUNT(*) FROM server_rewards WHERE user_id=?", (pending,)).fetchone()[0] == 5
        assert conn.execute("SELECT COUNT(*) FROM server_rewards WHERE user_id=? AND is_active=1", (pending,)).fetchone()[0] == 3
