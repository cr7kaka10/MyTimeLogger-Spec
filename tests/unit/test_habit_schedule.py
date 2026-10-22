from server.domain.habit_schedule import scheduled_for_date


def test_schedule_matches_client_daily_weekdays_and_weekends():
    assert scheduled_for_date(None, "2026-10-19")
    assert scheduled_for_date("FREQ=DAILY", "2026-10-25")
    assert scheduled_for_date("RRULE:FREQ=WEEKLY;BYDAY=MO,TU", "2026-10-19")
    assert not scheduled_for_date("FREQ=WEEKLY;BYDAY=MO,TU", "2026-10-25")
    assert scheduled_for_date("FREQ=WEEKLY;BYDAY=SA,SU", "2026-10-25")
