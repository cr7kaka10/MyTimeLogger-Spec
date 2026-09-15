import sqlite3
import pytest
from server.domain.management_plan_service import ManagementPlanService
from server.domain.management_bundle_schema import BUNDLE_SCHEMA_ID, BUNDLE_VERSION
from server.models.server_schema import ensure_server_schema
from typing import Callable

def _setup_db(tmp_path) -> tuple[str, Callable[[], sqlite3.Connection]]:
    db_path = tmp_path / "test.db"
    def connect():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    conn = connect(); ensure_server_schema(conn); now = "2026-08-12 20:00:00"
    conn.executemany("INSERT INTO users(id,username,password_hash,created_at) VALUES(?,?,?,?)", [(1,"u1","x",now),(2,"u2","x",now)])
    conn.executemany("INSERT INTO server_categories(id,user_id,name,group_name,icon,color,sort_order,updated_at) VALUES(?,?,?,?,?,?,?,?)", [(1,1,"工作","默认","💼","#FF0000",1,now),(2,2,"生活","默认","🏠","#00FF00",1,now)])
    conn.execute("INSERT INTO server_tasks(id,user_id,title,category_id,priority,status,updated_at) VALUES('10',1,'写代码',1,3,0,?)", (now,))
    conn.execute("INSERT INTO server_habits(id,user_id,name,category_id,is_active,created_at,updated_at) VALUES('20',1,'喝水',1,1,?,?)", (now,now))
    conn.execute("INSERT INTO server_learning_objectives(id,user_id,title,status,created_at,updated_at) VALUES('obj1',1,'学AI',0,?,?)", (now,now))
    conn.execute("INSERT INTO server_learning_krs(id,user_id,objective_id,title,target_value,created_at,updated_at) VALUES('kr1',1,'obj1','10小时',10,?,?)", (now,now))
    conn.execute("INSERT INTO server_learning_tasks(id,user_id,kr_id,title,status,created_at,updated_at) VALUES('lt1',1,'kr1','看视频',0,?,?)", (now,now))
    conn.execute("INSERT INTO server_exercise_plan_versions(version,user_id,title,is_active,created_at,updated_at) VALUES('v1',1,'力量训练',1,?,?)", (now,now))
    conn.execute("INSERT INTO server_exercise_plan_items(id,user_id,plan_version,day_key,variant,section,sort_order,name,sets,intensity,tags_json,is_active,created_at,updated_at) VALUES('eitem1',1,'v1','monday','gym','warmup',1,'跑步','10min','low','[]',1,?,?)", (now,now))
    conn.execute("INSERT INTO server_goals(id,user_id,title,category_id,metric,target_value,period,reward_coins,penalty_coins,reward_id,is_active,created_at,updated_at) VALUES('g1',1,'每日写代码',1,'duration',2,'daily',10,0,'r1',1,?,?)", (now,now))
    conn.execute("INSERT INTO server_rewards(id,user_id,title,price,unlock_source_type,unlock_source_id,is_active,created_at,updated_at) VALUES('r1',1,'买杯咖啡',15,'goal','g1',1,?,?)", (now,now))

    conn.commit()
    conn.close()
    return str(db_path), connect


def test_export_bundle_full_matrix(tmp_path):
    _, connect = _setup_db(tmp_path)
    service = ManagementPlanService(connect)
    
    # 1. Export Bundle
    bundle = service.export_bundle(user_id=1)
    
    assert bundle["schema"] == BUNDLE_SCHEMA_ID
    assert bundle["version"] == BUNDLE_VERSION
    assert "nodes" in bundle
    assert "relations" in bundle
    assert "unresolved_relations" in bundle
    
    nodes = bundle["nodes"]
    relations = bundle["relations"]
    
    # 2. Check types matrix
    types_found = set(n["type"] for n in nodes)
    assert "category" in types_found
    assert "task" in types_found
    assert "habit" in types_found
    assert "learning-objective" in types_found
    assert "learning-kr" in types_found
    assert "learning-task" in types_found
    assert "exercise-plan" in types_found
    assert "exercise-item" in types_found
    assert "goal" in types_found
    assert "store-item" in types_found
    
    # 3. Check archived object
    habit = next(n for n in nodes if n["type"] == "habit")
    assert habit["status"] == "archived"
    
    # 4. Check relations
    rel_types = set(r["type"] for r in relations)
    assert "child_of" in rel_types
    assert "binds" in rel_types
    assert "rewards" in rel_types
    assert "unlocks" in rel_types
    
    # 5. Check unresolved relations (dirty relations)
    # User 1 has no missing relations natively, let's inject a dangling relation
    conn = connect()
    # Add a goal pointing to a non-existent category
    conn.execute("INSERT INTO server_goals(id,user_id,title,category_id,metric,target_value,period,reward_coins,penalty_coins,reward_id,is_active,created_at,updated_at) VALUES('g2',1,'坏目标',999,'duration',2,'daily',10,0,NULL,1,'2026-08-12 20:00:00','2026-08-12 20:00:00')")
    conn.commit()
    conn.close()
    
    bundle2 = service.export_bundle(user_id=1)
    unresolved = bundle2["unresolved_relations"]
    assert any(u["type"] == "binds" and u["target_key"] == "category.999" for u in unresolved)

    # 6. Cross Account Isolation
    bundle_u2 = service.export_bundle(user_id=2)
    assert len(bundle_u2["nodes"]) == 1
    assert bundle_u2["nodes"][0]["type"] == "category"
    assert bundle_u2["nodes"][0]["data"]["name"] == "生活"

    # 7. Secure Exclusions
    # Ensure id/user_id are absent in nodes
    for n in bundle["nodes"]:
        assert "user_id" not in n["data"]
        assert "id" not in n["data"]
        assert "raw_json" not in n["data"]


def test_export_bundle_uses_production_task_schema(tmp_path):
    db_path = tmp_path / "production-schema.db"
    conn = sqlite3.connect(db_path)
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','x','2026-08-12 18:00:00')")
    conn.execute("INSERT INTO server_categories(id,user_id,name,group_name,icon,color,sort_order,updated_at) VALUES(1,1,'工作','默认','','#fff',1,'2026-08-12 18:00:00')")
    conn.execute("INSERT INTO server_tasks(id,user_id,title,priority,status,category_id,updated_at) VALUES('task-1',1,'写代码',3,0,1,'2026-08-12 18:00:00')")
    conn.commit(); conn.close()

    def connect():
        result = sqlite3.connect(db_path); result.row_factory = sqlite3.Row
        return result

    bundle = ManagementPlanService(connect).export_bundle(1)
    task = next(node for node in bundle["nodes"] if node["type"] == "task")
    assert task["data"]["title"] == "写代码"
