# -*- coding: utf-8 -*-
import pytest

from server.domain.sleep_reward_service import calculate_bedtime_coin, calculate_sleep_score, select_authoritative_sleep_settlements
from server.store import ServerSleepStore


def _metrics(**updates):
    value = {"sleep_start": "23:00", "sleep_end": "07:00", "sleep_score": 90,
             "deep_sleep_min": 95, "sleep_cycles": 5.5, "awake_min": 10,
             "awake_count": 1, "fall_asleep_min": 20, "wake_up_min": 10,
             "total_sleep_min": 1, "sleep_date": "2026-08-28", "report_completed_at": "2026-08-28 08:00:00",
             "report_status": 2, "analysis_report": "# 睡眠报告"}
    value.update(updates)
    return value


@pytest.mark.parametrize(("sleep_start", "amount"), [
    ("18:00", 20), ("22:29", 20), ("23:00", 20), ("23:01", 12), ("23:30", 12),
    ("23:31", 6), ("00:00", 6), ("00:01", 0), ("01:00", 0), ("01:01", -20),
    ("02:01", -40), ("03:01", -60), ("04:01", -80), ("05:01", -100), ("12:00", -100),
])
def test_bedtime_coin_minute_boundaries(sleep_start, amount):
    result = calculate_bedtime_coin(sleep_start)
    assert result["status"] == "settled" and result["amount"] == amount and result["reason"]


@pytest.mark.parametrize("sleep_start", [None, "", "not-a-time"])
def test_missing_or_invalid_bedtime_remains_pending_without_a_penalty(sleep_start):
    result = calculate_bedtime_coin(sleep_start)
    assert (result["status"], result["amount"]) == ("pending", 0)


def test_bedtime_deadline_without_sleep_start_does_not_create_a_ledger(tmp_db_path):
    store, date = ServerSleepStore(tmp_db_path), "2026-09-08"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'bedtime','x',?)", (date,))
    first = store.sleep_reward_service.reconcile_bedtime_coin(1, date, deadline_reached=True)
    store.save_huawei_sleep_data(1, date, {"sleep_start": "23:15"})
    store.save_huawei_sleep_data(1, date, {"sleep_start": "23:15"})
    with store._connect() as conn:
        rows = conn.execute("SELECT id,amount FROM server_reward_ledger WHERE user_id=1 AND source_type='sleep_bedtime_adjustment'").fetchall()
        balance = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()[0]
    assert first["bedtime_coin_amount"] == 0
    assert len(rows) == 1 and rows[0]["amount"] == 12 and balance == 12


def test_bedtime_coin_is_user_isolated_and_does_not_backfill_history(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    with store._transact() as conn:
        for user_id in (1, 4):
            conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(?,?,?,?)", (user_id, f'u{user_id}', 'x', '2026-09-08'))
    store.save_huawei_sleep_data(1, "2026-09-08", {"sleep_start": "22:45"})
    store.save_huawei_sleep_data(4, "2026-09-08", {"sleep_start": "02:30"})
    store.save_huawei_sleep_data(1, "2026-09-07", {"sleep_start": "22:45"})
    with store._connect() as conn:
        rows = [tuple(row) for row in conn.execute("SELECT user_id,target_date,amount FROM server_reward_ledger WHERE source_type='sleep_bedtime_adjustment' ORDER BY user_id")]
    assert rows == [(1, "2026-09-08", 20.0), (4, "2026-09-08", -40.0)]


def test_bedtime_rollback_removes_only_legacy_noon_ledgers(tmp_db_path):
    store, date = ServerSleepStore(tmp_db_path), "2026-09-08"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'rollback','x',?)", (date,))
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(2,'keep','x',?)", (date,))
    store.save_huawei_sleep_data(1, date, {"sleep_start": "22:45"})
    store.save_huawei_sleep_data(2, date, {"sleep_start": "22:45"})
    with store._transact() as conn:
        conn.execute("UPDATE server_sleep_score_settlements SET bedtime_coin_amount=-100,bedtime_coin_reason='截至北京时间12:00仍无有效睡眠记录' WHERE user_id=1")
        conn.execute("UPDATE server_reward_ledger SET amount=-100,description='截至北京时间12:00仍无有效睡眠记录' WHERE user_id=1 AND source_type='sleep_bedtime_adjustment'")
        store.reward_wallet_service.rebuild_wallet_snapshot_in_txn(conn, 1, store.reward_wallet_service._now)
    assert store.sleep_reward_service.audit_bedtime_coins()["users"] == [{"user_id": 1, "ledger_count": 1, "amount": -100.0}]
    result = store.sleep_reward_service.rollback_bedtime_coins()
    with store._connect() as conn:
        legacy = conn.execute("SELECT 1 FROM server_reward_ledger WHERE user_id=1 AND source_type='sleep_bedtime_adjustment'").fetchone()
        retained = conn.execute("SELECT amount FROM server_reward_ledger WHERE user_id=2 AND source_type='sleep_bedtime_adjustment'").fetchone()
        settlement = conn.execute("SELECT * FROM server_sleep_score_settlements WHERE user_id=1").fetchone()
        balance = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()[0]
    assert result["deleted_ledgers"] == 1 and legacy is None and retained["amount"] == 20 and balance == 0
    assert settlement["bedtime_coin_status"] == "pending" and settlement["bedtime_coin_rule_version"] is None


