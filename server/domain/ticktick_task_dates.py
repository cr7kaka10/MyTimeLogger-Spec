from __future__ import annotations

from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class TaskTimezoneUnavailableError(ValueError):
    """Raised when a task timezone cannot be resolved without guessing."""


_SHANGHAI = "Asia/Shanghai"
_SHANGHAI_FALLBACK = timezone(timedelta(hours=8), name=_SHANGHAI)


def resolve_timezone(value: object) -> tzinfo:
    requested = str(value or _SHANGHAI)
    try:
        return ZoneInfo(requested)
    except ZoneInfoNotFoundError:
        try:
            return ZoneInfo(_SHANGHAI)
        except ZoneInfoNotFoundError as exc:
            if requested == _SHANGHAI:
                return _SHANGHAI_FALLBACK
            raise TaskTimezoneUnavailableError("task_timezone_unavailable") from exc


def normalize_task_date(value: object, time_zone: object = None) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("validation_error:invalid_task_date") from exc
    zone = resolve_timezone(time_zone)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S%z")


def postpone_task_date(value: object, days: int, time_zone: object = None) -> str | None:
    normalized = normalize_task_date(value, time_zone)
    if normalized is None:
        return None
    zone = resolve_timezone(time_zone)
    local = datetime.strptime(normalized, "%Y-%m-%dT%H:%M:%S%z").astimezone(zone)
    target_day = local.date() + timedelta(days=int(days))
    shifted = local.replace(year=target_day.year, month=target_day.month, day=target_day.day)
    return shifted.strftime("%Y-%m-%dT%H:%M:%S%z")


def validate_task_date_range(start_date: object, due_date: object, time_zone: object = None) -> tuple[str | None, str | None]:
    start = normalize_task_date(start_date, time_zone)
    due = normalize_task_date(due_date, time_zone)
    if start and due and datetime.strptime(start, "%Y-%m-%dT%H:%M:%S%z") > datetime.strptime(due, "%Y-%m-%dT%H:%M:%S%z"):
        raise ValueError("validation_error:start_after_due")
    return start, due
