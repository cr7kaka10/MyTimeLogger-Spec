import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

from server.domain.session_business_date_repair import audit_cross_day_session_dates, repair_cross_day_session_dates
from server.db_wrapper import ServerDBWrapper
from server.models.server_schema import ensure_server_schema
from server.sync_hub import SyncHub


BEIJING = timezone(timedelta(hours=8))


def test_repair_is_auditable_idempotent_and_keeps_session_identity(tmp_path):
    path = tmp_path / "repair.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES (1,'u','x','now')")
    conn.execute(
        "INSERT INTO server_study_sessions (id,user_id,start_time,end_time,net_duration_minutes,net_duration_seconds,date,day_of_week,pause_count,pause_reasons,session_summary,category_id,updated_at) "
        "VALUES ('sleep',1,'2026-08-30 22:30:00+08:00','2026-08-31 08:30:00+08:00',600,36000,'2026-08-30','星期日',2,'[]','keep',NULL,'old')"
    )
    conn.commit()
    conn.close()

    def connect():
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        return db

    assert audit_cross_day_session_dates(connect()) == [{"id": "sleep", "user_id": 1, "old_date": "2026-08-30", "date": "2026-08-31"}]
    assert repair_cross_day_session_dates(connect, apply=False) == [{"id": "sleep", "user_id": 1, "old_date": "2026-08-30", "date": "2026-08-31"}]
    assert repair_cross_day_session_dates(connect, apply=True, now=lambda: datetime(2026, 8, 31, 9, tzinfo=BEIJING))
    assert repair_cross_day_session_dates(connect, apply=True) == []

    conn = connect()
    session = conn.execute("SELECT id,start_time,end_time,net_duration_seconds,date,day_of_week,pause_count,session_summary FROM server_study_sessions").fetchone()
    change = conn.execute("SELECT server_version,record_id,changed_fields_json FROM server_change_log").fetchone()
    conn.close()
    assert tuple(session) == ('sleep', '2026-08-30 22:30:00+08:00', '2026-08-31 08:30:00+08:00', 36000, '2026-08-31', '星期一', 2, 'keep')
    assert (change['server_version'], change['record_id']) == (1, 'sleep')
    assert '2026-08-31' in change['changed_fields_json']

    wrapper = ServerDBWrapper()
    wrapper.log_path = str(path)
    pc_pull = asyncio.run(SyncHub(wrapper).handle_pull_by_version(0, user_id=1))
    android_pull = asyncio.run(SyncHub(wrapper).handle_pull_by_version(0, user_id=1))
    for pull in (pc_pull, android_pull):
        sessions = pull['tables']['study_sessions']
        assert [(row['id'], row['date']) for row in sessions] == [('sleep', '2026-08-31')]
