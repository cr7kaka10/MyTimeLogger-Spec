# -*- coding: utf-8 -*-
"""Security helpers shared by server status, logs and deployment code."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping


SECRET_KEYWORDS = ("token", "password", "secret", "api_key", "access_key", "refresh")
TIMER_LEASE_LOG_FIELDS = frozenset(
    {"user", "session", "completed_session", "intent", "operation", "revision", "result", "errorCode"}
)


def hash_bearer_token(token: str) -> str:
    return "sha256:" + hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def redact_secret(value: object, visible: int = 4) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= visible * 2:
        return "*" * len(text)
    return f"{text[:visible]}...{text[-visible:]}"


def redact_mapping(data: Mapping[str, object]) -> dict[str, object]:
    redacted: dict[str, object] = {}
    for key, value in data.items():
        lower = key.lower()
        if isinstance(value, str) and any(word in lower for word in SECRET_KEYWORDS):
            redacted[key] = redact_secret(value)
        elif isinstance(value, Mapping):
            redacted[key] = redact_mapping(value)
        else:
            redacted[key] = value
    return redacted


def redact_timer_lease_event(data: Mapping[str, object]) -> dict[str, object]:
    """只保留租约审计所需字段，避免把快照或认证信息写入日志。"""
    return {
        key: data[key]
        for key in TIMER_LEASE_LOG_FIELDS
        if key in data and data[key] is not None
    }
