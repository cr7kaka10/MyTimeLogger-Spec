from datetime import datetime, timezone, timedelta
import json
import sqlite3

import pytest

import server.server as server_module
from server.domain.exercise_v4_service import DIET_RULES, ExerciseV4Service
from server.domain.sample_data_initialization_service import SampleDataInitializationService
from server.store import ServerSleepStore


BJ = timezone(timedelta(hours=8))


def _setup(path, users=(1,)):
    store = ServerSleepStore(path)
    with store._transact() as conn:
        for user_id in users:
            conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(?,?,?,?)",
                         (user_id, f"u{user_id}", "x", "2026-09-10"))
    seed = SampleDataInitializationService(path)
    for user_id in users:
        seed.ensure_user_sample_data(user_id)
    service = ExerciseV4Service(store.reward_wallet_service, lambda *args: None)
    return store, service


def _daily(conn, user_id, date, weight=None, body_fat=None):
    conn.execute("""INSERT INTO server_exercise_daily_logs
        (id,user_id,date,plan_version,exercise_type,weight,body_fat_rate,created_at,updated_at)
        VALUES (?,?,?,?, 'daily',?,?,?,?)""",
        (f"log-{user_id}-{date}", user_id, date, "v4", weight, body_fat, date, date))


def test_v4_is_complete_idempotent_and_user_isolated(tmp_db_path):
    store, _ = _setup(tmp_db_path, (1, 4))
    repaired = SampleDataInitializationService(tmp_db_path).repair_v4_diet_rule_keys(1)
    assert repaired == 3
    with store._connect() as conn:
        assert [tuple(row) for row in conn.execute("SELECT user_id,value FROM server_system_config WHERE key='active_exercise_plan_version' ORDER BY user_id")] == [(1, "v4"), (4, "v4")]
        assert [tuple(row) for row in conn.execute("SELECT user_id,COUNT(*) FROM server_exercise_plan_items WHERE plan_version='v4' GROUP BY user_id ORDER BY user_id")] == [(1, 23), (4, 23)]
        assert conn.execute("SELECT COUNT(*) FROM server_exercise_plan_versions WHERE version='scoring-v3'").fetchone()[0] == 0


def test_v4_diet_rule_repair_replaces_empty_keys_and_ignores_empty_checkin_fact(tmp_db_path):
    store, service = _setup(tmp_db_path, (1, 6))
    date, now = "2026-09-14", datetime(2026, 9, 14, 8, tzinfo=BJ)
    with store._transact() as conn:
        conn.execute("UPDATE server_exercise_plan_diet_rules SET rule_key=NULL WHERE user_id=1 AND plan_version='v4'")
        conn.execute("""INSERT INTO server_exercise_diet_checkins
            (id,user_id,date,plan_version,rule_key,status,deadline_at,created_at,updated_at)
            VALUES ('empty-diet',1,?,'v4','','completed',?,?,?)""", (date, "2026-09-15 00:00:00", date, date))

    SampleDataInitializationService(tmp_db_path).ensure_user_sample_data(1)

    with store._transact() as conn:
        rule_keys = [row[0] for row in conn.execute("""SELECT rule_key FROM server_exercise_plan_diet_rules
            WHERE user_id=1 AND plan_version='v4' ORDER BY sort_order""")]
        preserved_keys = [row[0] for row in conn.execute("""SELECT rule_key FROM server_exercise_plan_diet_rules
            WHERE user_id=6 AND plan_version='v4' ORDER BY sort_order""")]
        score = service.settle(conn, 1, date, now)
        empty_fact = conn.execute("""SELECT 1 FROM server_exercise_diet_checkins
            WHERE user_id=1 AND date=? AND plan_version='v4' AND rule_key=''""", (date,)).fetchone()

    assert rule_keys == list(DIET_RULES)
    assert preserved_keys == list(DIET_RULES)
    assert score["cats"]["饮食约束"] == {"s": 0.0, "m": 15.0}
    assert empty_fact is None


