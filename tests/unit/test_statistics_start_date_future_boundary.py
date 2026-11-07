from datetime import timedelta

import pytest

from server.statistics_start_date import maximum_statistics_start_date, parse_statistics_start_date
from server.domain.reward_rebuild_service import RewardRebuildService
from server.store import ServerSleepStore


def test_statistics_start_date_accepts_beijing_tomorrow_only():
    maximum = maximum_statistics_start_date()
    assert parse_statistics_start_date(maximum.isoformat(), reject_future=True, allowed_future_days=1) == maximum
    with pytest.raises(ValueError, match="不能晚于明天"):
        parse_statistics_start_date((maximum + timedelta(days=1)).isoformat(), reject_future=True, allowed_future_days=1)


def test_legacy_future_rejection_still_defaults_to_today():
    tomorrow = maximum_statistics_start_date()
    with pytest.raises(ValueError, match="不能晚于今天"):
        parse_statistics_start_date(tomorrow.isoformat(), reject_future=True)


def test_rebuild_preview_and_start_accept_tomorrow_but_never_later(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'future-user','hash','2026-09-24')")
    service = RewardRebuildService(store)
    tomorrow = maximum_statistics_start_date().isoformat()
    preview = service.preview(1, tomorrow)
    assert preview["new_balance_estimate"] == 0
    job, created = service.start(1, tomorrow, preview["preview_hash"])
    assert created is True and job["statistics_start_date"] == tomorrow
    with store._connect() as conn:
        before = conn.execute("SELECT COUNT(*) FROM server_reward_rebuild_jobs WHERE user_id=1").fetchone()[0]
        saved = conn.execute(
            "SELECT value FROM server_system_config WHERE user_id=1 AND key='statistics_start_date'"
        ).fetchone()
        assert saved[0] == tomorrow
    with pytest.raises(ValueError, match="不能晚于明天"):
        service.preview(1, (maximum_statistics_start_date() + timedelta(days=1)).isoformat())
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_reward_rebuild_jobs WHERE user_id=1").fetchone()[0] == before
