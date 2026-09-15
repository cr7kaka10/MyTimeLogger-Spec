import hashlib
import json
import sqlite3


def ticktick_reward_where(task_ids: str, habit_ids: str) -> str:
    historical = """EXISTS (
        SELECT 1 FROM server_change_log history
        WHERE history.user_id=server_reward_ledger.user_id
          AND history.record_id=CAST(server_reward_ledger.source_id AS TEXT)
          AND {entity}
          AND json_valid(history.changed_fields_json)
          AND COALESCE(json_extract(history.changed_fields_json, '$.raw_json'), '') != ''
    )"""
    task_history = historical.format(entity="(history.entity_type='task' OR history.table_name IN ('tasks','server_tasks'))")
    habit_history = historical.format(entity="(history.entity_type='habit' OR history.table_name IN ('habits','server_habits'))")
    task_occurrences = """EXISTS (
        SELECT 1 FROM server_tasks occurrence
        WHERE occurrence.user_id=server_reward_ledger.user_id
          AND COALESCE(occurrence.raw_json, '') != ''
          AND server_reward_ledger.source_id LIKE CAST(occurrence.id AS TEXT) || '#%'
    )"""
    return f"""user_id=? AND (
        (source_type='task_complete' AND (source_id IN ({task_ids}) OR {task_occurrences} OR {task_history}))
        OR (source_type IN ('habit_checkin','habit_fail') AND (source_id IN ({habit_ids}) OR {habit_history}))
    )"""


def preview_ticktick_reset(db_path: str, user_id: int, start_date: str) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        task = "user_id=? AND COALESCE(raw_json, '') != ''"
        habit = "user_id=? AND COALESCE(raw_json, '') != ''"
        task_ids = f"SELECT id FROM server_tasks WHERE {task}"
        habit_ids = f"SELECT id FROM server_habits WHERE {habit}"
        rewards = ticktick_reward_where(task_ids, habit_ids)
        counts = {
            "tasks": conn.execute(f"SELECT COUNT(*) FROM server_tasks WHERE {task}", (user_id,)).fetchone()[0],
            "habits": conn.execute(f"SELECT COUNT(*) FROM server_habits WHERE {habit}", (user_id,)).fetchone()[0],
            "checkins": conn.execute(f"SELECT COUNT(*) FROM server_habit_checkins WHERE user_id=? AND habit_id IN ({habit_ids})", (user_id, user_id)).fetchone()[0],
            "rewards": conn.execute(f"SELECT COUNT(*) FROM server_reward_ledger WHERE {rewards}", (user_id, user_id, user_id)).fetchone()[0],
            "wallets": conn.execute("SELECT COUNT(*) FROM server_user_wallets WHERE user_id=?", (user_id,)).fetchone()[0],
            "sync_state": conn.execute("SELECT COUNT(*) FROM server_sync_state WHERE user_id=? AND system='ticktick'", (user_id,)).fetchone()[0],
        }
        result = {"user_id": user_id, "start_date": start_date, "counts": counts}
        result["summary_hash"] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return result
    finally:
        conn.close()