def test_bedtime_reconciliation_rolls_back_every_fact_on_wallet_failure(tmp_db_path, monkeypatch):
    store, date = ServerSleepStore(tmp_db_path), "2026-09-08"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'atomic','x',?)", (date,))
    monkeypatch.setattr(store.reward_wallet_service, "rebuild_wallet_snapshot_in_txn", lambda *args: (_ for _ in ()).throw(RuntimeError("injected")))
    with pytest.raises(RuntimeError, match="injected"):
        store.save_huawei_sleep_data(1, date, {"sleep_start": "22:45"})
    with store._connect() as conn:
        assert conn.execute("SELECT 1 FROM server_huawei_sleep_data WHERE user_id=1").fetchone() is None
        assert conn.execute("SELECT 1 FROM server_sleep_score_settlements WHERE user_id=1").fetchone() is None
        assert conn.execute("SELECT 1 FROM server_reward_ledger WHERE user_id=1").fetchone() is None


def test_score_is_100_and_cycle_boundary_is_inclusive():
    result = calculate_sleep_score(_metrics())
    assert result["status"] == "scored"
    assert result["score_total"] == 100
    assert result["dimensions"]["sleep_cycles"]["score"] == 30
    assert result["reward_amount"] == 80


def test_v4_has_exactly_eight_hard_coded_dimensions_and_100_points():
    result = calculate_sleep_score(_metrics(
        sleep_date="2026-09-12", report_completed_at="2026-09-12 08:00:00",
        deep_sleep_min=120, awake_min=0, awake_count=0, wake_up_min=20,
    ))
    assert result["rule_version"] == "sleep-score-v4"
    assert list(result["dimensions"]) == [
        "sleep_cycles", "on_time_sleep", "wake_up", "awake_count", "deep_sleep",
        "report_before_nine", "huawei_sleep_score", "awake_duration",
    ]
    assert result["score_total"] == 100
    assert result["is_all_complete"] is True
    assert "fall_asleep" not in result["dimensions"] and "wake_regular" not in result["dimensions"]
    assert all("coin_effect" in dimension for dimension in result["dimensions"].values())
    assert all("🪙" in dimension["coin_effect"] or "无独立金币流水" in dimension["coin_effect"]
               for dimension in result["dimensions"].values())


def test_v4_coin_attribution_explains_cycle_and_bedtime_penalties_without_double_counting(tmp_db_path):
    date = "2026-09-12"
    store = ServerSleepStore(tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'attribution','x',?)", (date,))
    metrics = _metrics(
        sleep_date=date, sleep_start="03:01", sleep_cycles=3.9,
        deep_sleep_min=81, awake_min=0, awake_count=0, wake_up_min=20,
        report_completed_at=f"{date} 08:00:00",
    )
    result = store.save_huawei_sleep_data(1, date, metrics, settle_score=True)
    with store._connect() as conn:
        settlement = conn.execute("SELECT net_amount FROM server_sleep_score_settlements WHERE user_id=1 AND sleep_date=?", (date,)).fetchone()
    assert result["dimensions"]["sleep_cycles"]["coin_effect"] == "-50 🪙：睡眠周期不足（<4.0）惩罚"
    assert result["dimensions"]["on_time_sleep"]["coin_effect"] == "-60 🪙：03:01–04:00入睡，扣60金币"
    assert result["dimensions"]["deep_sleep"]["coin_effect"] == "+0 🪙：未触发深睡惩罚"
    assert result["dimensions"]["wake_up"]["coin_effect"] == "影响睡眠评分奖励；本项无独立金币流水"
    assert settlement["net_amount"] == -110


