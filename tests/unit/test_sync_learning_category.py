import sqlite3

from server.db_wrapper import ServerDBWrapper
from server.models.server_schema import ensure_server_schema
from server.sync_hub import SyncHub


def test_sync_rejects_invalid_learning_category_and_preserves_server_record(tmp_path):
    path = tmp_path / "learning-sync.db"; conn = sqlite3.connect(path); ensure_server_schema(conn)
    conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u1','x','x'),(2,'u2','x','x')")
    conn.execute("INSERT INTO server_categories(user_id,name,group_name) VALUES(1,'输入','增益'),(1,'输出','增益'),(1,'娱乐','生活'),(2,'输入','增益'),(2,'输出','增益')")
    conn.execute("INSERT INTO server_learning_objectives(id,user_id,title,status,created_at) VALUES('o',1,'目标',0,'x')")
    conn.execute("INSERT INTO server_learning_krs(id,user_id,objective_id,title,target_value,current_value,created_at) VALUES('k',1,'o','关键结果',1,0,'x')")
    conn.execute("INSERT INTO server_learning_tasks(id,user_id,kr_id,title,status,category_id,created_at) VALUES('t',1,'k','原任务',0,1,'x')")
    conn.commit(); conn.close()
    wrapper = ServerDBWrapper(); wrapper.log_path = str(path); hub = SyncHub(wrapper)
    for category_id in (None, 3, 4):
        ok, rejected = hub.upsert("learning_tasks", {"id": "t", "title": "污染", "category_id": category_id}, 1)
        assert not ok and rejected[0]["reason"] == "invalid_learning_category"
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT title,category_id FROM server_learning_tasks WHERE id='t'").fetchone() == ("原任务", 1)
