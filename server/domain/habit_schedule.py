"""与客户端 HabitSchedule.ts 一致的本地习惯排期判断。"""

from datetime import date

WEEKDAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")


def scheduled_for_date(rule: str | None, day: str) -> bool:
    value = str(rule or "").upper().removeprefix("RRULE:")
    if not value or "FREQ=DAILY" in value or "FREQ=WEEKLY" not in value:
        return True
    fields = dict(part.split("=", 1) for part in value.split(";") if "=" in part)
    if "BYDAY" not in fields:
        return True
    selected = set(fields["BYDAY"].split(",")) & set(WEEKDAYS)
    try:
        return WEEKDAYS[date.fromisoformat(day).weekday()] in selected
    except ValueError:
        return True
