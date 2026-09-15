import pytest

import server.domain.ticktick_task_dates as task_dates
from server.domain.ticktick_task_dates import TaskTimezoneUnavailableError, normalize_task_date, postpone_task_date, validate_task_date_range


def test_normalizes_provider_dates_and_explicit_clear():
    assert normalize_task_date("2026-08-09T09:00:00+0800", "Asia/Shanghai") == "2026-08-09T09:00:00+0800"
    assert normalize_task_date(None, "Asia/Shanghai") is None


def test_postpone_uses_calendar_days_across_dst():
    assert postpone_task_date("2026-03-07T09:00:00-0500", 2, "America/New_York") == "2026-03-09T09:00:00-0400"


def test_postpone_uses_shanghai_when_timezone_is_invalid():
    assert postpone_task_date("2026-08-09T00:00:00+0800", 7, "invalid/time-zone") == "2026-08-16T00:00:00+0800"


def test_shanghai_uses_fixed_offset_when_iana_data_is_unavailable(monkeypatch):
    monkeypatch.setattr(task_dates, "ZoneInfo", lambda _: (_ for _ in ()).throw(task_dates.ZoneInfoNotFoundError("missing")))
    assert normalize_task_date("2026-08-09T09:00:00+08:00", "Asia/Shanghai") == "2026-08-09T09:00:00+0800"


def test_non_shanghai_timezone_does_not_silently_fallback_without_iana_data(monkeypatch):
    monkeypatch.setattr(task_dates, "ZoneInfo", lambda _: (_ for _ in ()).throw(task_dates.ZoneInfoNotFoundError("missing")))
    with pytest.raises(TaskTimezoneUnavailableError, match="task_timezone_unavailable"):
        normalize_task_date("2026-08-09T09:00:00-04:00", "America/New_York")


def test_range_validation_rejects_start_after_due_and_keeps_single_date():
    assert validate_task_date_range(None, "2026-08-09T00:00:00+0800", "Asia/Shanghai") == (None, "2026-08-09T00:00:00+0800")
    with pytest.raises(ValueError, match="start_after_due"):
        validate_task_date_range("2026-08-10T00:00:00+0800", "2026-08-09T00:00:00+0800", "Asia/Shanghai")