def test_v4_perfect_sleep_awards_200_once_and_replay_is_idempotent(tmp_db_path):
    store, date = ServerSleepStore(tmp_db_path), "2026-09-12"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'v4-perfect','x',?)", (date,))
    metrics = _metrics(sleep_date=date, report_completed_at=f"{date} 08:00:00", deep_sleep_min=120, awake_min=0, awake_count=0, wake_up_min=20)
    first = store.sleep_reward_service.settle(1, date, metrics)
    replay = store.sleep_reward_service.settle(1, date, metrics)
    with store._connect() as conn:
        reward = conn.execute("SELECT amount FROM server_reward_ledger WHERE user_id=1 AND source_type='sleep_completion_reward'").fetchone()[0]
        balance = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()[0]
    assert first["completion_reward_amount"] == replay["completion_reward_amount"] == 200
    assert reward == 200 and balance == 280


def test_v4_historical_100_completion_snapshot_is_not_topped_up(tmp_db_path):
    store, date = ServerSleepStore(tmp_db_path), "2026-09-12"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'v4-history','x',?)", (date,))
    metrics = _metrics(sleep_date=date, report_completed_at=f"{date} 08:00:00", deep_sleep_min=120, awake_min=0, awake_count=0, wake_up_min=20)
    store.sleep_reward_service.settle(1, date, metrics)
    with store._transact() as conn:
        conn.execute("UPDATE server_sleep_score_settlements SET completion_reward_amount=100,net_amount=180 WHERE user_id=1 AND sleep_date=?", (date,))
        conn.execute("UPDATE server_reward_ledger SET amount=100 WHERE user_id=1 AND source_type='sleep_completion_reward'")
        store.reward_wallet_service.rebuild_wallet_snapshot_in_txn(conn, 1, store.reward_wallet_service._now)
    replay = store.sleep_reward_service.settle(1, date, metrics)
    with store._connect() as conn:
        reward = conn.execute("SELECT amount FROM server_reward_ledger WHERE user_id=1 AND source_type='sleep_completion_reward'").fetchone()[0]
    assert replay["completion_reward_amount"] == reward == 100


@pytest.mark.parametrize(("updates", "expected"), [
    ({"sleep_start": "23:31"}, (10, 20)),
    ({"wake_up_min": 21}, (6, 15)),
    ({"awake_count": 1}, (5, 10)),
    ({"awake_count": 2}, (0, 10)),
    ({"awake_min": 9}, (2, 5)),
    ({"awake_min": 10}, (0, 5)),
    ({"deep_sleep_min": 90}, (6, 10)),
    ({"deep_sleep_min": 60}, (2, 10)),
])
def test_v4_hard_coded_boundaries(updates, expected):
    values = {"sleep_date": "2026-09-12", "report_completed_at": "2026-09-12 08:00:00",
              "deep_sleep_min": 120, "awake_min": 0, "awake_count": 0, "wake_up_min": 20}
    values.update(updates)
    result = calculate_sleep_score(_metrics(**values))
    key = "on_time_sleep" if "sleep_start" in updates else "wake_up" if "wake_up_min" in updates else "awake_count" if "awake_count" in updates else "awake_duration" if "awake_min" in updates else "deep_sleep"
    assert (result["dimensions"][key]["score"], result["dimensions"][key]["max_score"]) == expected


def test_v4_deep_sleep_penalty_is_idempotent_and_does_not_change_v3(tmp_db_path):
    store, date = ServerSleepStore(tmp_db_path), "2026-09-12"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'v4-sleep','x',?)", (date,))
    metrics = _metrics(sleep_date=date, report_completed_at=f"{date} 08:00:00", deep_sleep_min=59, awake_min=0, awake_count=0)
    first = store.sleep_reward_service.settle(1, date, metrics)
    replay = store.sleep_reward_service.settle(1, date, metrics)
    historical = calculate_sleep_score(_metrics(sleep_date="2026-09-10", report_completed_at="2026-09-10 08:00:00"))
    with store._connect() as conn:
        rows = conn.execute("SELECT id,source_type,amount FROM server_reward_ledger WHERE user_id=1 ORDER BY id").fetchall()
    assert first["deep_sleep_penalty"] == -20 and replay["deep_sleep_penalty"] == -20
    assert [(row["source_type"], row["amount"]) for row in rows].count(("sleep_deep_penalty", -20.0)) == 1
    assert historical["rule_version"] == "sleep-score-v3" and "wake_regular" in historical["dimensions"]


