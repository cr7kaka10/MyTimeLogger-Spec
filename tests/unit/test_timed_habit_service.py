from datetime import datetime, timedelta, timezone

import pytest

from server.domain.timed_habit_service import TimedHabitService
from server.store import ServerSleepStore


TZ = timezone(timedelta(hours=8))
DAY = "2026-11-02"


def test_window_boundaries_finality_and_auto_failure(tmp_path):
    store = ServerSleepStore(str(tmp_path / "timed.db"))
    store.create_user("timed@example.test", "password")
    with store._transact() as conn:
        for name in ("done", "missed"):
            conn.execute("""INSERT INTO server_habits(id,user_id,name,source,is_active,created_at,updated_at)
                VALUES(?,1,?,'local',0,'2026-11-01','2026-11-01')""", (name, name))
            conn.execute("""INSERT INTO server_habit_windows(id,user_id,habit_id,effective_from,start_minute,end_minute,created_at,updated_at)
                VALUES(?,1,?,'2026-11-02',480,600,'2026-11-01','2026-11-01')""", (name, name))
            conn.execute("INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty) VALUES(1,'habit',?,1,0)", (name,))
    clock = ["2026-11-02 07:59:00"]
    store.habit_domain_service._now = lambda: clock[0]
    with pytest.raises(ValueError, match="timed_habit_before_window"):
        store.checkin_habit(1, "done", DAY)
    clock[0] = "2026-11-02 08:00:00"
    assert store.checkin_habit(1, "done", DAY)
    clock[0] = "2026-11-02 09:59:00"
    assert store.checkin_habit(1, "done", DAY)
    with pytest.raises(ValueError, match="timed_habit_immutable"):
        store.cancel_checkin_habit(1, "done", DAY)
    scanner = TimedHabitService(store._transact, store.habit_domain_service,
        now_fn=lambda: datetime.fromisoformat(clock[0]).replace(tzinfo=TZ))
    assert scanner.run(1) == set()
    clock[0] = "2026-11-02 10:00:00"
    assert scanner.run(1) == {1}
    assert scanner.run(1) == set()
    with pytest.raises(ValueError, match="timed_habit_final"):
        store.checkin_habit(1, "missed", DAY)
    with store._connect() as conn:
        assert [(r[0], r[1]) for r in conn.execute("SELECT habit_id,status FROM server_habit_checkins WHERE user_id=1 ORDER BY habit_id")] == [("done", 2), ("missed", 1)]
