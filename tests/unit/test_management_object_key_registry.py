import sqlite3

from server.domain.management_plan_service import ManagementPlanService
from server.models.server_schema import ensure_server_schema


def _setup_db(tmp_path):
    """创建隔离数据库并插入双用户基础数据"""
    path = tmp_path / "keys.db"
    conn = sqlite3.connect(path)
    ensure_server_schema(conn)
    conn.executemany("INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)", [("a", "x", "2026-08-12 08:00:00"), ("b", "x", "2026-08-12 08:00:00")])
    conn.commit()
    conn.close()

    def connect():
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        return db

    return path, connect


def test_object_key_backfill_is_stable_and_user_scoped(tmp_path):
    """回填幂等：键一旦分配不因重命名或重复回填改变，且不跨账号"""
    path, connect = _setup_db(tmp_path)
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO server_categories(user_id,name,group_name) VALUES(1,'工作','主要')")
    conn.execute("INSERT INTO server_tasks(id,user_id,title,updated_at) VALUES('task-a',1,'整理书桌','2026-08-12 08:00:00')")
    conn.execute("INSERT INTO server_habits(id,user_id,name,created_at,updated_at) VALUES('habit-a',1,'晨读','2026-08-12 08:00:00','2026-08-12 08:00:00')")
    conn.execute("INSERT INTO server_tasks(id,user_id,title,updated_at) VALUES('task-b',2,'其他账号','2026-08-12 08:00:00')")
    conn.commit()
    conn.close()

    service = ManagementPlanService(connect)
    service.ensure_object_keys(1)
    conn = sqlite3.connect(path)
    first = conn.execute("SELECT logical_key FROM server_management_object_keys WHERE user_id=1 AND domain_type='task'").fetchone()[0]
    conn.close()
    # 重命名后重新回填，键保持稳定
    conn = sqlite3.connect(path)
    conn.execute("UPDATE server_tasks SET title='整理桌面' WHERE id='task-a'")
    conn.commit()
    conn.close()
    service.ensure_object_keys(1)
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT COUNT(*) FROM server_management_object_keys WHERE user_id=1").fetchone()[0] == 3
    assert conn.execute("SELECT logical_key FROM server_management_object_keys WHERE user_id=1 AND domain_type='task'").fetchone()[0] == first
    # 键不泄漏数据库 ID
    assert "task-a" not in first
    # 跨账号隔离：user 2 未回填
    assert conn.execute("SELECT COUNT(*) FROM server_management_object_keys WHERE user_id=2").fetchone()[0] == 0
    conn.close()


def test_extended_object_key_backfill(tmp_path):
    """扩展实体（学习、运动、目标、商品）回填覆盖"""
    path, connect = _setup_db(tmp_path)
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO server_learning_objectives(id,user_id,title,status,created_at,updated_at) VALUES('obj-1',1,'AI学习',0,'2026-08-12','2026-08-12')")
    conn.execute("INSERT INTO server_learning_krs(id,user_id,objective_id,title,target_value,current_value,created_at,updated_at) VALUES('kr-1',1,'obj-1','KR1',10,0,'2026-08-12','2026-08-12')")
    conn.execute("INSERT INTO server_learning_tasks(id,user_id,kr_id,title,status,created_at,updated_at) VALUES('lt-1',1,'kr-1','学习第1课',0,'2026-08-12','2026-08-12')")
    conn.execute("INSERT INTO server_goals(id,user_id,title,metric,target_value,period,reward_coins,penalty_coins,is_active,created_at,updated_at) VALUES('goal-1',1,'日输入',':duration',4.5,'daily',0,0,1,'2026-08-12','2026-08-12')")
    conn.execute("INSERT INTO server_rewards(id,user_id,title,price,is_active,created_at,updated_at) VALUES('reward-1',1,'来一发',10,1,'2026-08-12','2026-08-12')")
    conn.execute("INSERT INTO server_exercise_plan_versions(version,user_id,title,is_active,created_at,updated_at) VALUES('v1',1,'每日打卡',1,'2026-08-12','2026-08-12')")
    conn.execute("INSERT INTO server_exercise_plan_items(id,user_id,plan_version,day_key,variant,section,sort_order,name,sets,intensity,tags_json,is_active,created_at,updated_at) VALUES('item-1',1,'v1','monday','gym','warmup',0,'卧推','3x10','medium','{}',1,'2026-08-12','2026-08-12')")
    conn.commit()
    conn.close()

    service = ManagementPlanService(connect)
    service.ensure_object_keys(1)
    conn = sqlite3.connect(path)
    rows = conn.execute("SELECT domain_type, logical_key FROM server_management_object_keys WHERE user_id=1 ORDER BY domain_type").fetchall()
    domain_types = {r[0] for r in rows}
    expected = {"learning-objective", "learning-kr", "learning-task", "goal", "store-item", "exercise-plan", "exercise-item"}
    assert expected.issubset(domain_types), f"缺失域类型: {expected - domain_types}"
    # 每个键不含数据库 ID
    for _, key in rows:
        assert "obj-1" not in key
        assert "kr-1" not in key
        assert "lt-1" not in key
        assert "goal-1" not in key
        assert "reward-1" not in key
        assert "item-1" not in key
    conn.close()


def test_cross_account_isolation(tmp_path):
    """user 1 的回填不影响 user 2，user 2 独立回填也不与 user 1 冲突"""
    path, connect = _setup_db(tmp_path)
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO server_categories(user_id,name,group_name) VALUES(1,'工作','主要')")
    conn.execute("INSERT INTO server_categories(user_id,name,group_name) VALUES(2,'学习','主要')")
    conn.commit()
    conn.close()

    service = ManagementPlanService(connect)
    service.ensure_object_keys(1)
    service.ensure_object_keys(2)
    conn = sqlite3.connect(path)
    key1 = conn.execute("SELECT logical_key FROM server_management_object_keys WHERE user_id=1 AND domain_type='category'").fetchone()[0]
    key2 = conn.execute("SELECT logical_key FROM server_management_object_keys WHERE user_id=2 AND domain_type='category'").fetchone()[0]
    assert key1 != key2, "跨账号键不应相同"
    assert conn.execute("SELECT COUNT(*) FROM server_management_object_keys WHERE user_id=1").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM server_management_object_keys WHERE user_id=2").fetchone()[0] == 1
    conn.close()


def test_logical_key_format_no_id_leak(tmp_path):
    """logical_key 格式为 domain_type.random_hex，不包含任何业务标识"""
    path, connect = _setup_db(tmp_path)
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO server_tasks(id,user_id,title,updated_at) VALUES('sensitive-task-id-123',1,'测试','2026-08-12')")
    conn.execute("INSERT INTO server_habits(id,user_id,name,created_at,updated_at) VALUES('habit-secret-456',1,'跑步','2026-08-12','2026-08-12')")
    conn.commit()
    conn.close()

    service = ManagementPlanService(connect)
    service.ensure_object_keys(1)
    conn = sqlite3.connect(path)
    rows = conn.execute("SELECT domain_type, record_id, logical_key FROM server_management_object_keys WHERE user_id=1").fetchall()
    for domain_type, record_id, logical_key in rows:
        # 键以 domain_type. 开头
        assert logical_key.startswith(f"{domain_type}."), f"键格式错误: {logical_key}"
        # 键不包含原始 record_id
        assert record_id not in logical_key, f"键泄漏了数据库 ID: {logical_key} 包含 {record_id}"
        # 键不包含 user_id
        assert "user" not in logical_key.lower()
    conn.close()
