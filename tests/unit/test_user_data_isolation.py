import sqlite3

from server.models.server_schema import ensure_server_schema


def _connection(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'alice','x','2026-09-01'),(2,'bob','x','2026-09-01')")
    conn.execute("INSERT INTO server_categories(id,user_id,name,icon,color,group_name,sort_order,updated_at) VALUES(101,1,'工作','briefcase','#f00','默认',1,'x'),(201,2,'工作','briefcase','#0f0','默认',1,'x')")
    conn.execute("INSERT INTO server_study_sessions(id,user_id,category_id,start_time,end_time,net_duration_minutes,date,updated_at) VALUES('a',1,101,'2026-09-01 09:00:00','2026-09-01 10:00:00',60,'2026-09-01','x'),('b',2,201,'2026-09-01 09:00:00','2026-09-01 10:00:00',60,'2026-09-01','x')")
    conn.commit()
    return conn


def test_user_owned_tables_and_same_name_records_are_isolated(tmp_path):
    conn = _connection(tmp_path / "isolated.db")
    for table in ("server_categories", "server_study_sessions", "server_huawei_sleep_data", "server_atm_summary", "server_flash_skill_evaluations"):
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        assert "user_id" in columns
    assert [row["id"] for row in conn.execute("SELECT id FROM server_categories WHERE user_id=?", (1,))] == [101]
    assert [row["id"] for row in conn.execute("SELECT id FROM server_study_sessions WHERE user_id=?", (2,))] == ["b"]
    assert conn.execute("UPDATE server_categories SET name='串号' WHERE id=? AND user_id=?", (201, 1)).rowcount == 0
    assert conn.execute("SELECT name FROM server_categories WHERE id=201").fetchone()[0] == "工作"
    conn.close()