def test_v4_no_main_sleep_is_zero_scored_minus_200_once_and_idempotent(tmp_db_path):
    store, date = ServerSleepStore(tmp_db_path), "2026-09-12"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'no-main-sleep','x',?)", (date,))
    data = {
        "full_report_state": "no_main_sleep", "report_status": 1,
        "analysis_report": "无睡眠，严重警告！", "official_advice": "无睡眠，严重警告！",
        "sleep_score": 0, "total_sleep_min": 0, "deep_sleep_min": 0,
        "light_sleep_min": 0, "rem_sleep_min": 0, "sleep_cycles": 0,
        "awake_min": 0, "awake_count": 0, "fall_asleep_min": 0, "wake_up_min": 0,
    }
    first = store.save_huawei_sleep_data(1, date, data, settle_score=True)
    replay = store.save_huawei_sleep_data(1, date, data, settle_score=True)
    with store._connect() as conn:
        negatives = conn.execute(
            "SELECT id,source_type,amount FROM server_reward_ledger WHERE user_id=1 AND target_date=? AND amount<0 ORDER BY source_type",
            (date,),
        ).fetchall()
        balance = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()[0]
    assert first["score_total"] == replay["score_total"] == 0
    assert len(first["dimensions"]) == 8 and all(row["score"] == 0 for row in first["dimensions"].values())
    assert (first["cycle_penalty"], first["deep_sleep_penalty"], first["no_sleep_penalty"], first["bedtime_coin_amount"]) == (-50, -20, -200, 0)
    assert first["net_amount"] == replay["net_amount"] == balance == -270
    assert [(row["source_type"], row["amount"]) for row in negatives] == [
        ("sleep_cycle_penalty", -50), ("sleep_deep_penalty", -20),
        ("sleep_no_sleep_penalty", -200),
    ]

    store.save_huawei_sleep_data(1, date, {"morning_diary": "晨记"})
    with store._connect() as conn:
        settlement = conn.execute("SELECT net_amount FROM server_sleep_score_settlements WHERE user_id=1 AND sleep_date=?", (date,)).fetchone()
        ledger_count = conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1 AND target_date=? AND amount<0", (date,)).fetchone()[0]
    assert settlement["net_amount"] == -260 and ledger_count == 3
    assert calculate_sleep_score(_metrics(sleep_date=date))["no_sleep_penalty"] == 0


def test_v3_wake_regular_uses_atimelogger_end_not_huawei_wake_time():
    result = calculate_sleep_score(_metrics(
        sleep_date="2026-09-10", sleep_end="07:20", atm_sleep_end="09:10",
        report_completed_at="2026-09-10 08:00:00",
    ))
    wake = result["dimensions"]["wake_regular"]
    assert result["rule_version"] == "sleep-score-v3"
    assert (wake["raw_value"], wake["score"], wake["matched_rule"]) == ("09:10", 5, "08:31–09:30")


def test_v3_missing_atimelogger_end_scores_zero_without_huawei_fallback():
    result = calculate_sleep_score(_metrics(
        sleep_date="2026-09-10", sleep_end="07:20", atm_sleep_end=None,
        report_completed_at="2026-09-10 08:00:00",
    ))
    wake = result["dimensions"]["wake_regular"]
    assert result["status"] == "scored"
    assert wake["score"] == 0 and wake["matched_rule"] == "缺少 aTimeLogger 睡眠结束记录"


@pytest.mark.parametrize(("atm_end", "expected"), [
    ("06:00", 10), ("08:30", 10), ("08:31", 5), ("09:30", 5), ("09:31", 0),
])
def test_v3_wake_regular_atimelogger_boundaries(atm_end, expected):
    result = calculate_sleep_score(_metrics(
        sleep_date="2026-09-10", sleep_end="07:20", atm_sleep_end=atm_end,
        report_completed_at="2026-09-10 10:00:00",
    ))
    assert result["dimensions"]["wake_regular"]["score"] == expected


def test_cycle_bands_and_penalty_are_explicit():
    assert calculate_sleep_score(_metrics(sleep_cycles=5.0))["dimensions"]["sleep_cycles"]["score"] == 25
    assert calculate_sleep_score(_metrics(sleep_cycles=4.2))["dimensions"]["sleep_cycles"]["score"] == 0
    low = calculate_sleep_score(_metrics(sleep_cycles=3.9))
    assert low["cycle_penalty"] == -50
    assert low["net_amount"] == low["reward_amount"] - 50


def test_awake_metrics_are_independent_and_total_duration_is_not_scored():
    result = calculate_sleep_score(_metrics(awake_min=35, awake_count=3, total_sleep_min=None))
    assert result["status"] == "scored"
    assert result["dimensions"]["awake_duration"]["score"] == 2
    assert result["dimensions"]["awake_count"]["score"] == 2


def test_missing_required_field_does_not_guess_or_penalize():
    result = calculate_sleep_score(_metrics(awake_count=None))
    assert result["status"] == "not_scored"
    assert result["missing_fields"] == ["awake_count"]
    assert result["cycle_penalty"] == 0


