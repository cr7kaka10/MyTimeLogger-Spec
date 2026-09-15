from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone


DEFAULT_STATISTICS_START_DATE = "2026-08-17"
BEIJING_TIMEZONE = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class StatisticsStartDate:
    date: str
    compact_date: str
    beijing_start_datetime: datetime
    utc_start_for_ticktick_completed: str


def parse_statistics_start_date(value: object, *, reject_future: bool = False) -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("统计起始日期格式必须为 YYYY-MM-DD")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("统计起始日期无效")
    if reject_future and parsed > datetime.now(BEIJING_TIMEZONE).date():
        raise ValueError("统计起始日期不能晚于今天")
    return parsed


def resolve_statistics_start_date(value: object) -> StatisticsStartDate:
    try:
        parsed = parse_statistics_start_date(value)
    except (TypeError, ValueError):
        parsed = date.fromisoformat(DEFAULT_STATISTICS_START_DATE)
    beijing_start = datetime.combine(parsed, time.min, tzinfo=BEIJING_TIMEZONE)
    return StatisticsStartDate(
        date=parsed.isoformat(),
        compact_date=parsed.strftime("%Y%m%d"),
        beijing_start_datetime=beijing_start,
        utc_start_for_ticktick_completed=beijing_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+0000"),
    )


def is_statistics_date_eligible(business_date: object, start_date: object) -> bool:
    try:
        business = parse_statistics_start_date(str(business_date)[:10])
        start = parse_statistics_start_date(resolve_statistics_start_date(start_date).date)
    except (TypeError, ValueError):
        return False
    return business >= start


def get_user_statistics_start_date(conn, user_id: int) -> StatisticsStartDate:
    row = conn.execute(
        "SELECT value FROM server_system_config WHERE user_id=? AND key='statistics_start_date'",
        (user_id,),
    ).fetchone()
    if not row:
        row = conn.execute(
            "SELECT value FROM server_system_config WHERE user_id=? AND key='checklist_sync_start_date'",
            (user_id,),
        ).fetchone()
    return resolve_statistics_start_date(row[0] if row else None)


def is_user_statistics_date_eligible(conn, user_id: int, business_date: object) -> bool:
    return is_statistics_date_eligible(
        business_date, get_user_statistics_start_date(conn, user_id).date,
    )
