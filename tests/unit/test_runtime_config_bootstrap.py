# -*- coding: utf-8 -*-
import json
import sqlite3

from server.runtime_config import build_skill_config, bootstrap_server_system_config, migrate_legacy_service_config_to_user
from server.config_manager import ConfigManager
from server.store import ServerSleepStore


def _read_config(db_path, user_id, key):
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT value FROM server_system_config WHERE user_id=? AND key=?",
            (user_id, key),
        ).fetchone()
        return json.loads(row[0]) if row else None
    finally:
        conn.close()


def _server_config(tmp_path, text):
    path = tmp_path / "server_config.json"
    path.write_text(text, encoding="utf-8")
    return ConfigManager(str(path), legacy_path=str(tmp_path / "missing_legacy.jsonc"))


def test_generated_skill_config_has_no_legacy_wechat_notification(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "server.config_manager.server_config",
        _server_config(tmp_path, '{"runtime": {}}'),
    )

    config = build_skill_config()

    assert "wechat" not in config


def test_bootstrap_does_not_overwrite_existing_shared_config_by_default(tmp_path, monkeypatch):
    db_path = str(tmp_path / "server.db")
    store = ServerSleepStore(db_path)
    assert store.create_user("redacted@example.com", "pass123")
    user_id = store.verify_user("redacted@example.com", "pass123")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO server_system_config (user_id, key, value, updated_at) VALUES (?, ?, ?, ?)",
            (user_id, "ai_model_config", json.dumps({"text_model": "existing"}), "2026-07-04 22:00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("TEXT_MODEL", "from-env")
    monkeypatch.delenv("MTL_CONFIG_OVERWRITE", raising=False)

    bootstrap_server_system_config(user_id=user_id, db_path=db_path)

    assert _read_config(db_path, user_id, "ai_model_config")["text_model"] == "existing"


def test_bootstrap_does_not_use_env_overwrite_flag(tmp_path, monkeypatch):
    db_path = str(tmp_path / "server.db")
    store = ServerSleepStore(db_path)
    assert store.create_user("redacted@example.com", "pass123")
    user_id = store.verify_user("redacted@example.com", "pass123")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO server_system_config (user_id, key, value, updated_at) VALUES (?, ?, ?, ?)",
            (user_id, "ai_model_config", json.dumps({"text_model": "existing"}), "2026-07-04 22:00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    monkeypatch.setenv("MTL_CONFIG_OVERWRITE", "1")
    monkeypatch.setenv("TEXT_MODEL", "from-env")
    monkeypatch.setattr(
        "server.config_manager.server_config",
        _server_config(tmp_path, '{"ai_model": {"text_model": "from-config"}}'),
    )

    bootstrap_server_system_config(user_id=user_id, db_path=db_path)

    assert _read_config(db_path, user_id, "ai_model_config")["text_model"] == "existing"


def test_owner_account_does_not_get_shared_secret_config(tmp_path, monkeypatch):
    db_path = str(tmp_path / "server.db")
    store = ServerSleepStore(db_path)
    assert store.create_user("redacted@example.com", "pass123")
    user_id = store.verify_user("redacted@example.com", "pass123")

    monkeypatch.setattr(
        "server.config_manager.server_config",
        _server_config(
            tmp_path,
            """
            {
              "s3_backup": {
                "endpoint": "https://s3.example",
                "access_key_id": "shared-access",
                "secret_access_key": "shared-secret"
              },
              "ai_model": {"text_api_key": "text-secret"}
            }
            """,
        ),
    )

    bootstrap_server_system_config(user_id=user_id, db_path=db_path)

    assert _read_config(db_path, user_id, "s3_backup_config") is None
    assert _read_config(db_path, user_id, "ai_model_config") is None


def test_new_account_gets_no_shared_refs_or_secret_copies(tmp_path, monkeypatch):
    db_path = str(tmp_path / "server.db")
    store = ServerSleepStore(db_path)
    assert store.create_user("new@example.com", "pass123")
    user_id = store.verify_user("new@example.com", "pass123")

    monkeypatch.setattr(
        "server.config_manager.server_config",
        _server_config(
            tmp_path,
            """
            {
              "s3_backup": {
                "endpoint": "https://s3.example",
                "access_key_id": "shared-access",
                "secret_access_key": "shared-secret"
              },
              "ai_model": {"text_api_key": "text-secret"}
            }
            """,
        ),
    )

    bootstrap_server_system_config(user_id=user_id, db_path=db_path)

    assert _read_config(db_path, user_id, "s3_backup_config") is None
    assert _read_config(db_path, user_id, "ai_model_config") is None


def test_legacy_service_config_migrates_only_to_confirmed_user(tmp_path, monkeypatch):
    db_path = str(tmp_path / "server.db")
    store = ServerSleepStore(db_path)
    assert store.create_user("owner@example.com", "pass123")
    assert store.create_user("other@example.com", "pass123")
    owner_id = store.verify_user("owner@example.com", "pass123")
    other_id = store.verify_user("other@example.com", "pass123")

    monkeypatch.setattr(
        "server.config_manager.server_config",
        _server_config(
            tmp_path,
            """
            {
              "ticktick": {"access_token": "tick-token"},
              "s3_backup": {"endpoint": "https://s3.example", "access_key_id": "ak", "secret_access_key": "sk"},
              "ai_model": {"text_api_key": "text-secret"}
            }
            """,
        ),
    )

    result = migrate_legacy_service_config_to_user(owner_id, db_path=db_path)

    assert result["applied"] == 3
    assert _read_config(db_path, owner_id, "ticktick_config")["access_token"] == "tick-token"
    assert _read_config(db_path, owner_id, "s3_backup_config")["secret_key"] == "sk"
    assert _read_config(db_path, owner_id, "ai_model_config")["text_api_key"] == "text-secret"
    assert _read_config(db_path, other_id, "ticktick_config") is None
    assert _read_config(db_path, other_id, "s3_backup_config") is None
    assert _read_config(db_path, other_id, "ai_model_config") is None
