"""北京时间下，按实际覆盖时长确定会话在时间书中的归属日。"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone


BEIJING_TZ = timezone(timedelta(hours=8))


def session_business_date(start_time: object, end_time: object, fallback: str = "") -> str:
    """Return the Beijing date with the longest covered duration; ties belong to the later date."""
    start = _parse_beijing_time(start_time)
    end = _parse_beijing_time(end_time)
    if start is None or end is None or end <= start:
        return fallback

    coverage: dict[str, float] = {}
    cursor = start
    while cursor < end:
        next_day = datetime.combine(cursor.date() + timedelta(days=1), time.min, BEIJING_TZ)
        segment_end = min(end, next_day)
        date_text = cursor.date().isoformat()
        coverage[date_text] = coverage.get(date_text, 0.0) + (segment_end - cursor).total_seconds()
        cursor = segment_end
    return max(coverage, key=lambda date_text: (coverage[date_text], date_text))


def _parse_beijing_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.replace(tzinfo=BEIJING_TZ) if parsed.tzinfo is None else parsed.astimezone(BEIJING_TZ)
