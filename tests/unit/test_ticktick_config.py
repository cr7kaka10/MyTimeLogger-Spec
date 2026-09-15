# -*- coding: utf-8 -*-
import json
import sqlite3

from server.ticktick_config import load_ticktick_settings, load_ticktick_test_probe_settings
from server.ticktick_client import TickTickClient
from server.config_manager import ConfigManager


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE server_system_config (
            user_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL
        )
    """)
    return conn


def _server_config(tmp_path, text=None):
    path = tmp_path / "server_config.json"
    if text:
        path.write_text(text, encoding="utf-8")
    return ConfigManager(str(path), legacy_path=str(tmp_path / "missing_legacy.jsonc"))


def test_ticktick_verify_tls_defaults_to_local_false(monkeypatch, tmp_path):
    monkeypatch.delenv("TICKTICK_VERIFY_TLS", raising=False)
    conn = _conn()

    settings = load_ticktick_settings(conn, 1)

    assert settings.verify_tls is False


def test_ticktick_verify_tls_can_be_enabled_by_config(monkeypatch, tmp_path):
    conn = _conn()
    conn.execute(
        "INSERT INTO server_system_config (user_id, key, value) VALUES (?, ?, ?)",
        (1, "ticktick_config", json.dumps({"access_token": "token", "verify_tls": True})),
    )

    settings = load_ticktick_settings(conn, 1)
    client = TickTickClient(settings.access_token, settings.host, settings.verify_tls, settings.timeout_seconds)

    assert settings.verify_tls is True
    assert client.verify_tls is True


def test_ticktick_token_ignores_legacy_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TICKTICK_ACCESS_TOKEN", "owner-token")
    conn = _conn()

    settings = load_ticktick_settings(conn, 2)

    assert settings.access_token is None
    assert settings.enabled is False


def test_ticktick_test_probe_uses_opt_in_environment_only(monkeypatch):
    monkeypatch.setenv("TICKTICK_TEST_ACCESS_TOKEN", "test-only-token")
    monkeypatch.delenv("TICKTICK_TEST_PROBE_ENABLED", raising=False)
    assert load_ticktick_test_probe_settings().enabled is False

    monkeypatch.setenv("TICKTICK_TEST_PROBE_ENABLED", "true")
    settings = load_ticktick_test_probe_settings()
    assert settings.access_token == "test-only-token"
    assert settings.verify_tls is True
