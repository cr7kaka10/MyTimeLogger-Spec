"""奖励库存的北京时间自然周期边界。"""

from datetime import date, datetime, timedelta


def period_end(target_date: str | date | datetime, mode: str) -> str | None:
    """返回包含 target_date 的周期右开边界（北京时间）。"""
    normalized = str(mode or "unlimited").lower()
    if normalized == "unlimited":
        return None
    if isinstance(target_date, datetime):
        current = target_date.date()
    elif isinstance(target_date, date):
        current = target_date
    else:
        current = datetime.fromisoformat(str(target_date)[:19]).date()
    if normalized == "daily":
        boundary = current + timedelta(days=1)
    elif normalized == "weekly":
        boundary = current + timedelta(days=7 - current.weekday())
    elif normalized == "monthly":
        boundary = date(current.year + (current.month == 12), current.month % 12 + 1, 1)
    else:
        raise ValueError("库存周期无效")
    return f"{boundary.isoformat()} 00:00:00"


def period_window(target_date: str | date | datetime, mode: str) -> tuple[str, str] | None:
    """返回额度统计使用的自然周期首尾日期（闭区间）。"""
    normalized = str(mode or "unlimited").lower()
    if normalized == "unlimited":
        return None
    current = target_date.date() if isinstance(target_date, datetime) else target_date
    if not isinstance(current, date):
        current = datetime.fromisoformat(str(target_date)[:19]).date()
    if normalized == "daily":
        start = current
    elif normalized == "weekly":
        start = current - timedelta(days=current.weekday())
    elif normalized == "monthly":
        start = current.replace(day=1)
    else:
        raise ValueError("库存周期无效")
    end = date.fromisoformat(period_end(current, normalized)[:10]) - timedelta(days=1)
    return start.isoformat(), end.isoformat()