def test_v4_plan_has_seven_days_215_cardio_minutes_and_low_impact_frequency_guide(tmp_db_path):
    store, _ = _setup(tmp_db_path)
    with store._connect() as conn:
        items = [dict(row) for row in conn.execute("""SELECT day_key,section,name,sets,intensity,tags_json
            FROM server_exercise_plan_items WHERE user_id=1 AND plan_version='v4' AND variant='gym'""")]
        schedules = [row[0] for row in conn.execute("""SELECT item FROM server_exercise_plan_schedule_items
            WHERE user_id=1 AND plan_version='v4'""")]
        progress = [row[0] for row in conn.execute("""SELECT text FROM server_exercise_plan_progress_items
            WHERE user_id=1 AND plan_version='v4' ORDER BY sort_order""")]
    assert {row["day_key"] for row in items} == {"周一", "周二", "周三", "周四", "周五", "六", "日"}
    cardio_minutes = sum(int(row["sets"].split("分钟")[0]) for row in items if row["section"] == "有氧")
    assert cardio_minutes == 215
    intensities = " ".join(row["intensity"] for row in items)
    assert all(band in intensities for band in ("55–60", "60–65", "68–75", "78–85"))
    stair = next(json.loads(row["tags_json"]) for row in items if "爬楼" in row["name"])
    assert stair["optional"] == 1 and stair["scorePoints"] == 0
    assert not any("体重" in item or "体脂" in item for item in schedules)
    assert "80%" in progress[0] and "215分钟" in progress[1]


def test_v4_schedule_never_scores_and_body_fields_score_independently(tmp_db_path):
    store, service = _setup(tmp_db_path)
    now, date = datetime(2026, 9, 14, 8, tzinfo=BJ), "2026-09-14"
    with store._transact() as conn:
        _daily(conn, 1, date, weight=100)
        conn.execute("""INSERT INTO server_exercise_item_scores
            (id,user_id,date,plan_version,item_key,earned_points,max_points,score_scope,created_at,updated_at)
            VALUES ('legacy-sc',1,?,'v4',?,40,40,'schedule',?,?)""", (date, f"sc-{date}-0", date, date))
        score = service.settle(conn, 1, date, now)
        body = [tuple(row) for row in conn.execute("SELECT item_key,earned_points,max_points FROM server_exercise_item_scores WHERE user_id=1 AND date=? AND score_scope='body' ORDER BY item_key", (date,))]
        schedule = conn.execute("SELECT earned_points,max_points,status FROM server_exercise_item_scores WHERE id='legacy-sc'").fetchone()
    assert body == [("body:body_fat_rate", 0.0, 5.0), ("body:weight", 5.0, 5.0)]
    assert tuple(schedule) == (0.0, 0.0, "ignored")
    assert score["total"] == 5


@pytest.mark.parametrize(("weight", "body_fat", "expected"), [
    (100, None, 5), (None, 35, 5), (100, 35, 10),
])
def test_v4_body_fields_each_score_five_on_save(tmp_db_path, weight, body_fat, expected):
    store, service = _setup(tmp_db_path)
    date = "2026-09-14"
    with store._transact() as conn:
        _daily(conn, 1, date, weight, body_fat)
        score = service.settle(conn, 1, date, datetime(2026, 9, 14, 8, tzinfo=BJ))
        body = conn.execute("""SELECT SUM(earned_points),SUM(max_points) FROM server_exercise_item_scores
            WHERE user_id=1 AND date=? AND score_scope='body'""", (date,)).fetchone()
    assert tuple(body) == (expected, 10.0)
    assert score["cats"]["身体记录"]["s"] == expected


