import sqlite3
import logging
import hashlib
import uuid
from datetime import datetime, timedelta, timezone

try:
    from .db_wrapper import ServerDBWrapper
    from .ticktick_reset import preview_ticktick_reset, ticktick_reward_where
except ImportError:
    from db_wrapper import ServerDBWrapper
    from ticktick_reset import preview_ticktick_reset, ticktick_reward_where

logger = logging.getLogger(__name__)


class TickTickResetError(RuntimeError):
    pass


def reset_ticktick_data(db_path: str, user_id: int, start_date: str, summary_hash: str, phrase: str, request_id: str | None = None, allow_repeat: bool = False) -> dict:
    preview = preview_ticktick_reset(db_path, user_id, start_date)
    if summary_hash != preview['summary_hash'] or phrase != f'RESET TICKTICK USER {user_id}':
        raise ValueError('confirmation_invalid')
    logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=transaction_verified counts=%s", request_id, user_id, preview["counts"])
    conn = sqlite3.connect(db_path)
    trace_namespace = hashlib.sha256(str(request_id or "manual").encode()).hexdigest()[:12]
    reset_namespace = f"ticktick-reset:{trace_namespace}:{uuid.uuid4().hex[:12]}"
    stage = "transaction_started"
    current_table = None
    try:
        conn.execute('BEGIN IMMEDIATE')
        logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=transaction_started", request_id, user_id)
        conn.execute('CREATE TABLE IF NOT EXISTS ticktick_reset_audit (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, summary_hash TEXT NOT NULL, start_date TEXT NOT NULL, reset_at TEXT NOT NULL, UNIQUE(user_id, summary_hash))')
        used = conn.execute('SELECT 1 FROM ticktick_reset_audit WHERE user_id=? AND summary_hash=?', (user_id, summary_hash)).fetchone()
        if used and not allow_repeat:
            raise ValueError('confirmation_already_used')
        if used:
            conn.execute('DELETE FROM ticktick_reset_audit WHERE user_id=? AND summary_hash=?', (user_id, summary_hash))
        task = "user_id=? AND COALESCE(raw_json, '') != ''"; habit = task
        task_ids = f'SELECT id FROM server_tasks WHERE {task}'; habit_ids = f'SELECT id FROM server_habits WHERE {habit}'
        rewards = ticktick_reward_where(task_ids, habit_ids)
        reward_ids = conn.execute(f"SELECT id FROM server_reward_ledger WHERE {rewards}", (user_id, user_id, user_id)).fetchall()
        checkin_ids = conn.execute(f'SELECT id FROM server_habit_checkins WHERE user_id=? AND habit_id IN ({habit_ids})', (user_id, user_id)).fetchall()
        imported_task_ids = conn.execute(f'SELECT id FROM server_tasks WHERE {task}', (user_id,)).fetchall()
        imported_habit_ids = conn.execute(f'SELECT id FROM server_habits WHERE {habit}', (user_id,)).fetchall()
        conn.execute(f"DELETE FROM server_reward_ledger WHERE {rewards}", (user_id, user_id, user_id))
        logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=rewards_deleted count=%s", request_id, user_id, len(reward_ids))
        conn.execute(f'DELETE FROM server_habit_checkins WHERE user_id=? AND habit_id IN ({habit_ids})', (user_id, user_id))
        logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=checkins_deleted count=%s", request_id, user_id, len(checkin_ids))
        conn.execute(f'DELETE FROM server_tasks WHERE {task}', (user_id,))
        logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=tasks_deleted count=%s", request_id, user_id, len(imported_task_ids))
        conn.execute(f'DELETE FROM server_habits WHERE {habit}', (user_id,))
        logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=habits_deleted count=%s", request_id, user_id, len(imported_habit_ids))
        writer = ServerDBWrapper(db_path)
        stage = "tombstones"
        for table_name, entity_type, rows in (
            ('server_reward_ledger', 'reward_ledger', reward_ids),
            ('server_habit_checkins', 'habit_checkin', checkin_ids),
            ('server_tasks', 'task', imported_task_ids),
            ('server_habits', 'habit', imported_habit_ids),
        ):
            current_table = table_name
            for (record_id,) in rows:
                writer.write_server_change(user_id, entity_type, str(record_id), 'delete', {'id': str(record_id)}, change_id=f'{reset_namespace}:{table_name}:{record_id}', device_id='server-reset', table_name=table_name, conn=conn)
        tombstone_count = len(reward_ids) + len(checkin_ids) + len(imported_task_ids) + len(imported_habit_ids)
        logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=tombstones_written namespace_suffix=%s count=%s", request_id, user_id, reset_namespace[-12:], tombstone_count)
        conn.execute("DELETE FROM server_sync_state WHERE user_id=? AND system='ticktick'", (user_id,))
        logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=sync_state_cleared", request_id, user_id)
        reset_at = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
        marker_key = 'checklist_ticktick_reset_marker'
        marker_value = f'{start_date}:{summary_hash[:16]}'
        conn.execute("INSERT INTO server_system_config (user_id,key,value,updated_at) VALUES (?, 'statistics_start_date', ?, ?) ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (user_id, start_date, reset_at))
        conn.execute("INSERT INTO server_system_config (user_id,key,value,updated_at) VALUES (?,?,?,?) ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (user_id, marker_key, marker_value, reset_at))
        for key in ('statistics_start_date', marker_key):
            writer.write_server_change(user_id, 'system_config', key, 'upsert', {'key': key},
                change_id=f'{reset_namespace}:server_system_config:{key}',
                device_id='server-reset', table_name='server_system_config', conn=conn)
        logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=start_date_saved start_date=%s", request_id, user_id, start_date)
        logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=cache_marker_written", request_id, user_id)
        conn.execute('DELETE FROM server_user_wallets WHERE user_id=?', (user_id,))
        conn.execute("INSERT INTO server_user_wallets (user_id,balance,updated_at) SELECT ?,COALESCE(SUM(amount),0),? FROM server_reward_ledger WHERE user_id=?", (user_id, datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S'), user_id))
        logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=wallet_rebuilt", request_id, user_id)
        conn.execute('INSERT INTO ticktick_reset_audit (user_id,summary_hash,start_date,reset_at) VALUES (?,?,?,?)', (user_id, summary_hash, start_date, reset_at))
        conn.commit()
        logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=transaction_committed", request_id, user_id)
        return {'reset': preview['counts'], 'summary_hash': summary_hash}
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=transaction_rolled_back error_type=%s reset_stage=%s namespace_suffix=%s table=%s", request_id, user_id, type(exc).__name__, stage, reset_namespace[-12:], current_table)
        error = TickTickResetError("ticktick_reset_tombstone_conflict" if stage == "tombstones" else "ticktick_reset_integrity_error")
        error.reward_rebuild_details = {"chain": "ticktick_reset", "check": stage, "namespace_suffix": reset_namespace[-12:], "table": current_table}
        raise error from exc
    except Exception as exc:
        conn.rollback()
        logger.warning("[ChecklistReset] request_id=%s user_id=%s stage=transaction_rolled_back error_type=%s", request_id, user_id, type(exc).__name__)
        raise
    finally:
        conn.close()