def test_metrics_without_visible_report_never_score_or_write_score_ledgers(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'no-report','x','2026-09-08')")
    result = store.sleep_reward_service.settle(1, "2026-09-08", _metrics(
        sleep_date="2026-09-08", report_status=0, analysis_report="", report_completed_at=None))
    with store._connect() as conn:
        ledgers = conn.execute("SELECT source_type FROM server_reward_ledger WHERE user_id=1").fetchall()
    assert result["status"] == "not_scored" and result["missing_fields"] == ["report"]
    assert ledgers == []


def test_diary_reward_is_independent_from_report_gate(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'diary-no-report','x','2026-09-08')")
    store.save_huawei_sleep_data(1, "2026-09-08", {"morning_diary": "晨记"})
    with store._connect() as conn:
        settlement = conn.execute("SELECT * FROM server_sleep_score_settlements WHERE user_id=1").fetchone()
        ledgers = conn.execute("SELECT source_type,amount FROM server_reward_ledger WHERE user_id=1").fetchall()
    assert settlement["settlement_status"] == "not_scored"
    assert [tuple(row) for row in ledgers] == [("sleep_morning_diary_reward", 10.0)]


def test_settlement_writes_reward_and_cycle_penalty_once(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'sleep','x','2026-08-28 00:00:00')")
    result = store.sleep_reward_service.settle(1, "2026-08-28", _metrics(sleep_cycles=3.9))
    store.sleep_reward_service.settle(1, "2026-08-28", _metrics(sleep_cycles=3.9))
    with store._connect() as conn:
        rows = conn.execute("SELECT source_type,amount FROM server_reward_ledger ORDER BY source_type").fetchall()
        count = conn.execute("SELECT COUNT(*) FROM server_sleep_score_settlements").fetchone()[0]
    assert count == 1
    assert [(row["source_type"], row["amount"]) for row in rows] == [
        ("sleep_completion_reward", 0.0),
        ("sleep_cycle_penalty", -50.0), ("sleep_settlement_reward", result["reward_amount"]),
    ]


def test_complete_report_timestamp_refreshes_current_v2_snapshot_once(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'sleep-refresh','x','2026-08-28 00:00:00')")
    store.sleep_reward_service.settle(1, "2026-08-28", _metrics(report_completed_at=None))
    refreshed = store.sleep_reward_service.settle(1, "2026-08-28", _metrics(report_completed_at="2026-08-28 08:59:00"))
    replay = store.sleep_reward_service.settle(1, "2026-08-28", _metrics(report_completed_at="2026-08-28 09:01:00"))
    assert refreshed["report_completed_at"] == "2026-08-28 08:59:00"
    assert refreshed["dimensions"]["report_before_nine"]["score"] == 5
    assert replay["report_completed_at"] == "2026-08-28 08:59:00"
    with store._connect() as conn:
        completion_count = conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='sleep_completion_reward'").fetchone()[0]
    assert completion_count == 1


def test_completion_reward_only_for_ten_perfect_dimensions_and_is_idempotent(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'sleep-complete','x','2026-08-28 00:00:00')")
    result = store.sleep_reward_service.settle(1, "2026-08-28", _metrics(sleep_date="2026-08-28"))
    replay = store.sleep_reward_service.settle(1, "2026-08-28", _metrics(sleep_date="2026-08-28"))
    with store._connect() as conn:
        rows = conn.execute("SELECT source_type,amount FROM server_reward_ledger WHERE user_id=1 ORDER BY source_type").fetchall()
    assert result["is_all_complete"] is True
    assert result["completion_reward_amount"] == 100
    assert replay["is_all_complete"] is True
    assert [(row["source_type"], row["amount"]) for row in rows] == [
        ("sleep_completion_reward", 100.0), ("sleep_cycle_penalty", 0.0),
        ("sleep_settlement_reward", 80.0),
    ]


def test_non_perfect_sleep_records_zero_completion_result(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'sleep-incomplete','x','2026-08-28 00:00:00')")
    result = store.sleep_reward_service.settle(1, "2026-08-28", _metrics(sleep_date="2026-08-28", awake_count=3))
    assert result["is_all_complete"] is False
    with store._connect() as conn:
        row = conn.execute("SELECT amount FROM server_reward_ledger WHERE source_type='sleep_completion_reward'").fetchone()
    assert row["amount"] == 0.0


