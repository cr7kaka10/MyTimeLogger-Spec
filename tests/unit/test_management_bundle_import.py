import sqlite3
import pytest
import json
from server.domain.management_plan_service import ManagementPlanService
from server.models.server_schema import ensure_server_schema

def _setup_db(tmp_path):
    db_path = tmp_path / "test_import.db"
    def connect():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn
    
    conn = connect(); ensure_server_schema(conn)
    conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','x','2026-08-12 20:00:00')")
    
    conn.commit()
    conn.close()
    return connect


def test_preview_bundle(tmp_path):
    connect = _setup_db(tmp_path)
    service = ManagementPlanService(connect)
    
    # Empty current bundle
    current_bundle = {"nodes": [], "relations": []}
    
    incoming_bundle = {
        "nodes": [
            {"logical_key": "category.new", "type": "category", "status": "active", "data": {"name": "Test Cat"}},
            {"logical_key": "task.new", "type": "task", "status": "active", "data": {"name": "Test Task"}}
        ],
        "relations": [
            {"source_key": "task.new", "target_key": "category.new", "type": "child_of"}
        ]
    }
    
    preview = service.preview_bundle(1, "merge", incoming_bundle, current_bundle)
    
    assert len(preview["nodes"]) == 2
    assert preview["nodes"][0]["action"] == "add"
    assert preview["nodes"][1]["action"] == "add"
    assert len(preview["relations"]) == 1
    assert preview["relations"][0]["action"] == "add"


def test_apply_bundle_idempotency_and_write(tmp_path):
    connect = _setup_db(tmp_path)
    service = ManagementPlanService(connect)
    
    incoming_bundle = {
        "schema": "mytimelogger.management-bundle",
        "version": 1,
        "nodes": [
            {"logical_key": "category.c1", "type": "category", "status": "active", "data": {"name": "New Cat"}},
            {"logical_key": "task.t1", "type": "task", "status": "active", "data": {"name": "New Task"}}
        ],
        "relations": [
            {"source_key": "task.t1", "target_key": "category.c1", "type": "child_of"}
        ]
    }
    
    # 1. Apply bundle
    rev_id1 = service.apply_bundle(1, "idem-1", incoming_bundle, "merge")
    assert rev_id1 is not None
    
    # 2. Check DB
    conn = connect()
    cats = conn.execute("SELECT * FROM server_categories").fetchall()
    assert len(cats) == 1
    assert cats[0]["name"] == "New Cat"
    
    tasks = conn.execute("SELECT * FROM server_tasks").fetchall()
    assert len(tasks) == 1
    assert tasks[0]["title"] == "New Task"
    assert tasks[0]["category_id"] == cats[0]["id"]
    
    # Check Revision & Binding
    revs = conn.execute("SELECT * FROM server_management_plan_revisions").fetchall()
    assert len(revs) == 1
    assert revs[0]["id"] == rev_id1
    
    bindings = conn.execute("SELECT * FROM server_management_plan_bindings WHERE revision_id=?", (rev_id1,)).fetchall()
    assert len(bindings) == 2
    
    conn.close()
    
    # 3. Test Idempotency (Applying same ID again returns same revision_id)
    rev_id2 = service.apply_bundle(1, "idem-1", incoming_bundle, "merge")
    assert rev_id1 == rev_id2
    
    # 4. Test Error Rollback
    bad_bundle = {
        "schema": "mytimelogger.management-bundle",
        "version": 1,
        "nodes": [
            # Missing logical_key which will raise KeyError if not careful or schema error
            {"type": "category", "status": "active", "data": {"name": "Fail Cat"}}
        ],
        "relations": []
    }
    with pytest.raises(Exception):
        service.apply_bundle(1, "idem-2", bad_bundle, "merge")
        
    # Check that DB is not polluted
    conn = connect()
    cats = conn.execute("SELECT * FROM server_categories").fetchall()
    assert len(cats) == 1  # Still 1
    conn.close()
