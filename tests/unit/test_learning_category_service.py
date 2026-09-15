import sqlite3
import pytest

from server.domain.learning_category_service import LearningCategoryError, LearningCategoryService, OUTPUT_SEED_TASK_IDS
from server.domain.sample_data_initialization_service import LEARNING_TASKS
from server.models.server_schema import ensure_server_schema


def _db(tmp_path):
    path = tmp_path / "categories.db"; conn = sqlite3.connect(path); conn.row_factory = sqlite3.Row
    ensure_server_schema(conn)
    for user in (1, 3):
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(?,?,?,?)", (user, f"u{user}", "x", "2026-08-14"))
        for name in ("输入", "输出", "娱乐"):
            conn.execute("INSERT INTO server_categories(user_id,name,group_name,updated_at) VALUES(?,?,?,?)", (user, name, "测试", "2026-08-14"))
    conn.commit(); return conn


def test_resolves_account_ids_and_rejects_missing_cross_account_or_other(tmp_path):
    conn = _db(tmp_path); one = LearningCategoryService.resolve_ids(conn, 1); three = LearningCategoryService.resolve_ids(conn, 3)
    assert one != three and LearningCategoryService.validate_id(conn, 1, one["输入"]) == one["输入"]
    entertainment = conn.execute("SELECT id FROM server_categories WHERE user_id=1 AND name='娱乐'").fetchone()[0]
    for value in (None, three["输入"], entertainment):
        with pytest.raises(LearningCategoryError, match="分类"):
            LearningCategoryService.validate_id(conn, 1, value)
    conn.execute("DELETE FROM server_categories WHERE user_id=1 AND name='输出'")
    with pytest.raises(LearningCategoryError, match="配置缺失"):
        LearningCategoryService.resolve_ids(conn, 1)


def test_seed_mapping_and_repair_are_complete_idempotent_and_versioned(tmp_path):
    conn = _db(tmp_path); ids = LearningCategoryService.resolve_ids(conn, 1)
    task_ids = [task[0] for task in LEARNING_TASKS]
    assert len(task_ids) == 32 and len(OUTPUT_SEED_TASK_IDS) == 12 and set(OUTPUT_SEED_TASK_IDS) < set(task_ids)
    conn.execute("INSERT INTO server_learning_objectives(id,user_id,title,status,created_at,updated_at) VALUES('o',1,'o',0,'x','x')")
    conn.execute("INSERT INTO server_learning_krs(id,user_id,objective_id,title,target_value,current_value,created_at,updated_at) VALUES('k',1,'o','k',33,0,'x','x')")
    for task_id in task_ids:
        conn.execute("INSERT INTO server_learning_tasks(id,user_id,kr_id,title,status,created_at) VALUES(?,1,'k',?,0,'x')", (f"1:{task_id}", task_id))
    conn.execute("INSERT INTO server_learning_tasks(id,user_id,kr_id,title,status,category_id,created_at) VALUES('custom',1,'k','custom',0,NULL,'x')")
    changes = []
    changed = LearningCategoryService.repair_account(conn, 1, lambda *args: changes.append(args))
    assert changed == 33 == len(changes)
    counts = dict(conn.execute("SELECT c.name,COUNT(*) FROM server_learning_tasks t JOIN server_categories c ON c.id=t.category_id WHERE t.user_id=1 GROUP BY c.name"))
    assert counts == {"输入": 21, "输出": 12}
    assert LearningCategoryService.repair_account(conn, 1, lambda *args: changes.append(args)) == 0 and len(changes) == 33


def test_repair_skips_account_without_learning_tasks_or_categories(tmp_path):
    conn = _db(tmp_path)
    conn.execute("DELETE FROM server_categories WHERE user_id=3")
    assert LearningCategoryService.repair_account(conn, 3) == 0