def test_double_diary_reward_is_atomic_idempotent_and_reversible(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    date = "2026-09-05"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'diary','x','2026-09-05')")
    store.sleep_reward_service.settle(1, date, _metrics(sleep_date=date, awake_count=3))
    store.save_huawei_sleep_data(1, date, {"sleep_score": 82, "morning_diary": "晨记"})
    store.save_huawei_sleep_data(1, date, {"evening_diary": "晚记"})
    store.save_huawei_sleep_data(1, date, {"evening_diary": "晚记"})
    with store._connect() as conn:
        diary = conn.execute("SELECT * FROM server_sleep_score_settlements WHERE user_id=1 AND sleep_date=? AND rule_version='sleep-score-v2'", (date,)).fetchone()
        ledgers = conn.execute("SELECT source_type,amount FROM server_reward_ledger WHERE user_id=1 AND target_date=?", (date,)).fetchall()
        balance = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()[0]
    assert diary["diary_completion_status"] == "completed"
    assert diary["diary_completion_reward_amount"] == 10
    assert [(row["source_type"], row["amount"]) for row in ledgers].count(("sleep_diary_completion_reward", 10.0)) == 1
    assert sum(row["amount"] for row in ledgers) == balance

    store.save_huawei_sleep_data(1, date, {"evening_diary": ""})
    with store._connect() as conn:
        assert conn.execute("SELECT 1 FROM server_reward_ledger WHERE source_type='sleep_diary_completion_reward'").fetchone() is None
        after = conn.execute("SELECT * FROM server_sleep_score_settlements WHERE user_id=1 AND sleep_date=? AND rule_version='sleep-score-v2'", (date,)).fetchone()
        score_rows = conn.execute("SELECT source_type,amount FROM server_reward_ledger WHERE target_date=?", (date,)).fetchall()
    assert after["diary_completion_status"] == "pending"
    assert after["diary_completion_reward_amount"] == 0
    assert {row["source_type"] for row in score_rows} == {"sleep_settlement_reward", "sleep_cycle_penalty", "sleep_completion_reward"}


def test_independent_diary_rewards_are_idempotent_and_clear_separately(tmp_db_path):
    store, date = ServerSleepStore(tmp_db_path), "2026-09-06"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'independent-diary','x',?)", (date,))
    store.sleep_reward_service.settle(1, date, _metrics(sleep_date=date, awake_count=3))
    store.save_huawei_sleep_data(1, date, {"morning_diary": "晨记"})
    store.save_huawei_sleep_data(1, date, {"morning_diary": "晨记（修改）"})
    with store._connect() as conn:
        projection = conn.execute("SELECT * FROM server_sleep_score_settlements WHERE user_id=1 AND sleep_date=? AND rule_version='sleep-score-v2'", (date,)).fetchone()
        diary_rows = conn.execute("SELECT id,source_type,amount FROM server_reward_ledger WHERE user_id=1 AND target_date=? AND source_type LIKE 'sleep_%_diary_reward'", (date,)).fetchall()
    assert projection["morning_diary_reward_status"] == "completed" and projection["morning_diary_reward_amount"] == 10
    assert projection["evening_diary_reward_status"] == "pending" and projection["evening_diary_reward_amount"] == 0
    assert [(row["source_type"], row["amount"]) for row in diary_rows] == [("sleep_morning_diary_reward", 10.0)]

    store.save_huawei_sleep_data(1, date, {"evening_diary": "晚记"})
    with store._connect() as conn:
        diary_rows = conn.execute("SELECT source_type,amount FROM server_reward_ledger WHERE user_id=1 AND target_date=? AND source_type LIKE 'sleep_%_diary_reward' ORDER BY source_type", (date,)).fetchall()
    assert [(row["source_type"], row["amount"]) for row in diary_rows] == [("sleep_evening_diary_reward", 10.0), ("sleep_morning_diary_reward", 10.0)]

    store.save_huawei_sleep_data(1, date, {"morning_diary": ""})
    with store._connect() as conn:
        rows = conn.execute("SELECT source_type,amount FROM server_reward_ledger WHERE user_id=1 AND target_date=?", (date,)).fetchall()
        balance = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()[0]
    assert "sleep_morning_diary_reward" not in {row["source_type"] for row in rows}
    assert "sleep_evening_diary_reward" in {row["source_type"] for row in rows}
    assert {"sleep_settlement_reward", "sleep_cycle_penalty", "sleep_completion_reward"} <= {row["source_type"] for row in rows}
    assert sum(row["amount"] for row in rows) == balance


