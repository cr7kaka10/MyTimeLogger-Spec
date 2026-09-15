# -*- coding: utf-8 -*-
"""华为睡眠结构化同步的字段合同与安全边界。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any


class SleepDataSource(StrEnum):
    HUAWEI_OFFICIAL = "huawei_official"
    HUAWEI_USER_IMPORT = "huawei_user_import"
    LOCAL_AUTOMATION = "local_automation"
    SCREENSHOT_OCR = "screenshot_ocr"


class SleepSyncStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    ERROR = "error"


PROHIBITED_SYNC_SOURCES = frozenset(
    {
        "huawei_app_simulation",
        "private_api",
        "token_reuse",
        "certificate_bypass",
        "anti_debug_bypass",
        "risk_control_bypass",
    }
)

CORE_SLEEP_FIELDS = [
    "sleep_score",
    "total_sleep_min",
    "deep_sleep_min",
    "light_sleep_min",
    "rem_sleep_min",
    "awake_count",
    "sleep_start",
    "sleep_end",
    "deep_sleep_ratio",
    "light_sleep_ratio",
    "rem_sleep_ratio",
    "sleep_continuity",
    "breathing_score",
]

OPTIONAL_SLEEP_FIELDS = [
    "sleep_cycles",
    "awake_min",
    "fall_asleep_min",
    "wake_up_min",
    "atm_sleep_start",
    "atm_sleep_end",
    "analysis_report",
    "morning_diary",
    "evening_diary",
    "report_status",
]

SLEEP_SOURCE_FIELDS = [
    "source",
    "synced_at",
    "sync_status",
    "sync_error",
]

HUAWEI_SLEEP_FIELD_MAP = {
    "score": "sleep_score",
    "sleepScore": "sleep_score",
    "totalSleepMin": "total_sleep_min",
    "deepSleepMin": "deep_sleep_min",
    "lightSleepMin": "light_sleep_min",
    "remSleepMin": "rem_sleep_min",
    "awakeCount": "awake_count",
    "sleepStart": "sleep_start",
    "sleepEnd": "sleep_end",
    "deepSleepRatio": "deep_sleep_ratio",
    "lightSleepRatio": "light_sleep_ratio",
    "remSleepRatio": "rem_sleep_ratio",
    "sleepContinuity": "sleep_continuity",
    "breathingScore": "breathing_score",
}


def sleep_field_mapping() -> dict[str, str]:
    mapping = {field: field for field in CORE_SLEEP_FIELDS + OPTIONAL_SLEEP_FIELDS}
    mapping.update(HUAWEI_SLEEP_FIELD_MAP)
    mapping["date"] = "date"
    mapping["sleep_date"] = "sleep_date"
    for field in SLEEP_SOURCE_FIELDS:
        mapping[field] = field
    return mapping


def validate_source(source: str | None) -> SleepDataSource:
    if not source:
        return SleepDataSource.HUAWEI_USER_IMPORT
    if source in PROHIBITED_SYNC_SOURCES:
        raise ValueError("禁止使用模拟华为运动健康 App 或绕过授权的数据来源")
    try:
        return SleepDataSource(source)
    except ValueError as exc:
        raise ValueError(f"未知睡眠数据来源: {source}") from exc


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    cleaned = "".join(ch for ch in str(value) if ch.isdigit() or ch == ".")
    if not cleaned:
        return None
    try:
        return int(float(cleaned))
    except ValueError:
        return None


def normalize_structured_sleep_payload(
    payload: dict[str, Any],
    *,
    date_str: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")

    source_value = validate_source(source or payload.get("source"))
    field_map = sleep_field_mapping()
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        target = field_map.get(key)
        if target:
            normalized[target] = value

    target_date = date_str or normalized.get("date") or normalized.get("sleep_date")
    if not target_date:
        raise ValueError("date is required")
    normalized["date"] = str(target_date)
    normalized["sleep_date"] = str(target_date)

    for field in [
        "sleep_score",
        "total_sleep_min",
        "deep_sleep_min",
        "light_sleep_min",
        "rem_sleep_min",
        "awake_count",
        "deep_sleep_ratio",
        "light_sleep_ratio",
        "rem_sleep_ratio",
        "sleep_continuity",
        "breathing_score",
        "sleep_cycles",
        "awake_min",
        "fall_asleep_min",
        "wake_up_min",
        "report_status",
    ]:
        if field in normalized:
            normalized[field] = _to_int(normalized[field])

    normalized["source"] = source_value.value
    normalized["sync_status"] = SleepSyncStatus.SUCCESS.value
    normalized["sync_error"] = ""
    normalized["synced_at"] = payload.get("synced_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return normalized

