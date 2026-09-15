import sqlite3
import pytest

from server.domain.learning_plan_service import LearningPlanService
from server.domain.management_plan_service import ManagementPlanError
from server.models.server_schema import ensure_server_schema


def test_learning_tree_is_atomic_and_user_scoped(tmp_path):
    path = tmp_path / "learning.db"
    conn = sqlite3.connect(path)
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES('learn','x','2026-08-06 02:00:00')")
    conn.execute("INSERT INTO server_categories(user_id,name,group_name) VALUES(1,'输入','增益'),(1,'输出','增益')")
    conn.commit(); conn.close()

    def connect():
        item = sqlite3.connect(path)
        item.row_factory = sqlite3.Row
        return item

    service = LearningPlanService(connect)
    result = service.apply_tree(1, {"title": "React", "krs": [{"title": "完成基础", "tasks": [{"title": "学习 hooks", "reward": 3, "category_id": 1}]}]})
    assert result["objective_id"]
    conn = connect()
    assert conn.execute("SELECT COUNT(*) FROM server_learning_objectives WHERE user_id=1").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM server_learning_tasks WHERE user_id=1 AND reward=3").fetchone()[0] == 1
    conn.close()


def test_learning_commands_update_and_delete_only_current_user(tmp_path):
    path = tmp_path / "learning-commands.db"
    conn = sqlite3.connect(path)
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES('learn','x','2026-08-06 02:00:00')")
    conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES('other','x','2026-08-06 02:00:00')")
    conn.execute("INSERT INTO server_categories(user_id,name,group_name) VALUES(1,'输入','增益'),(1,'输出','增益'),(2,'输入','增益'),(2,'输出','增益')")
    conn.commit(); conn.close()

    def connect():
        item = sqlite3.connect(path)
        item.row_factory = sqlite3.Row
        return item

    service = LearningPlanService(connect)
    objective = service.command(1, {"action": "create_objective", "title": "命令化学习"})
    kr = service.command(1, {"action": "create_kr", "objective_id": objective["objective_id"], "title": "完成第一阶段"})
    task = service.command(1, {"action": "create_task", "kr_id": kr["kr_id"], "title": "完成服务端迁移", "reward": 5, "category_id": 1})
    assert service.command(1, {"action": "toggle_task", "id": task["task_id"]})["status"] == 2
    conn = connect()
    assert conn.execute("SELECT current_value FROM server_learning_krs WHERE id=? AND user_id=1", (kr["kr_id"],)).fetchone()[0] == 1
    conn.close()
    service.command(1, {"action": "delete_objective", "id": objective["objective_id"]})
    conn = connect()
    assert conn.execute("SELECT COUNT(*) FROM server_learning_tasks WHERE user_id=1").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM server_learning_objectives WHERE user_id=2").fetchone()[0] == 0
    conn.close()


def test_invalid_learning_category_rolls_back_whole_tree(tmp_path):
    path = tmp_path / "invalid-learning.db"; conn = sqlite3.connect(path); ensure_server_schema(conn)
    conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES('learn','x','2026-08-14')")
    conn.execute("INSERT INTO server_categories(user_id,name,group_name) VALUES(1,'输入','增益'),(1,'输出','增益'),(1,'娱乐','生活')")
    conn.commit(); conn.close()
    def connect():
        item = sqlite3.connect(path); item.row_factory = sqlite3.Row; return item
    service = LearningPlanService(connect)
    with pytest.raises(ManagementPlanError) as error:
        service.apply_tree(1, {"title": "非法树", "krs": [{"title": "KR", "tasks": [{"title": "合法", "category_id": 1}, {"title": "非法", "category_id": 3}]}]})
    assert error.value.code == "invalid_learning_category"
    conn = connect()
    assert conn.execute("SELECT COUNT(*) FROM server_learning_objectives").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM server_learning_tasks").fetchone()[0] == 0
    conn.close()


def test_set_task_status_is_idempotent_reversible_and_user_scoped(tmp_path):
    path = tmp_path / "learning-status.db"; conn = sqlite3.connect(path); ensure_server_schema(conn)
    conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'learn','x','2026-08-15'),(2,'other','x','2026-08-15')")
    conn.execute("INSERT INTO server_categories(user_id,name,group_name) VALUES(1,'输入','增益'),(2,'输入','增益')")
    conn.commit(); conn.close()
    def connect():
        item = sqlite3.connect(path); item.row_factory = sqlite3.Row; return item
    service = LearningPlanService(connect)
    objective = service.command(1, {"action": "create_objective", "title": "状态"})
    kr = service.command(1, {"action": "create_kr", "objective_id": objective["objective_id"], "title": "KR"})
    task = service.command(1, {"action": "create_task", "kr_id": kr["kr_id"], "title": "任务", "category_id": 1})
    assert service.command(1, {"action": "set_task_status", "id": task["task_id"], "status": 2})["status"] == 2
    assert service.command(1, {"action": "set_task_status", "id": task["task_id"], "status": 2})["status"] == 2
    assert service.command(1, {"action": "set_task_status", "id": task["task_id"], "status": 0})["status"] == 0
    with pytest.raises(ManagementPlanError, match="状态无效"):
        service.command(1, {"action": "set_task_status", "id": task["task_id"], "status": 1})
    with pytest.raises(ManagementPlanError, match="不存在"):
        service.command(2, {"action": "set_task_status", "id": task["task_id"], "status": 2})
    with connect() as check:
        assert check.execute("SELECT current_value FROM server_learning_krs WHERE id=?", (kr["kr_id"],)).fetchone()[0] == 0
