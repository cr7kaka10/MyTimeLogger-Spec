# -*- coding: utf-8 -*-
"""TickTick 配置读取入口。

调用链路：
  SyncHub -> load_ticktick_settings(conn, user_id) -> server_config_manager
    -> TickTickClient(access_token, host, timeout_seconds, verify_tls)

"""

from dataclasses import dataclass
import json
import os
import sqlite3
import hashlib
import uuid


def _coerce_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() not in ("0", "false", "no", "off")


def _float_or_default(value, default: float) -> float:
    try:
        result = float(value)
        return result if result > 0 else default
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class TickTickSettings:
    access_token: str | None
    host: str
    timeout_seconds: float
    verify_tls: bool
    inbox_pull_enabled: bool = True
    proxy_url: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.access_token)

    @property
    def transport_mode(self) -> str:
        return "explicit_proxy" if self.proxy_url else "direct"


def load_ticktick_test_probe_settings() -> TickTickSettings:
    """Return an opt-in test-only credential without reading user configuration."""
    if not _coerce_bool(os.getenv("TICKTICK_TEST_PROBE_ENABLED"), False):
        return TickTickSettings(None, "dida365.com", 15.0, True, True)
    return TickTickSettings(
        access_token=os.getenv("TICKTICK_TEST_ACCESS_TOKEN") or None,
        host=os.getenv("TICKTICK_TEST_HOST") or "dida365.com",
        timeout_seconds=_float_or_default(os.getenv("TICKTICK_TEST_TIMEOUT_SECONDS"), 15.0),
        verify_tls=_coerce_bool(os.getenv("TICKTICK_TEST_VERIFY_TLS"), True),
        inbox_pull_enabled=_coerce_bool(os.getenv("TICKTICK_TEST_INBOX_PULL_ENABLED"), True),
        proxy_url=os.getenv("TICKTICK_TEST_PROXY_URL") or None,
    )


def load_ticktick_settings(conn: sqlite3.Connection, user_id: int) -> TickTickSettings:
    """读取当前用户私有 TickTick 配置。"""
    row = conn.execute(
        "SELECT value FROM server_system_config WHERE user_id=? AND key='ticktick_config'",
        (user_id,),
    ).fetchone()
    cfg = {}
    if row and row[0]:
        try:
            parsed = json.loads(row[0])
            cfg = parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            cfg = {}
    return TickTickSettings(
        access_token=cfg.get("access_token") or None,
        host=cfg.get("host") or "dida365.com",
        timeout_seconds=_float_or_default(cfg.get("timeout_seconds"), 15.0),
        verify_tls=_coerce_bool(cfg.get("verify_tls"), False),
        inbox_pull_enabled=_coerce_bool(cfg.get("inbox_pull_enabled"), True),
        proxy_url=cfg.get("proxy_url") or None,
    )


def habit_binding_digest(settings):
    return hashlib.sha256(json.dumps([settings.host.lower(), settings.access_token],
                                    separators=(',', ':')).encode()).hexdigest()


def begin_habit_round(conn, user_id, settings):
    """调用者持有短写事务；禁止把凭据或摘要写入诊断。"""
    digest = habit_binding_digest(settings)
    row = conn.execute("SELECT * FROM server_habit_provider_bindings WHERE user_id=?", (user_id,)).fetchone()
    binding_id = row['binding_id'] if row and row['config_digest'] == digest else uuid.uuid4().hex
    round_id = int(row['round']) + 1 if row and row['binding_id'] == binding_id else 1
    conn.execute("""INSERT INTO server_habit_provider_bindings VALUES(?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET binding_id=excluded.binding_id,
        config_digest=excluded.config_digest,host=excluded.host,round=excluded.round""",
        (user_id, binding_id, digest, settings.host.lower(), round_id))
    return binding_id, round_id


def habit_round_is_current(conn, user_id, binding_id, round_id):
    row = conn.execute("SELECT * FROM server_habit_provider_bindings WHERE user_id=?", (user_id,)).fetchone()
    return bool(row and row['binding_id'] == binding_id and row['round'] == round_id
                and row['config_digest'] == habit_binding_digest(load_ticktick_settings(conn, user_id)))