def test_v4_diet_deadline_penalties_are_idempotent_and_offline_completion_repairs_one(tmp_db_path):
    store, service = _setup(tmp_db_path)
    changes = []
    service.record_change = lambda _conn, _user, table, record_id, operation='upsert': changes.append((table, record_id, operation))
    date = "2026-09-14"
    with store._transact() as conn:
        assert service.close_diet(conn, 1, date, datetime(2026, 9, 15, 0, 0, 1, tzinfo=BJ)) == 3
        changes.clear()
        assert service.close_diet(conn, 1, date, datetime(2026, 9, 15, 1, tzinfo=BJ)) == 0
        assert changes == []
        rows = conn.execute("SELECT amount FROM server_reward_ledger WHERE user_id=1 AND source_type='exercise_diet_penalty'").fetchall()
        assert [row[0] for row in rows] == [-20.0, -20.0, -20.0]
        assert conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()[0] == -60
        service.set_diet(conn, 1, date, DIET_RULES[0], True, "2026-09-14 23:59:00", datetime(2026, 9, 15, 1, tzinfo=BJ))
        rows = conn.execute("SELECT amount FROM server_reward_ledger WHERE user_id=1 AND source_type='exercise_diet_penalty'").fetchall()
        assert [row[0] for row in rows] == [-20.0, -20.0]
        assert conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()[0] == -40
        assert any(table == "server_reward_ledger" and operation == "delete" for table, _, operation in changes)
        assert any(table == "server_user_wallets" for table, _, _ in changes)
        with pytest.raises(ValueError, match="diet_deadline_passed"):
            service.set_diet(conn, 1, date, DIET_RULES[1], True, "2026-09-15 00:00:00", datetime(2026, 9, 15, 1, tzinfo=BJ))


def test_v4_user_marked_diet_failure_is_zero_score_without_early_penalty(tmp_db_path):
    store, service = _setup(tmp_db_path)
    date, now = "2026-09-14", datetime(2026, 9, 14, 20, tzinfo=BJ)
    with store._transact() as conn:
        score = service.set_diet(conn, 1, date, DIET_RULES[0], "failed", f"{date} 20:00:00", now)
        fact = conn.execute("""SELECT status,failure_reason,penalty_source_id FROM server_exercise_diet_checkins
            WHERE user_id=1 AND date=? AND rule_key=?""", (date, DIET_RULES[0])).fetchone()
        assert service.close_diet(conn, 1, date, datetime(2026, 9, 15, 0, 1, tzinfo=BJ)) == 2
        penalties = conn.execute("SELECT source_id FROM server_reward_ledger WHERE user_id=1 AND source_type='exercise_diet_penalty' ORDER BY source_id").fetchall()
    assert tuple(fact) == ("failed", "user_marked_failed", None)
    assert score["cats"]["饮食约束"] == {"s": 0.0, "m": 15.0}
    assert len(penalties) == len(set(penalties)) == 2


def test_v4_full_domains_keep_exercise_completion_reward_at_100(tmp_db_path):
    store, service = _setup(tmp_db_path, (1, 4))
    date, now = "2026-09-14", datetime(2026, 9, 14, 22, tzinfo=BJ)
    with store._transact() as conn:
        _daily(conn, 1, date, 100, 35)
        service.settle_body_deadline(conn, 1, date, datetime(2026, 9, 14, 9, tzinfo=BJ))
        for row in conn.execute("SELECT sort_order FROM server_exercise_plan_items WHERE user_id=1 AND plan_version='v4' AND day_key='周一' AND variant='gym'"):
            key = f"ex-{date}-g-{row['sort_order']}"
            conn.execute("""INSERT INTO server_exercise_checkins(id,user_id,log_id,plan_version,item_key,status,date,created_at,updated_at)
                VALUES (?,?,?,?,?,1,?,?,?)""", (f"check-{key}", 1, f"log-1-{date}", "v4", key, date, date, date))
        for rule in DIET_RULES:
            service.set_diet(conn, 1, date, rule, True, f"{date} 22:00:00", now)
        first = service.settle(conn, 1, date, now); second = service.settle(conn, 1, date, now)
        rewards = conn.execute("SELECT amount FROM server_reward_ledger WHERE user_id=1 AND source_type='exercise_completion_reward'").fetchall()
        other = conn.execute("SELECT COUNT(*) FROM server_exercise_item_scores WHERE user_id=4 AND date=?", (date,)).fetchone()[0]
    assert first["total"] == second["total"] == 100
    assert [row[0] for row in rewards] == [100.0]
    assert other == 0