def test_effective_date_migration_replaces_combined_reward_but_preserves_history(tmp_db_path):
    store, stamp = ServerSleepStore(tmp_db_path), "2026-09-06 09:00:00"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'migration','x',?)", (stamp,))
        for date in ("2026-09-05", "2026-09-06"):
            conn.execute("INSERT INTO server_huawei_sleep_data(user_id,date,morning_diary,evening_diary,updated_at) VALUES(1,?,'晨记','晚记',?)", (date, stamp))
            conn.execute("""INSERT INTO server_sleep_score_settlements
                (id,user_id,sleep_date,metrics_snapshot,score_breakdown,score_total,reward_amount,cycle_penalty,net_amount,settlement_status,missing_fields,rule_version,occurred_at,created_at,updated_at,diary_completion_status,diary_completion_reward_amount)
                VALUES(?,1,?,'{}','{}',0,0,0,10,'pending','[]','sleep-score-v2',?,?,?,'completed',10)""", (f"settlement-{date}", date, stamp, stamp, stamp))
            ledger_id = f"sleep-diary-completion-reward:1:{date}:sleep-score-v2"
            store.reward_wallet_service.append_ledger_in_txn(conn, 1, 10, "sleep_diary_completion_reward", ledger_id, "旧双日记奖励", date, ledger_id, stamp)
    assert store.sleep_reward_service.migrate_effective_date_diary_rewards() == 1
    with store._connect() as conn:
        rows = [tuple(row) for row in conn.execute("SELECT target_date,source_type,amount FROM server_reward_ledger ORDER BY target_date,source_type")]
        wallet = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()[0]
    assert rows == [("2026-09-05", "sleep_diary_completion_reward", 10.0), ("2026-09-06", "sleep_evening_diary_reward", 10.0), ("2026-09-06", "sleep_morning_diary_reward", 10.0)]
    assert wallet == 30.0


def test_authoritative_sleep_settlement_prefers_current_rule_then_stable_history():
    rows = [
        {"sleep_date": "2026-08-28", "settlement_status": "scored", "rule_version": "sleep-score-v1", "updated_at": "2026-08-28 12:00:00", "created_at": "2026-08-28 10:00:00"},
        {"sleep_date": "2026-08-28", "settlement_status": "scored", "rule_version": "sleep-score-v2", "updated_at": "2026-08-28 11:00:00", "created_at": "2026-08-28 11:00:00"},
        {"sleep_date": "2026-08-29", "settlement_status": "scored", "rule_version": "sleep-score-v1", "updated_at": "2026-08-29 12:00:00", "created_at": "2026-08-29 10:00:00"},
        {"sleep_date": "2026-08-29", "settlement_status": "scored", "rule_version": "sleep-score-v0", "updated_at": "2026-08-29 12:00:00", "created_at": "2026-08-29 10:00:00"},
    ]

    selected = select_authoritative_sleep_settlements(rows)

    assert selected["2026-08-28"]["rule_version"] == "sleep-score-v2"
    assert selected["2026-08-29"]["rule_version"] == "sleep-score-v1"
    assert select_authoritative_sleep_settlements(rows) == selected


def test_current_sleep_version_replaces_legacy_version_ledger_in_one_transaction(tmp_db_path):
    store = ServerSleepStore(tmp_db_path)
    date = "2026-08-28"
    stamp = "2026-08-28 12:00:00"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'sleep-version','x',?)", (stamp,))
        conn.execute("""INSERT INTO server_sleep_score_settlements
            (id,user_id,sleep_date,metrics_snapshot,score_breakdown,score_total,reward_amount,cycle_penalty,net_amount,settlement_status,missing_fields,rule_version,occurred_at,created_at,updated_at,completion_reward_amount,is_all_complete)
            VALUES('legacy-v1',1,?,'{}','{}',28,0,-50,-50,'scored','[]','sleep-score-v1',?,?,?,0,0)""", (date, stamp, stamp, stamp))
        for ledger_id, source_type, source_id, amount in (
            (f"sleep-reward:1:{date}:sleep-score-v1", "sleep_settlement_reward", f"sleep-score:{date}:sleep-score-v1:reward", 0),
            (f"sleep-cycle-penalty:1:{date}:sleep-score-v1", "sleep_cycle_penalty", f"sleep-score:{date}:sleep-score-v1:cycle-penalty", -50),
            (f"sleep-completion-reward:1:{date}:sleep-score-v1", "sleep_completion_reward", f"sleep-score:{date}:sleep-score-v1:completion", 0),
        ):
            store.reward_wallet_service.append_ledger_in_txn(conn, 1, amount, source_type, source_id, "旧版本", date, ledger_id, stamp)

    store.sleep_reward_service.settle(1, date, _metrics(sleep_date=date, sleep_cycles=3.9))
    with store._transact() as conn:
        store.reward_wallet_service.append_ledger_in_txn(
            conn, 1, -50, "sleep_cycle_penalty", f"sleep-score:{date}:sleep-score-v1:cycle-penalty",
            "遗留旧版本", date, f"sleep-cycle-penalty:1:{date}:sleep-score-v1", stamp,
        )
    store.sleep_reward_service.settle(1, date, _metrics(sleep_date=date, sleep_cycles=3.9))

    with store._connect() as conn:
        ledgers = conn.execute("SELECT id,source_type,amount FROM server_reward_ledger ORDER BY id").fetchall()
        versions = conn.execute("SELECT rule_version FROM server_sleep_score_settlements ORDER BY rule_version").fetchall()
        balance = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()["balance"]
        changes = conn.execute("SELECT operation,record_id FROM server_change_log WHERE table_name='server_reward_ledger'").fetchall()
    assert [row[0] for row in ledgers] == [
        f"sleep-completion-reward:1:{date}:sleep-score-v2",
        f"sleep-cycle-penalty:1:{date}:sleep-score-v2",
        f"sleep-reward:1:{date}:sleep-score-v2",
    ]
    assert sum(row[2] for row in ledgers) == balance
    assert [row[0] for row in versions] == ["sleep-score-v1", "sleep-score-v2"]
    assert ("delete", f"sleep-cycle-penalty:1:{date}:sleep-score-v1") in [tuple(row) for row in changes]
    assert ("upsert", f"sleep-cycle-penalty:1:{date}:sleep-score-v2") in [tuple(row) for row in changes]


