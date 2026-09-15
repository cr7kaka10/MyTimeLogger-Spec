# -*- coding: utf-8 -*-
"""Runtime config helpers for Docker/server sleep analysis mode."""

import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

def _server_config():
    try:
        from .config_manager import server_config
    except (ImportError, ValueError):
        from config_manager import server_config
    return server_config


def build_root_config():
    return {
        "db_type": "sqlite",
        "ai_model_config": {},
    }


def build_skill_config():
    server_config = _server_config()
    return {
        "reports_dir": server_config.get_runtime("reports_dir", "/app/reports"),
        "atimelogger": {
            "base_url": "https://app.atimelogger.pro",
            "username": "",
            "password": "",
        },
        "huawei_health": {
            "data_directory": server_config.get_runtime("huawei_health_data_dir", "/app/server_data/huawei_health_data"),
        },
    }


def write_json(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def _truthy_value(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off", ""):
        return False
    return default


def _int_value(value, default):
    try:
        result = int(value)
        return result if result > 0 else default
    except (TypeError, ValueError):
        return default


def _float_value(value, default):
    try:
        result = float(value)
        return result if result > 0 else default
    except (TypeError, ValueError):
        return default


def build_s3_backup_config():
    return {
        "enabled": False,
        "endpoint": "",
        "bucket": "obss3",
        "region": "us-east-1",
        "access_key": "",
        "secret_key": "",
        "reports_prefix": "reports",
    }


def build_ticktick_config():
    return {
        "enabled": False,
        "access_token": "",
        "host": "dida365.com",
        "timeout_seconds": 15.0,
        "verify_tls": False,
        "username": "",
        "password": "",
        "sync_interval": 300,
    }


def build_atimelogger_config():
    return {
        "enabled": False,
        "username": "",
        "password": "",
        "token": "",
        "refresh_token": "",
        "device_id": "",
        "type_map": {},
        "unmatched_categories": [],
        "auth_required": False,
    }


def build_ai_model_config():
    return {
        "text_base_url": "",
        "text_api_key": "",
        "text_model": "",
        "vision_base_url": "",
        "vision_api_key": "",
        "vision_model": "",
        "text_backup_1_base_url": "",
        "text_backup_1_api_key": "",
        "text_backup_1_model": "",
        "text_backup_2_base_url": "",
        "text_backup_2_api_key": "",
        "text_backup_2_model": "",
        "vision_backup_1_base_url": "",
        "vision_backup_1_api_key": "",
        "vision_backup_1_model": "",
        "vision_backup_2_base_url": "",
        "vision_backup_2_api_key": "",
        "vision_backup_2_model": "",
        "backup_base_url": "",
        "backup_api_key": "",
        "backup_model": "",
    }


def _has_any_value(data):
    if isinstance(data, dict):
        return any(_has_any_value(value) for value in data.values())
    if isinstance(data, list):
        return bool(data)
    return bool(str(data or "").strip())


def _resolve_server_db_path(db_path=None):
    if db_path:
        return db_path
    return os.path.join(os.path.dirname(__file__), "data", "mtl_server.db")


def _resolve_bootstrap_user_id(conn, username=""):
    if username:
        row = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if row:
            return int(row[0])
    row = conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
    return int(row[0]) if row else None


def _resolve_username(conn, user_id):
    row = conn.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
    return row[0] if row else ""


def _upsert_system_config(conn, user_id, key, value, overwrite=False):
    existing = conn.execute(
        "SELECT value FROM server_system_config WHERE user_id=? AND key=?",
        (user_id, key),
    ).fetchone()
    if existing and not overwrite:
        return False
    updated_at = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        """
        INSERT INTO server_system_config (user_id, key, value, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
        """,
        (user_id, key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value), updated_at),
    )
    return True


def bootstrap_server_system_config(user_id=None, db_path=None):
    """Do not bootstrap user external service configs from deployment config."""
    path = _resolve_server_db_path(db_path)
    if not os.path.exists(path):
        return {"applied": 0, "skipped": "db_missing"}

    conn = sqlite3.connect(path)
    try:
        target_user_id = user_id or _resolve_bootstrap_user_id(conn, "")
        if not target_user_id:
            return {"applied": 0, "skipped": "user_missing"}
        return {"applied": 0, "user_id": target_user_id, "skipped": "user_service_configs_are_private"}
    finally:
        conn.close()


def migrate_legacy_service_config_to_user(user_id, db_path=None):
    """Explicitly absorb old shared service config into one confirmed user only."""
    path = _resolve_server_db_path(db_path)
    if not user_id or not os.path.exists(path):
        return {"applied": 0, "skipped": "user_or_db_missing"}

    legacy = _server_config().legacy_service_config_values()
    configs = {}
    if isinstance(legacy.get("ticktick"), dict):
        ticktick = dict(legacy["ticktick"])
        ticktick["enabled"] = bool(ticktick.get("access_token"))
        configs["ticktick_config"] = ticktick
    if isinstance(legacy.get("s3_backup"), dict):
        s3 = dict(legacy["s3_backup"])
        if "access_key_id" in s3:
            s3["access_key"] = s3.pop("access_key_id")
        if "secret_access_key" in s3:
            s3["secret_key"] = s3.pop("secret_access_key")
        configs["s3_backup_config"] = s3
    if isinstance(legacy.get("ai_model"), dict):
        configs["ai_model_config"] = dict(legacy["ai_model"])

    conn = sqlite3.connect(path)
    try:
        applied = 0
        for key, value in configs.items():
            if _has_any_value(value) and _upsert_system_config(conn, int(user_id), key, value, False):
                applied += 1
        conn.commit()
        return {"applied": applied, "user_id": int(user_id)}
    finally:
        conn.close()


def ensure_server_runtime_config(base_dir=None):
    """Create minimal config files needed by generate_full_report in containers."""
    base_dir = base_dir or os.path.abspath(".")
    server_config = _server_config()
    if not _truthy_value(server_config.get_runtime("generate_skill_config"), False):
        return

    root_config_path = os.path.join(base_dir, "config.json")
    skill_config_path = os.path.join(base_dir, "server", "skills", "time-management", "config.json")
    if not os.path.exists(root_config_path):
        write_json(root_config_path, build_root_config())
    if not os.path.exists(skill_config_path):
        write_json(skill_config_path, build_skill_config())
    # User service secrets are managed per authenticated user, not in runtime config.


def generate_token():
    return secrets.token_urlsafe(32)