def test_v4_repeated_settlement_creates_no_new_version_or_wallet_write(tmp_db_path):
    store, _ = _setup(tmp_db_path)
    service = ExerciseV4Service(
        store.reward_wallet_service,
        lambda conn, user_id, table, record_id, operation="upsert": store._record_server_change(
            conn, user_id, table, record_id, operation, {"id": record_id},
        ),
    )
    date, now = "2026-09-14", datetime(2026, 9, 14, 8, tzinfo=BJ)
    with store._transact() as conn:
        service.settle(conn, 1, date, now)
        before = (
            conn.execute("SELECT COUNT(*) FROM server_change_log WHERE user_id=1").fetchone()[0],
            conn.execute("SELECT current_version FROM server_version_counters WHERE user_id=1").fetchone()[0],
            tuple(conn.execute("SELECT COUNT(*),COALESCE(SUM(balance),0) FROM server_user_wallets WHERE user_id=1").fetchone()),
        )
        service.settle(conn, 1, date, now)
        after = (
            conn.execute("SELECT COUNT(*) FROM server_change_log WHERE user_id=1").fetchone()[0],
            conn.execute("SELECT current_version FROM server_version_counters WHERE user_id=1").fetchone()[0],
            tuple(conn.execute("SELECT COUNT(*),COALESCE(SUM(balance),0) FROM server_user_wallets WHERE user_id=1").fetchone()),
        )

    assert after == before


def test_body_deadline_penalty_survives_late_body_backfill_without_score(tmp_db_path):
    store, service = _setup(tmp_db_path)
    date, late = "2026-09-14", datetime(2026, 9, 14, 10, tzinfo=BJ)
    with store._transact() as conn:
        fact = service.settle_body_deadline(conn, 1, date, late)
        _daily(conn, 1, date, 100, 35)
        score = service.settle(conn, 1, date, late)
        penalty = conn.execute("SELECT amount FROM server_reward_ledger WHERE user_id=1 AND source_type='body_metric_deadline_penalty'").fetchone()[0]
        saved = conn.execute("SELECT status FROM server_exercise_deadline_facts WHERE user_id=1 AND date=?", (date,)).fetchone()[0]
    assert fact["status"] == saved == "failed" and penalty == -50
    assert score["cats"]["身体记录"] == {"s": 0.0, "m": 10.0}


def test_body_deadline_freezes_each_field_and_stays_idempotent(tmp_db_path):
    store, service = _setup(tmp_db_path)
    date = "2026-09-14"
    with store._transact() as conn:
        _daily(conn, 1, date, weight=100)
        service.settle_body_deadline(conn, 1, date, datetime(2026, 9, 14, 9, tzinfo=BJ))
        conn.execute("UPDATE server_exercise_daily_logs SET body_fat_rate=30 WHERE user_id=1 AND date=?", (date,))
        score = service.settle(conn, 1, date, datetime(2026, 9, 14, 10, tzinfo=BJ))
        repeated = service.settle_body_deadline(conn, 1, date, datetime(2026, 9, 14, 10, tzinfo=BJ))
        facts = [tuple(row) for row in conn.execute("SELECT fact_type,status FROM server_exercise_deadline_facts WHERE user_id=1 AND date=? ORDER BY fact_type", (date,))]
        penalties = conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1 AND source_type='body_metric_deadline_penalty'").fetchone()[0]
    assert facts == [("body_fat_rate", "failed"), ("body_metrics", "failed"), ("body_weight", "complete")]
    assert score["cats"]["身体记录"] == {"s": 5.0, "m": 10.0} and penalties == 1
    assert repeated["_changed"] is False


