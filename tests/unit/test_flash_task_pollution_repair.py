import json

import pytest

from server.domain.flash_task_pollution_repair import (
    POLLUTED_FLASH_TASKS,
    FlashTaskPollutionRepairService,
)
from server.store import ServerSleepStore


def _fixture(tmp_path):
    store = ServerSleepStore(str(tmp_path / "flash-pollution.db"))
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'owner','x','2026-08-01')")
        for index, item in enumerate(POLLUTED_FLASH_TASKS):
            now = "2026-09-24 18:12:32"
            conn.execute(
                "INSERT INTO server_flash_cards(id,user_id,occurred_at,original_text,task_recommendations_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (item["flash_card_id"], 1, "2026-08-13", f"闪念{index}", "[]", "2026-08-13", "2026-08-13"),
            )
            conn.execute(
                "INSERT INTO server_flash_task_recommendations(id,user_id,flash_card_id,ordinal,title,status,creation_mode,local_task_id,creation_idempotency_key,created_at,updated_at) VALUES(?,?,?,?,?,'added','direct',?,?,?,?)",
                (item["recommendation_id"], 1, item["flash_card_id"], 0, f"任务{index}", item["task_id"], f"flash:{index}", "2026-08-13", now),
            )
            raw = json.dumps({"flash_card_id": item["flash_card_id"], "recommendation_id": item["recommendation_id"]})
            conn.execute(
                "INSERT INTO server_tasks(id,user_id,title,status,due_date,tags,raw_json,source,updated_at) VALUES(?,?,?,0,'2026-09-24','[]',?,'local',?)",
                (item["task_id"], 1, f"任务{index}", raw, now),
            )
            conn.execute(
                "INSERT INTO server_reward_config(user_id,item_type,item_id,coins,updated_at) VALUES(1,'task',?,1,?)",
                (item["task_id"], now),
            )
    return store, FlashTaskPollutionRepairService(store._connect, store._record_server_change)


def _state(store):
    with store._connect() as conn:
        tasks = [tuple(row) for row in conn.execute("SELECT id,deleted_at,updated_at FROM server_tasks ORDER BY id")]
        recs = [tuple(row) for row in conn.execute("SELECT id,status,local_task_id,updated_at FROM server_flash_task_recommendations ORDER BY id")]
        version = conn.execute("SELECT COALESCE(MAX(server_version),0) FROM server_change_log WHERE user_id=1").fetchone()[0]
    return tasks, recs, version


def test_pollution_repair_blocks_atomically_when_one_fingerprint_differs(tmp_path):
    store, service = _fixture(tmp_path)
    changed_id = POLLUTED_FLASH_TASKS[0]["task_id"]
    with store._transact() as conn:
        conn.execute("UPDATE server_tasks SET due_date='2026-09-25' WHERE id=?", (changed_id,))
    before = _state(store)

    result = service.repair()

    assert result["status"] == "blocked" and changed_id in result["mismatches"]
    assert _state(store) == before


def test_pollution_repair_publishes_seven_tombstones_and_is_idempotent(tmp_path):
    store, service = _fixture(tmp_path)

    first = service.repair()
    after_first = _state(store)
    second = service.repair()

    assert first == {"status": "repaired", "tasks": 7, "recommendations": 7}
    assert second == {"status": "already_repaired", "tasks": 7, "recommendations": 7}
    assert _state(store) == after_first
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_tasks WHERE deleted_at IS NOT NULL").fetchone()[0] == 7
        assert conn.execute("SELECT COUNT(*) FROM server_flash_task_recommendations WHERE status='pending' AND local_task_id IS NULL").fetchone()[0] == 7
        assert conn.execute("SELECT COUNT(*) FROM server_reward_config WHERE item_type='task'").fetchone()[0] == 7
        assert conn.execute("SELECT COUNT(*) FROM server_flash_cards WHERE deleted_at IS NULL").fetchone()[0] == 7
        deletes = conn.execute("SELECT COUNT(*) FROM server_change_log WHERE table_name='server_tasks' AND operation='delete'").fetchone()[0]
        restores = conn.execute("SELECT COUNT(*) FROM server_change_log WHERE table_name='server_flash_task_recommendations' AND operation='upsert'").fetchone()[0]
    assert (deletes, restores) == (7, 7)


def test_pollution_repair_rolls_back_when_change_publication_fails(tmp_path):
    store, _service = _fixture(tmp_path)
    before = _state(store)
    service = FlashTaskPollutionRepairService(
        store._connect,
        lambda *_args: (_ for _ in ()).throw(RuntimeError("publish failed")),
    )

    with pytest.raises(RuntimeError, match="publish failed"):
        service.repair()

    assert _state(store) == before
