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


def test_kr_edit_delete_is_scoped_atomic_and_preserves_checklist(tmp_path):
    path = tmp_path / "kr-edit-delete.db"
    conn = sqlite3.connect(path); ensure_server_schema(conn)
    conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'owner','x','2026-11-06'),(2,'other','x','2026-11-06')")
    conn.execute("INSERT INTO server_categories(user_id,name,group_name) VALUES(1,'输入','增益')")
    conn.commit(); conn.close()
    def connect():
        db = sqlite3.connect(path); db.row_factory = sqlite3.Row; return db
    changes, fail_delete = [], [False]
    def record_change(_conn, _user, table, record_id, operation, _fields):
        changes.append((table, record_id, operation))
        if fail_delete[0] and table == "server_learning_krs" and operation == "delete":
            raise RuntimeError("simulated sync log failure")
    service = LearningPlanService(connect, record_change)
    objective = service.command(1, {"action": "create_objective", "title": "博客"})["objective_id"]
    kr = service.command(1, {"action": "create_kr", "objective_id": objective, "title": "重复"})["kr_id"]
    task = service.command(1, {"action": "create_task", "kr_id": kr, "title": "写文章", "category_id": 1})["task_id"]
    conn = connect()
    conn.execute("INSERT INTO server_tasks(id,user_id,title,updated_at) VALUES('checklist-1',1,'独立清单','2026-11-06')")
    conn.execute("INSERT INTO server_learning_checklist_links(user_id,learning_task_id,checklist_task_id,created_at) VALUES(1,?, 'checklist-1','2026-11-06')", (task,))
    conn.commit(); conn.close()
    assert service.command(1, {"action": "update_kr", "id": kr, "title": "  正确标题  "})["title"] == "正确标题"
    for user_id, payload in [(1, {"action": "update_kr", "id": kr, "title": " "}), (2, {"action": "update_kr", "id": kr, "title": "越权"}), (2, {"action": "delete_kr", "id": kr})]:
        with pytest.raises(ManagementPlanError): service.command(user_id, payload)
    fail_delete[0] = True
    with pytest.raises(RuntimeError): service.command(1, {"action": "delete_kr", "id": kr})
    conn = connect()
    assert conn.execute("SELECT COUNT(*) FROM server_learning_tasks WHERE id=?", (task,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM server_learning_krs WHERE id=?", (kr,)).fetchone()[0] == 1
    conn.close()
    fail_delete[0] = False
    assert service.command(1, {"action": "delete_kr", "id": kr})["deleted_tasks"] == 1
    conn = connect()
    for table in ("server_learning_tasks", "server_learning_krs", "server_learning_checklist_links"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=1").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM server_tasks WHERE id='checklist-1'").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM server_reward_config WHERE item_type='learning' AND item_id=?", (task,)).fetchone()[0] == 0
    conn.close()
    assert ("server_learning_krs", kr, "upsert") in changes
    assert ("server_learning_tasks", task, "delete") in changes
    assert ("server_learning_krs", kr, "delete") in changes


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