def test_v4_state_never_replaces_its_three_domains_with_a_locked_v2_snapshot(tmp_db_path, monkeypatch):
    store, service = _setup(tmp_db_path)
    date = "2026-09-09"
    with store._transact() as conn:
        conn.execute("""INSERT INTO server_exercise_daily_logs
            (id,user_id,date,plan_version,exercise_type,weight,score_snapshot,created_at,updated_at)
            VALUES ('v2-only',1,?,'v2','daily',100,?,'2026-09-09 08:00:00','2026-09-09 08:00:00')""",
            (date, json.dumps({"total": 40, "cats": {"守时": {"s": 5, "m": 5}}})))
    monkeypatch.setattr(server_module, "_exercise_db_path", lambda: str(tmp_db_path))
    monkeypatch.setattr(server_module, "_exercise_v4", lambda: service)

    state = server_module.get_exercise_state(date, "v4", {"id": 1})

    assert state["daily_log"] is None
    assert set(state["score"]["cats"]) == {"运动训练", "饮食约束", "身体记录"}


def test_overdue_v4_notifies_only_when_deadline_facts_change(tmp_db_path, monkeypatch):
    store, service = _setup(tmp_db_path)
    calls, now = [], datetime(2026, 9, 14, 10, tzinfo=BJ)
    monkeypatch.setattr(server_module, "_exercise_db_path", lambda: str(tmp_db_path))
    monkeypatch.setattr(server_module, "_exercise_v4", lambda: service)
    monkeypatch.setattr(server_module, "_beijing_now", lambda: now)
    monkeypatch.setattr(server_module.sync_hub, "_notify_clients", lambda tables, user_id: calls.append((tables, user_id)))

    assert server_module._lock_overdue_body_metrics() == 1
    assert calls == [(["exercise_daily_logs", "exercise_deadline_facts", "exercise_item_scores", "exercise_settlements", "reward_ledger", "user_wallets"], 1)]
    calls.clear()
    assert server_module._lock_overdue_body_metrics() == 0 and calls == []


def test_v4_startup_compensation_notifies_only_for_real_changes(tmp_db_path, monkeypatch):
    store, _ = _setup(tmp_db_path)
    now = datetime(2026, 9, 12, 10, tzinfo=BJ)
    notifications = []
    monkeypatch.setattr(server_module, "store", store)
    monkeypatch.setattr(server_module, "_beijing_today", lambda: "2026-09-12")
    monkeypatch.setattr(server_module, "_beijing_now", lambda: now)
    monkeypatch.setattr(server_module.sync_hub, "_notify_clients", lambda tables, user_id: notifications.append((tables, user_id)))

    first = server_module._settle_completed_exercise_days()
    with store._connect() as conn:
        before = (
            conn.execute("SELECT COUNT(*) FROM server_change_log WHERE user_id=1").fetchone()[0],
            conn.execute("SELECT current_version FROM server_version_counters WHERE user_id=1").fetchone()[0],
            tuple(conn.execute("SELECT COUNT(*),COALESCE(SUM(balance),0) FROM server_user_wallets WHERE user_id=1").fetchone()),
        )
    second = server_module._settle_completed_exercise_days()
    with store._connect() as conn:
        after = (
            conn.execute("SELECT COUNT(*) FROM server_change_log WHERE user_id=1").fetchone()[0],
            conn.execute("SELECT current_version FROM server_version_counters WHERE user_id=1").fetchone()[0],
            tuple(conn.execute("SELECT COUNT(*),COALESCE(SUM(balance),0) FROM server_user_wallets WHERE user_id=1").fetchone()),
        )

    assert first == 1 and second == 0
    assert len(notifications) == 1
    assert after == before
