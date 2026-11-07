import pytest

import server.store as store_module
from server.store import ServerSleepStore


def test_window_edit_takes_effect_next_beijing_day(tmp_path, monkeypatch):
    store = ServerSleepStore(str(tmp_path / "window-edit.db"))
    store.create_user("window@example.test", "password")
    with store._transact() as conn:
        conn.execute("""INSERT INTO server_habits(id,user_id,name,source,is_active,created_at,updated_at)
            VALUES('h',1,'习惯','local',0,'2026-10-01','2026-10-01')""")
    monkeypatch.setattr(store_module, "now_str", lambda: "2026-11-01 08:30:00")
    result = store.set_habit_window(1, "h", 480, 600)
    assert result["effective_from"] == "2026-11-02"
    store.habit_domain_service._now = lambda: "2026-11-01 07:59:00"
    with store._connect() as conn:
        assert store.habit_domain_service.timed_checkin_guard(conn, 1, "h", "2026-11-01", 2) is None
        with pytest.raises(ValueError, match="timed_habit_wrong_day"):
            store.habit_domain_service.timed_checkin_guard(conn, 1, "h", "2026-11-02", 2)