def test_unreported_score_reconciliation_preserves_diary_reward_and_other_user(tmp_db_path):
    store, date = ServerSleepStore(tmp_db_path), "2026-09-08"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'bad-score','x',?)", (date,))
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(2,'valid-score','x',?)", (date,))
    store.sleep_reward_service.settle(1, date, _metrics(sleep_date=date))
    store.save_huawei_sleep_data(1, date, {"morning_diary": "晨记"})
    store.save_huawei_sleep_data(2, date, {"report_status": 2, "analysis_report": "# 报告"})
    store.sleep_reward_service.settle(2, date, _metrics(sleep_date=date))

    assert store.sleep_reward_service.reconcile_unreported_scores() == {"candidates": 1, "users": 1}
    with store._connect() as conn:
        statuses = [tuple(row) for row in conn.execute("SELECT user_id,settlement_status FROM server_sleep_score_settlements ORDER BY user_id")]
        ledgers = [tuple(row) for row in conn.execute("SELECT user_id,source_type FROM server_reward_ledger ORDER BY user_id,source_type")]
        wallets = [tuple(row) for row in conn.execute("SELECT user_id,balance FROM server_user_wallets ORDER BY user_id")]
    assert statuses == [(1, "not_scored"), (2, "scored")]
    assert (1, "sleep_morning_diary_reward") in ledgers
    assert not any(user_id == 1 and source_type in {"sleep_settlement_reward", "sleep_cycle_penalty", "sleep_completion_reward"} for user_id, source_type in ledgers)
    assert dict(wallets)[1] == 10 and dict(wallets)[2] == 180


def test_unreported_score_reconciliation_rolls_back_on_change_log_failure(tmp_db_path):
    store, date = ServerSleepStore(tmp_db_path), "2026-09-08"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'rollback-score','x',?)", (date,))
    store.sleep_reward_service.settle(1, date, _metrics(sleep_date=date))
    store.sleep_reward_service._record_change = lambda *_args: (_ for _ in ()).throw(RuntimeError("injected"))

    import pytest
    with pytest.raises(RuntimeError, match="injected"):
        store.sleep_reward_service.reconcile_unreported_scores()

    with store._connect() as conn:
        status = conn.execute("SELECT settlement_status FROM server_sleep_score_settlements WHERE user_id=1").fetchone()[0]
        count = conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1").fetchone()[0]
    assert status == "scored" and count == 3


def test_report_body_and_score_commit_in_one_transaction(tmp_db_path, monkeypatch):
    store, date = ServerSleepStore(tmp_db_path), "2026-09-08"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'atomic-report','x',?)", (date,))
    monkeypatch.setattr(
        store.sleep_reward_service,
        "settle_in_txn",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("score failed")),
    )

    import pytest
    with pytest.raises(RuntimeError, match="score failed"):
        store.save_huawei_sleep_data(
            1, date, {"report_status": 1, "analysis_report": "# 报告"}, settle_score=True,
        )

    with store._connect() as conn:
        assert conn.execute(
            "SELECT 1 FROM server_huawei_sleep_data WHERE user_id=1 AND date=?", (date,),
        ).fetchone() is None
