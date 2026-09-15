import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone


DATA_TABLES = ("server_habits", "server_habit_checkins", "server_tasks", "server_reward_ledger", "server_user_wallets")
CONFIG_KEYS = (
    "account_identity_key", "auth_token", "ticktick_config", "atimelogger_config", "ai_model_config", "s3_backup_config",
    "env_development_auth_token", "env_testing_auth_token", "env_production_auth_token",
)
CHANGE_TABLES = (*DATA_TABLES, "habits", "habit_checkins", "tasks", "reward_ledger", "user_wallets")


def preview_contamination(db_path: str, user_id: int) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        if not conn.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone(): raise ValueError("user_not_found")
        counts = {name: conn.execute(f"SELECT COUNT(*) FROM {name} WHERE user_id=?", (user_id,)).fetchone()[0] for name in DATA_TABLES}
        counts["sync_state"] = conn.execute("SELECT COUNT(*) FROM server_sync_state WHERE user_id=?", (user_id,)).fetchone()[0]
        keys = [row[0] for row in conn.execute(f"SELECT key FROM server_system_config WHERE user_id=? AND key IN ({','.join('?' * len(CONFIG_KEYS))}) ORDER BY key", (user_id, *CONFIG_KEYS))]
        window = conn.execute(f"SELECT MIN(changed_at), MAX(changed_at) FROM server_change_log WHERE user_id=? AND table_name IN ({','.join('?' * len(CHANGE_TABLES))})", (user_id, *CHANGE_TABLES)).fetchone()
        counts["change_log"] = conn.execute(f"SELECT COUNT(*) FROM server_change_log WHERE user_id=? AND table_name IN ({','.join('?' * len(CHANGE_TABLES))})", (user_id, *CHANGE_TABLES)).fetchone()[0]
        result = {"user_id": user_id, "counts": {**counts, "provider_configs": len(keys)}, "change_window": {"start": window[0], "end": window[1]}, "config_keys": keys}
        result["summary_hash"] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return result
    finally:
        conn.close()


def recover_contamination(db_path: str, actor_user_id: int, user_id: int, summary_hash: str, confirmation_phrase: str) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        preview = preview_contamination(db_path, user_id)
        if summary_hash != preview["summary_hash"] or confirmation_phrase != f"RESTORE USER {user_id}": raise ValueError("confirmation_invalid")
        conn.execute("CREATE TABLE IF NOT EXISTS account_contamination_audit (id INTEGER PRIMARY KEY, actor_user_id INTEGER NOT NULL, target_user_id INTEGER NOT NULL, summary_hash TEXT NOT NULL, restored_at TEXT NOT NULL, UNIQUE(target_user_id, summary_hash))")
        if conn.execute("SELECT 1 FROM account_contamination_audit WHERE target_user_id=? AND summary_hash=?", (user_id, summary_hash)).fetchone(): raise ValueError("confirmation_already_used")
        for table in DATA_TABLES: conn.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
        conn.execute(f"DELETE FROM server_system_config WHERE user_id=? AND key IN ({','.join('?' * len(CONFIG_KEYS))})", (user_id, *CONFIG_KEYS))
        conn.execute("DELETE FROM server_sync_state WHERE user_id=?", (user_id,))
        conn.execute(f"DELETE FROM server_change_log WHERE user_id=? AND (table_name IN ({','.join('?' * len(CHANGE_TABLES))}) OR (table_name='system_config' AND record_id IN ({','.join('?' * len(CONFIG_KEYS))})))", (user_id, *CHANGE_TABLES, *CONFIG_KEYS))
        now = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT INTO account_contamination_audit (actor_user_id,target_user_id,summary_hash,restored_at) VALUES (?,?,?,?)", (actor_user_id, user_id, summary_hash, now))
        conn.commit()
        return {"user_id": user_id, "summary_hash": summary_hash, "restored": preview["counts"]}
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()
