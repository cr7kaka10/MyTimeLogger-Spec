from server.domain.session_business_date import session_business_date


def test_session_business_date_uses_longer_beijing_day_and_later_tie_breaker():
    assert session_business_date("2026-08-30 22:30:00+08:00", "2026-08-31 08:30:00+08:00", "old") == "2026-08-31"
    assert session_business_date("2026-08-30 12:00:00+08:00", "2026-08-31 08:00:00+08:00", "old") == "2026-08-30"
    assert session_business_date("2026-08-30 20:00:00+08:00", "2026-08-31 04:00:00+08:00", "old") == "2026-08-31"


def test_session_business_date_handles_multiple_days_utc_and_invalid_values():
    assert session_business_date("2026-08-30T15:00:00Z", "2026-09-01T16:00:00Z", "old") == "2026-09-01"
    assert session_business_date("broken", "2026-08-31 08:30:00+08:00", "2026-08-30") == "2026-08-30"
    assert session_business_date("2026-08-31 08:30:00+08:00", "2026-08-31 08:30:00+08:00", "2026-08-30") == "2026-08-30"
