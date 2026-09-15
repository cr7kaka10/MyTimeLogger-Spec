import sqlite3

from server.db_wrapper import ServerDBWrapper
from server.domain.reward_config_service import RewardConfigService
from server.models.server_schema import ensure_server_schema
from server.store import ServerSleepStore


def _connection():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES('a','x','2026-08-09 12:00:00')")
    conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES('b','x','2026-08-09 12:00:00')")
    return conn


def test_materialize_user_creates_explicit_defaults_without_overwriting_existing_rules():
    conn = _connection()
    now = "2026-08-09 12:00:00"
    conn.execute("INSERT INTO server_tasks(id,user_id,title,status,updated_at) VALUES('task',1,'任务',0,?)", (now,))
    conn.execute("INSERT INTO server_habits(id,user_id,name,difficulty,is_active,created_at,updated_at) VALUES('habit',1,'习惯','hard',1,?,?)", (now, now))
    conn.execute("INSERT INTO server_learning_tasks(id,user_id,kr_id,title,status,reward,created_at,updated_at) VALUES('learning',1,'kr','学习',0,3,?,?)", (now, now))
    conn.execute("INSERT INTO server_exercise_plan_items(id,user_id,plan_version,day_key,variant,section,sort_order,name,is_active,created_at,updated_at) VALUES('exercise',1,'v1','mon','default','力量',0,'运动',1,?,?)", (now, now))
    conn.execute("INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty,updated_at) VALUES(1,'task','task',9,8,?)", (now,))
    conn.commit()

    service = RewardConfigService()
    assert service.materialize_user(conn, 1) == 3
    assert service.materialize_user(conn, 1) == 0
    rules = {(row["item_type"], row["item_id"]): (row["coins"], row["penalty"]) for row in conn.execute("SELECT item_type,item_id,coins,penalty FROM server_reward_config WHERE user_id=1")}
    assert rules == {("task", "task"): (9.0, 8.0), ("habit", "habit"): (5.0, 5.0), ("learning", "learning"): (3.0, 3.0), ("exercise", "exercise"): (1.0, 1.0)}
    assert conn.execute("SELECT COUNT(*) FROM server_reward_config WHERE user_id=2").fetchone()[0] == 0


def test_require_rejects_missing_config_without_default_value():
    conn = _connection()
    try:
        RewardConfigService.require(conn, 1, "task", "missing")
    except Exception as error:
        assert str(error) == "reward_config_missing:task:missing"
    else:
        raise AssertionError("missing config must not receive a default")


def test_task_sync_and_manual_habit_creation_write_explicit_rules(tmp_path):
    db_path = str(tmp_path / "rewards.db")
    store = ServerSleepStore(db_path)
    assert store.create_user("owner", "password")
    user_id = store.verify_user("owner", "password")
    task_db = ServerDBWrapper(db_path)
    assert task_db.upsert_task(user_id, {"id": "task-new", "title": "新任务", "priority": 0, "status": 0, "tags": []})
    habit_id = store.create_habit(user_id, "新习惯", difficulty="hard")

    conn = sqlite3.connect(db_path)
    rows = {(item_type, item_id): (coins, penalty) for item_type, item_id, coins, penalty in conn.execute("SELECT item_type,item_id,coins,penalty FROM server_reward_config WHERE user_id=?", (user_id,))}
    assert rows[("task", "task-new")] == (0.1, 0.1)
    assert rows[("habit", habit_id)] == (5.0, 5.0)
