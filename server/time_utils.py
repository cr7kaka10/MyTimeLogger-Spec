# -*- coding: utf-8 -*-
"""Timezone normalization helpers for database-bound timestamps."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

DEFAULT_TIME_ZONE = "Asia/Shanghai"
DB_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DB_DATE_FORMAT = "%Y-%m-%d"


def _target_tz(target_tz: str = DEFAULT_TIME_ZONE):
    if target_tz == DEFAULT_TIME_ZONE:
        return timezone(timedelta(hours=8))
    try:
        return ZoneInfo(target_tz)
    except Exception:
        return timezone(timedelta(hours=8))


def now_bj() -> str:
    return datetime.now(_target_tz()).strftime(DB_DATETIME_FORMAT)


def _parse_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    if not text:
        return None

    for fmt in (DB_DATETIME_FORMAT, DB_DATE_FORMAT):
        try:
            return datetime.strptime(text[: len(fmt)], fmt)
        except ValueError:
            pass

    normalized = text
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    if len(normalized) >= 5 and normalized[-5] in ("+", "-") and normalized[-2] != ":":
        normalized = normalized[:-2] + ":" + normalized[-2:]

    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def normalize_datetime(value, target_tz: str = DEFAULT_TIME_ZONE) -> str:
    dt = _parse_datetime(value)
    if dt is None:
        return "" if value is None else str(value)

    tz = _target_tz(target_tz)
    if dt.tzinfo is None:
        return dt.strftime(DB_DATETIME_FORMAT)
    return dt.astimezone(tz).strftime(DB_DATETIME_FORMAT)


def normalize_date(value, target_tz: str = DEFAULT_TIME_ZONE) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if "T" not in text and len(text) >= 10:
        return text[:10]
    normalized = normalize_datetime(text, target_tz)
    return normalized[:10] if normalized else ""


def normalize_record_times(record: dict, fields: tuple[str, ...] | list[str], target_tz: str = DEFAULT_TIME_ZONE) -> dict:
    result = dict(record)
    for field in fields:
        if field in result and result[field]:
            result[field] = normalize_datetime(result[field], target_tz)
    return result


TIME_FIELD_EXCLUDES = {"timeZone", "timezone", "isAllDay"}


def _is_time_field(field: str) -> bool:
    if field in TIME_FIELD_EXCLUDES:
        return False
    lowered = field.lower()
    return (
        lowered.endswith("date")
        or lowered.endswith("time")
        or lowered.endswith("_at")
        or lowered.endswith("_time")
        or lowered.endswith("_date")
    )


def normalize_detected_time_fields(record: dict, target_tz: str = DEFAULT_TIME_ZONE) -> dict:
    result = dict(record)
    for field, value in list(result.items()):
        if value and isinstance(value, (str, datetime)) and _is_time_field(field):
            result[field] = normalize_datetime(value, target_tz)
    return result


def normalize_ticktick_task_times(task: dict, target_tz: str = DEFAULT_TIME_ZONE) -> dict:
    result = normalize_detected_time_fields(task, target_tz)
    raw_due_date = result.get("due_date") or result.get("dueDate")
    if raw_due_date:
        result["due_date"] = normalize_datetime(raw_due_date, target_tz)
    if result.get("raw_json"):
        result["raw_json"] = normalize_task_raw_json(result["raw_json"], target_tz)
    return result


def normalize_task_record_for_db(task: dict, target_tz: str = DEFAULT_TIME_ZONE) -> dict:
    result = normalize_ticktick_task_times(task, target_tz)
    tags = result.get("tags")
    if isinstance(tags, list):
        result["tags"] = ",".join(str(tag) for tag in tags)
    elif not tags and "tags" in result:
        result["tags"] = ""
    return result


def normalize_task_raw_json(value, target_tz: str = DEFAULT_TIME_ZONE) -> str:
    if not value:
        return "" if value is None else str(value)
    try:
        payload = json.loads(value) if isinstance(value, str) else dict(value)
    except Exception:
        return str(value)
    normalized = normalize_detected_time_fields(payload, target_tz)
    raw_due_date = normalized.get("due_date") or normalized.get("dueDate")
    if raw_due_date:
        normalized["due_date"] = normalize_datetime(raw_due_date, target_tz)
    return json.dumps(normalized, ensure_ascii=False)
