import asyncio
import sqlite3

from tests.unit.test_sync_conflict_policies import _hub


def test_legacy_push_cannot_rewrite_timed_habit_final_state(tmp_path):
    db_path, hub = _hub(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute("""INSERT INTO server_habits(id,user_id,name,source,is_active,created_at,updated_at)
            VALUES('local_timed',1,'定时习惯','local',0,'2026-10-31','2026-10-31')""")
        conn.execute("""INSERT INTO server_habit_windows(id,user_id,habit_id,effective_from,start_minute,end_minute,created_at,updated_at)
            VALUES('w',1,'local_timed','2026-11-01',480,600,'2026-10-31','2026-10-31')""")
        conn.execute("""INSERT INTO server_habit_checkins(id,user_id,habit_id,date,checkin_date,status,created_at,updated_at)
            VALUES('final',1,'local_timed','2026-11-01','2026-11-01',2,'2026-11-01','2026-11-01')""")
    for status in (0, 1, 2):
        result = asyncio.run(hub.handle_push([{
            "table": "habit_checkins", "change_id": f"legacy-{status}", "operation": "upsert",
            "payload": {"id": "final", "habit_id": "local_timed", "checkin_date": "2026-11-01",
                        "status": status, "updated_at": "2026-11-01 12:00:00"},
        }], user_id=1))
        assert result["accepted"] == 0
        assert result["operation_results"][0]["reason"] == "server_authoritative_habit_checkin_command_required"
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT status FROM server_habit_checkins WHERE id='final'").fetchone()[0] == 2
