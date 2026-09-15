import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

from server.db_wrapper import ServerDBWrapper
from server.domain.session_category_reference_repair import repair_invalid_session_category_references
from server.models.server_schema import ensure_server_schema
from server.sync_hub import SyncHub

BEIJING = timezone(timedelta(hours=8))

def test_repairs_only_provable_category_references_once_and_pulls_them(tmp_path):
    path = tmp_path / "category-repair.db"; conn = sqlite3.connect(path); conn.row_factory = sqlite3.Row; ensure_server_schema(conn)
    conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES (1,'u','x','now')")
    conn.execute("INSERT INTO server_categories(id,user_id,name,group_name,updated_at) VALUES (47,1,'工作','默认','now')")
    for session_id, category_id in (("recover", 16), ("keep", 17)):
        conn.execute("INSERT INTO server_study_sessions(id,user_id,start_time,end_time,net_duration_minutes,date,updated_at,category_id) VALUES (?,?, 'now','now',1,'2026-08-31','old',?)", (session_id, 1, category_id))
    conn.execute("INSERT INTO live_timer_segments(segment_id,user_id,session_id,category_name,started_at,created_at) VALUES ('last',1,'recover','工作','2026-08-31 10:00:00+08:00','now')")
    before = conn.execute("SELECT * FROM server_study_sessions WHERE id='keep'").fetchone(); conn.commit(); conn.close()
    def connect():
        db = sqlite3.connect(path); db.row_factory = sqlite3.Row; return db
    findings = repair_invalid_session_category_references(connect, apply=True, now=lambda: datetime(2026, 8, 31, 11, tzinfo=BEIJING))
    assert [(item["id"], item.get("category_id")) for item in findings] == [("keep", None), ("recover", 47)]
    assert repair_invalid_session_category_references(connect, apply=True) == [{"id": "keep", "user_id": 1, "old_category_id": 17, "category_name": "", "reason": "missing_or_ambiguous_segment_category"}]
    conn = connect(); assert conn.execute("SELECT category_id FROM server_study_sessions WHERE id='recover'").fetchone()[0] == 47
    assert tuple(conn.execute("SELECT * FROM server_study_sessions WHERE id='keep'").fetchone()) == tuple(before)
    assert conn.execute("SELECT COUNT(*) FROM server_change_log WHERE record_id='recover'").fetchone()[0] == 1; conn.close()
    db = ServerDBWrapper(); db.log_path = str(path)
    pull = asyncio.run(SyncHub(db).handle_pull_by_version(0, user_id=1))
    assert [row for row in pull["tables"]["study_sessions"] if row["id"] == "recover"][0]["category_id"] == 47
