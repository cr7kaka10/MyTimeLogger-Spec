from datetime import datetime, timezone, timedelta
import json
import sqlite3

import pytest

import server.server as server_module
from server.domain.exercise_v4_service import DIET_RULES, PLAN_POLICIES, V5_DIET_POINTS, V5_MEAL_RULES, ExerciseV4Service, OPTIONAL_BODY_POLICY_KEY, optional_body_policy_active
from server.domain.sample_data_initialization_service import SampleDataInitializationService
from server.domain.reward_candidate_builder import RewardCandidateBuilder
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


def test_optional_body_policy_date_boundary_and_200_reward(tmp_db_path):
    store, service = _setup(tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO server_exercise_policy_metadata VALUES(?,?,?)", (OPTIONAL_BODY_POLICY_KEY, "2026-11-01", "2026-10-31"))
        assert not optional_body_policy_active(conn, "2026-10-31")
        assert optional_body_policy_active(conn, "2026-11-01")
        assert service.settle_body_deadline(conn, 1, "2026-11-01", datetime(2026, 11, 1, 10, tzinfo=BJ)) is None
        score = service.settle(conn, 1, "2026-11-01", datetime(2026, 11, 1, 10, tzinfo=BJ))
        assert score["cats"]["身体记录"]["m"] == 0
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='body_metric_deadline_penalty'").fetchone()[0] == 0
        service._reconcile_completion_reward(conn, 1, "2026-11-01", True, "2026-11-01 10:00:00")
        service._reconcile_completion_reward(conn, 1, "2026-11-01", True, "2026-11-01 10:00:00")
        v5 = ExerciseV4Service(store.reward_wallet_service, lambda *args: None, plan_version="v5")
        assert v5.settle_body_deadline(conn, 1, "2026-11-01", datetime(2026, 11, 1, 10, tzinfo=BJ)) is None
        v5._reconcile_completion_reward(conn, 1, "2026-11-01", True, "2026-11-01 10:00:00")
        service._reconcile_completion_reward(conn, 1, "2026-10-31", True, "2026-10-31 10:00:00")
        amounts = [row[0] for row in conn.execute("SELECT amount FROM server_reward_ledger WHERE source_type='exercise_completion_reward' ORDER BY target_date, id")]
        assert amounts == [100, 200, 200]


def test_v5_cutover_settles_training_fifty_without_legacy_diet(tmp_db_path):
    store, _ = _setup(tmp_db_path)
    date = "2026-11-03"
    now = datetime(2026, 11, 3, 20, tzinfo=BJ)
    service = ExerciseV4Service(store.reward_wallet_service, lambda *args: None, "v5")
    with store._transact() as conn:
        conn.execute("INSERT INTO server_diet_habit_migrations VALUES(1,?,?)", (date, date))
        conn.execute("INSERT OR REPLACE INTO server_exercise_policy_metadata VALUES(?,?,?)",
                     (OPTIONAL_BODY_POLICY_KEY, date, date))
        conn.execute("INSERT OR REPLACE INTO server_exercise_policy_metadata VALUES('v5_meal_timing',?,?)", (date, date))
        conn.execute("INSERT INTO server_exercise_daily_logs(id,user_id,date,plan_version,exercise_type,created_at,updated_at) "
                     "VALUES ('cutover-log',1,?,'v5','daily',?,?)", (date, date, date))
        for item in conn.execute("SELECT sort_order FROM server_exercise_plan_items WHERE user_id=1 AND plan_version='v5' AND day_key='周二' AND variant='gym' AND is_active=1"):
            key = f"ex-{date}-g-{item['sort_order']}"
            conn.execute("INSERT INTO server_exercise_checkins(id,user_id,log_id,plan_version,item_key,status,date,created_at,updated_at) "
                         "VALUES (?,?,?,'v5',?,1,?,?,?)", (f"check-{key}", 1, "cutover-log", key, date, date, date))
        first = service.settle(conn, 1, date, now)
        second = service.settle(conn, 1, date, now)
        assert first["cats"]["饮食约束"] == {"s": 0.0, "m": 0.0}
        assert first["cats"]["运动训练"] == {"s": 50.0, "m": 50.0}
        assert first == second
        assert conn.execute("SELECT COUNT(*) FROM server_exercise_diet_checkins WHERE user_id=1 AND date=?", (date,)).fetchone()[0] == 0
        assert conn.execute("SELECT SUM(amount) FROM server_reward_ledger WHERE source_type='exercise_completion_reward' AND target_date=?", (date,)).fetchone()[0] == 200
        with pytest.raises(ValueError, match="diet_habit_upgrade_required"):
            service.set_diet(conn, 1, date, "breakfast_on_time", True, f"{date} 08:00:00", now)


def test_body_penalty_rebuild_keeps_old_date_and_skips_new_date(tmp_db_path):
    store, _ = _setup(tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO server_exercise_policy_metadata VALUES(?,?,?)", (OPTIONAL_BODY_POLICY_KEY, "2026-11-01", "2026-10-31"))
        for day in ("2026-10-31", "2026-11-01"):
            conn.execute("""INSERT INTO server_exercise_deadline_facts
                (id,user_id,date,plan_version,fact_type,status,deadline_at,reason,penalty_source_id,penalty_amount,created_at,updated_at)
                VALUES (?,1,?,'v4','body_metrics','failed',?,'missing',?,-50,?,?)""",
                (f"body-deadline:1:{day}:v4", day, f"{day} 09:00:00", f"body-metric-deadline-penalty:1:{day}", day, day))
        RewardCandidateBuilder(store)._replay_body_metric_deadline_penalties(conn, 1, "2026-10-31")
        rows = [tuple(row) for row in conn.execute("SELECT target_date,amount FROM server_reward_ledger WHERE source_type='body_metric_deadline_penalty'")]
        assert rows == [("2026-10-31", -50)]


def test_optional_body_policy_skips_nine_oclock_scheduler(tmp_db_path, monkeypatch):
    store, _ = _setup(tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO server_exercise_policy_metadata VALUES(?,?,?)", (OPTIONAL_BODY_POLICY_KEY, "2026-11-01", "2026-10-31"))
    monkeypatch.setattr(server_module, "store", store)
    monkeypatch.setattr(server_module, "_exercise_conn", store._connect)
    monkeypatch.setattr(server_module, "_beijing_now", lambda: datetime(2026, 11, 1, 9, 2, tzinfo=BJ))
    assert server_module._lock_overdue_body_metrics() == 0
    assert server_module._exercise_weight_window("2026-11-01")["overdue"] is False
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE source_type='body_metric_deadline_penalty'").fetchone()[0] == 0


def test_v4_is_complete_idempotent_and_user_isolated(tmp_db_path):
    store, _ = _setup(tmp_db_path, (1, 4))
    repaired = SampleDataInitializationService(tmp_db_path).repair_v4_diet_rule_keys(1)
    assert repaired == 0
    with store._connect() as conn:
        assert [tuple(row) for row in conn.execute("SELECT user_id,value FROM server_system_config WHERE key='active_exercise_plan_version' ORDER BY user_id")] == [(1, "v5"), (4, "v5")]
        assert [tuple(row) for row in conn.execute("SELECT user_id,COUNT(*) FROM server_exercise_plan_items WHERE plan_version='v4' GROUP BY user_id ORDER BY user_id")] == [(1, 23), (4, 23)]
        assert [tuple(row) for row in conn.execute("SELECT user_id,COUNT(*) FROM server_exercise_plan_items WHERE plan_version='v5' GROUP BY user_id ORDER BY user_id")] == [(1, 41), (4, 41)]
        assert conn.execute("SELECT COUNT(*) FROM server_exercise_plan_versions WHERE version='scoring-v3'").fetchone()[0] == 0


def test_v5_publish_is_idempotent_and_does_not_override_manual_v4_switch(tmp_db_path):
    store, _ = _setup(tmp_db_path)
    seed = SampleDataInitializationService(tmp_db_path)
    with store._transact() as conn:
        conn.execute("UPDATE server_system_config SET value='v4' WHERE user_id=1 AND key='active_exercise_plan_version'")
    seed.ensure_user_sample_data(1)
    seed.ensure_user_sample_data(1)
    with store._connect() as conn:
        active = conn.execute("SELECT value FROM server_system_config WHERE user_id=1 AND key='active_exercise_plan_version'").fetchone()[0]
        items = conn.execute("SELECT COUNT(*) FROM server_exercise_plan_items WHERE user_id=1 AND plan_version='v5'").fetchone()[0]
        markers = conn.execute("SELECT COUNT(*) FROM server_sample_data_initializations WHERE user_id=1 AND module='exercise_plan_v5'").fetchone()[0]
    assert (active, items, markers) == ("v4", 41, 1)


def test_v5_quality_restore_is_idempotent_and_date_scoped(tmp_db_path, monkeypatch):
    store, _ = _setup(tmp_db_path)
    monkeypatch.setattr(server_module, "store", store)
    monkeypatch.setattr(server_module, "beijing_now", lambda: datetime(2026, 10, 27, 12, tzinfo=BJ))
    monkeypatch.setattr(server_module, "_exercise_write_change", lambda *args: None)
    old = ("protein_at_lunch_and_dinner", "vegetables_at_lunch_and_dinner",
           "controlled_staple_and_no_sugary_drink")
    with store._transact() as conn:
        for order, key in enumerate(old):
            conn.execute("UPDATE server_exercise_plan_diet_rules SET rule_key=?,content=? "
                         "WHERE user_id=1 AND id=?", (key, key, f"v5-diet-{order}"))
        conn.execute("INSERT OR IGNORE INTO server_exercise_policy_metadata VALUES('v5_meal_timing','2026-10-27','2026-10-27')")
        conn.execute("INSERT INTO server_exercise_item_scores(id,user_id,date,plan_version,item_key,earned_points,max_points,created_at) VALUES('historic-quality',1,'2026-10-27','v5','diet:protein_at_lunch_and_dinner',6,6,'2026-10-27')")
    assert server_module._restore_v5_quality_rules_on_startup() == 3
    assert server_module._restore_v5_quality_rules_on_startup() == 0
    v5 = ExerciseV4Service(store.reward_wallet_service, lambda *args: None, "v5")
    v4 = ExerciseV4Service(store.reward_wallet_service, lambda *args: None, "v4")
    with store._connect() as conn:
        assert conn.execute("SELECT effective_date FROM server_exercise_policy_metadata WHERE policy_key='v5_quality_restored'").fetchone()[0] == "2026-10-28"
        assert [row[0] for row in conn.execute("SELECT rule_key FROM server_exercise_plan_diet_rules WHERE user_id=1 AND plan_version='v5' AND sort_order<3 ORDER BY sort_order")] == ["no_sugary_drinks", "no_refined_staples", "no_snacks"]
        assert v5._diet_rules_for_date(conn, 1, "2026-10-27") == old + V5_MEAL_RULES
        assert v5._diet_rules_for_date(conn, 1, "2026-10-28") == ("no_sugary_drinks", "no_refined_staples", "no_snacks") + V5_MEAL_RULES
        assert sum(V5_DIET_POINTS[key] for key in v5._diet_rules_for_date(conn, 1, "2026-10-28")) == 50
        assert conn.execute("SELECT earned_points FROM server_exercise_item_scores WHERE id='historic-quality'").fetchone()[0] == 6
        assert v4._diet_rules_for_date(conn, 1, "2026-10-28") == DIET_RULES


@pytest.mark.parametrize("existing_policy", [False, True])
def test_v5_quality_restore_activates_safe_upgrade_day(tmp_db_path, monkeypatch, existing_policy):
    store, _ = _setup(tmp_db_path)
    monkeypatch.setattr(server_module, "store", store)
    now = datetime(2026, 10, 27, 12, tzinfo=BJ)
    monkeypatch.setattr(server_module, "beijing_now", lambda: now)
    monkeypatch.setattr(server_module, "_exercise_write_change", lambda *args: None)
    service = ExerciseV4Service(store.reward_wallet_service, lambda *args: None, "v5")
    with store._transact() as conn:
        conn.execute("INSERT OR IGNORE INTO server_exercise_policy_metadata VALUES('v5_meal_timing','2026-10-27','2026-10-27')")
        if existing_policy:
            conn.execute("INSERT INTO server_exercise_policy_metadata VALUES('v5_quality_restored','2026-10-28','2026-10-27')")
        service.ensure_diet_rows(conn, 1, "2026-10-27", now)
    assert server_module._restore_v5_quality_rules_on_startup() == 0
    assert server_module._restore_v5_quality_rules_on_startup() == 0
    with store._transact() as conn:
        assert conn.execute("SELECT effective_date FROM server_exercise_policy_metadata WHERE policy_key='v5_quality_restored'").fetchone()[0] == "2026-10-27"
        assert not service._quality_transition_day(conn, "2026-10-26")
        assert service._diet_rules_for_date(conn, 1, "2026-10-27") == ("no_sugary_drinks", "no_refined_staples", "no_snacks") + V5_MEAL_RULES
        service.set_diet(conn, 1, "2026-10-27", "no_sugary_drinks", "completed", None, now)
        service.set_diet(conn, 1, "2026-10-27", "no_refined_staples", "failed", None, now)
        assert [tuple(row) for row in conn.execute("SELECT rule_key,status FROM server_exercise_diet_checkins WHERE user_id=1 AND date='2026-10-27' AND rule_key IN ('no_sugary_drinks','no_refined_staples') ORDER BY rule_key")] == [("no_refined_staples", "failed"), ("no_sugary_drinks", "completed")]
        assert not conn.execute("SELECT 1 FROM server_exercise_diet_checkins WHERE user_id=1 AND date='2026-10-27' AND rule_key='protein_at_lunch_and_dinner'").fetchone()


def test_v5_hidden_quality_transition_exempts_pending_without_exempting_meals(tmp_db_path):
    store, _ = _setup(tmp_db_path)
    service = ExerciseV4Service(store.reward_wallet_service, lambda *args: None, "v5")
    start = datetime(2026, 10, 27, 12, tzinfo=BJ)
    overdue = datetime(2026, 10, 28, 0, 1, tzinfo=BJ)
    with store._transact() as conn:
        conn.execute("INSERT OR IGNORE INTO server_exercise_policy_metadata VALUES('v5_meal_timing','2026-10-27','2026-10-27')")
        conn.execute("INSERT INTO server_exercise_policy_metadata VALUES('v5_quality_restored','2026-10-28','2026-10-27')")
        service.ensure_diet_rows(conn, 1, "2026-10-27", start)
        old_key = "protein_at_lunch_and_dinner"
        old_source = f"exercise-diet-penalty:1:2026-10-27:v5:{old_key}"
        conn.execute("UPDATE server_exercise_diet_checkins SET status='failed',failure_reason='meal_window_passed',penalty_source_id=? WHERE user_id=1 AND date='2026-10-27' AND rule_key=?", (old_source, old_key))
        store.reward_wallet_service.append_ledger_in_txn(conn, 1, -20, "exercise_diet_penalty", old_source,
            "旧质量项逾期", "2026-10-27", old_source, "2026-10-28 00:01:00")
        assert service.close_diet(conn, 1, "2026-10-27", overdue) == 6
        assert service.close_diet(conn, 1, "2026-10-27", overdue) == 0
        reasons = [tuple(row) for row in conn.execute("SELECT rule_key,failure_reason FROM server_exercise_diet_checkins WHERE user_id=1 AND date='2026-10-27' AND rule_key IN ('protein_at_lunch_and_dinner','vegetables_at_lunch_and_dinner','controlled_staple_and_no_sugary_drink') ORDER BY rule_key")]
        assert len(reasons) == 3 and all(reason == "quality_transition_exempt" for _, reason in reasons)
        ledger = [row[0] for row in conn.execute("SELECT id FROM server_reward_ledger WHERE user_id=1 AND target_date='2026-10-27' AND source_type='exercise_diet_penalty'")]
        assert {entry.rsplit(':', 1)[-1] for entry in ledger} == set(V5_MEAL_RULES)
        assert not any(entry.endswith(key) for entry in ledger for key in PLAN_POLICIES["v5"]["diet_rules"])


def test_v5_restored_quality_only_pending_auto_fails_after_midnight(tmp_db_path):
    store, _ = _setup(tmp_db_path)
    service = ExerciseV4Service(store.reward_wallet_service, lambda *args: None, "v5")
    before = datetime(2026, 10, 28, 22, tzinfo=BJ)
    after = datetime(2026, 10, 29, 0, 1, tzinfo=BJ)
    with store._transact() as conn:
        conn.execute("INSERT INTO server_exercise_policy_metadata VALUES('v5_quality_restored','2026-10-28','2026-10-27')")
        conn.execute("INSERT OR IGNORE INTO server_exercise_policy_metadata VALUES('v5_meal_timing','2026-10-26','2026-10-25')")
        service.ensure_diet_rows(conn, 1, "2026-10-28", before)
        service.set_diet(conn, 1, "2026-10-28", "no_sugary_drinks", "completed", None, before)
        service.set_diet(conn, 1, "2026-10-28", "no_refined_staples", "failed", None, before)
        service.close_diet(conn, 1, "2026-10-28", after)
        assert service.close_diet(conn, 1, "2026-10-28", after) == 0
        facts = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT rule_key,status,failure_reason FROM server_exercise_diet_checkins WHERE user_id=1 AND date='2026-10-28'")}
        assert facts["no_sugary_drinks"] == ("completed", None)
        assert facts["no_refined_staples"] == ("failed", "user_marked_failed")
        assert facts["no_snacks"] == ("failed", "meal_window_passed")
        penalties = [r[0] for r in conn.execute("SELECT id FROM server_reward_ledger WHERE user_id=1 AND target_date='2026-10-28' AND source_type='exercise_diet_penalty'")]
        assert sum(id.endswith(":no_snacks") for id in penalties) == 1
        assert not any(id.endswith(":no_sugary_drinks") or id.endswith(":no_refined_staples") for id in penalties)
        assert service._diet_rules_for_date(conn, 1, "2026-11-02") == ()


def test_v5_meal_deadline_only_auto_fails_pending(tmp_db_path):
    store, _ = _setup(tmp_db_path)
    service = ExerciseV4Service(store.reward_wallet_service, lambda *args: None, "v5")
    date = "2026-10-28"
    with store._transact() as conn:
        conn.execute("INSERT OR IGNORE INTO server_exercise_policy_metadata VALUES('v5_meal_timing','2026-10-26','2026-10-25')")
        service.set_diet(conn, 1, date, "lunch_on_time", "completed", f"{date} 13:30:00", datetime(2026, 10, 28, 13, 30, tzinfo=BJ))
        service.set_diet(conn, 1, date, "breakfast_on_time", "failed", f"{date} 08:00:00", datetime(2026, 10, 28, 8, tzinfo=BJ))
        service.close_diet(conn, 1, date, datetime(2026, 10, 28, 19, 2, tzinfo=BJ))
        facts = {r[0]: r[1] for r in conn.execute("SELECT rule_key,status FROM server_exercise_diet_checkins WHERE user_id=1 AND date=?", (date,))}
        penalties = [r[0] for r in conn.execute("SELECT id FROM server_reward_ledger WHERE user_id=1 AND target_date=? AND source_type='exercise_diet_penalty'", (date,))]
        assert facts["lunch_on_time"] == "completed"
        assert facts["breakfast_on_time"] == "failed"
        assert len(penalties) == 1 and penalties[0].endswith(":dinner_on_time")


def test_v5_lunch_penalty_names_rule_and_cutoff(tmp_db_path):
    store, _ = _setup(tmp_db_path)
    service = ExerciseV4Service(store.reward_wallet_service, lambda *args: None, "v5")
    with store._transact() as conn:
        conn.execute("INSERT OR IGNORE INTO server_exercise_policy_metadata VALUES('v5_meal_timing','2026-10-26','2026-10-25')")
        now = datetime(2026, 10, 28, 13, 31, 1, tzinfo=BJ)
        service.close_diet(conn, 1, "2026-10-28", now)
        row = conn.execute("SELECT amount,description,id FROM server_reward_ledger WHERE user_id=1 AND id LIKE '%:lunch_on_time'").fetchone()
        assert row["amount"] == -20
        assert row["id"].endswith(":lunch_on_time")
        assert row["description"] == "午餐按时打卡逾期未完成（截止 2026-10-28 13:31，北京时间）"


def test_v5_cardio_v3_revision_upgrades_v2_rows_idempotently(tmp_db_path):
    store, _ = _setup(tmp_db_path)
    seed = SampleDataInitializationService(tmp_db_path)
    with store._transact() as conn:
        _daily(conn, 1, "2026-10-18")
        conn.execute("""INSERT INTO server_exercise_checkins(id,user_id,log_id,plan_version,item_key,status,date,created_at,updated_at)
            VALUES ('historic-v5-check',1,'log-1-2026-10-18','v5','v5-日-gym-2',1,'2026-10-18','2026-10-18','2026-10-18')""")
        conn.execute("""INSERT INTO server_exercise_item_scores(id,user_id,date,plan_version,item_key,earned_points,max_points,created_at)
            VALUES ('historic-v5-score',1,'2026-10-18','v5','v5-日-gym-2',15,15,'2026-10-18')""")
        conn.execute("UPDATE server_system_config SET value='v4' WHERE user_id=1 AND key='active_exercise_plan_version'")
        conn.execute("""UPDATE server_exercise_plan_items SET name='卧式健身车（无则椭圆）'
            WHERE user_id=1 AND id='v5-日-gym-2'""")
        conn.execute("DELETE FROM server_sample_data_initializations WHERE user_id=1 AND module='exercise_plan_v5_cardio_v3'")
        conn.execute("DELETE FROM server_change_log WHERE user_id=1 AND change_id LIKE 'exercise-v5-cardio-v3:%'")
    seed.ensure_user_sample_data(1)
    seed.ensure_user_sample_data(1)
    with store._connect() as conn:
        active = conn.execute("SELECT value FROM server_system_config WHERE user_id=1 AND key='active_exercise_plan_version'").fetchone()[0]
        rows = conn.execute("SELECT id,day_key,name,tags_json FROM server_exercise_plan_items WHERE user_id=1 AND plan_version='v5'").fetchall()
        markers = conn.execute("SELECT COUNT(*) FROM server_sample_data_initializations WHERE user_id=1 AND module='exercise_plan_v5_cardio_v3'").fetchone()[0]
        changes = conn.execute("SELECT COUNT(*) FROM server_change_log WHERE user_id=1 AND change_id LIKE 'exercise-v5-cardio-v3:%'").fetchone()[0]
        history = conn.execute("SELECT (SELECT status FROM server_exercise_checkins WHERE id='historic-v5-check'),(SELECT earned_points FROM server_exercise_item_scores WHERE id='historic-v5-score')").fetchone()
    assert active == "v4"
    assert len(rows) == 41 and len({row["id"] for row in rows}) == 41
    assert [row["day_key"] for row in rows if "爬楼机" in row["name"]] == ["周三", "周五", "日"]
    assert all("卧式健身车" not in row["name"] for row in rows)
    treadmills = [json.loads(row["tags_json"]) for row in rows if "跑步机" in row["name"]]
    assert len(treadmills) == 6 and all(item["durationMinutes"] == 10 for item in treadmills)
    assert markers == 1 and changes > 0
    assert tuple(history) == (1, 15.0)


def test_v5_cardio_revision_rolls_back_on_identity_mismatch(tmp_db_path):
    store, _ = _setup(tmp_db_path)
    seed = SampleDataInitializationService(tmp_db_path)
    with store._transact() as conn:
        conn.execute("DELETE FROM server_sample_data_initializations WHERE user_id=1 AND module='exercise_plan_v5_cardio_v2'")
        conn.execute("DELETE FROM server_change_log WHERE user_id=1 AND change_id LIKE 'exercise-v5-cardio-v2:%'")
        conn.execute("UPDATE server_exercise_plan_items SET name='迁移前名称' WHERE user_id=1 AND id='v5-周二-gym-0'")
        conn.execute("UPDATE server_exercise_plan_items SET day_key='错误日' WHERE user_id=1 AND id='v5-日-gym-2'")
    with pytest.raises(RuntimeError, match="identity_mismatch"):
        seed.ensure_user_sample_data(1)
    with store._connect() as conn:
        name = conn.execute("SELECT name FROM server_exercise_plan_items WHERE user_id=1 AND id='v5-周二-gym-0'").fetchone()[0]
        marker = conn.execute("SELECT COUNT(*) FROM server_sample_data_initializations WHERE user_id=1 AND module='exercise_plan_v5_cardio_v2'").fetchone()[0]
        changes = conn.execute("SELECT COUNT(*) FROM server_change_log WHERE user_id=1 AND change_id LIKE 'exercise-v5-cardio-v2:%'").fetchone()[0]
    assert (name, marker, changes) == ("迁移前名称", 0, 0)


def test_v5_state_endpoint_returns_authoritative_domains(tmp_db_path, monkeypatch):
    store, _ = _setup(tmp_db_path)
    monkeypatch.setattr(server_module, "store", store)
    monkeypatch.setattr(server_module, "_exercise_db_path", lambda: str(tmp_db_path))
    state = server_module.get_exercise_state("2026-10-20", "v5", {"id": 1})
    assert state["plan_version"] == "v5"
    assert state["score"]["plan_version"] == "v5"
    assert set(state["score"]["cats"]) == {"运动训练", "饮食约束", "身体记录"}
    assert {row["rule_key"] for row in state["diet_checkins"]} == set(PLAN_POLICIES["v5"]["diet_rules"])


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
        service.set_diet(conn, 1, date, DIET_RULES[0], True, "2026-09-14 23:59:00", datetime(2026, 9, 15, 1, tzinfo=BJ),
            recorded_at="2026-09-14 23:59:00")
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


def test_v5_late_sync_repairs_only_auto_failure_with_original_time(tmp_db_path):
    store, _ = _setup(tmp_db_path)
    service = ExerciseV4Service(store.reward_wallet_service, lambda *args: None, "v5")
    date = "2026-10-28"
    with store._transact() as conn:
        conn.execute("INSERT OR IGNORE INTO server_exercise_policy_metadata VALUES('v5_meal_timing','2026-10-26','2026-10-25')")
        service.close_diet(conn, 1, date, datetime(2026, 10, 28, 13, 32, tzinfo=BJ))
        source = f"exercise-diet-penalty:1:{date}:v5:lunch_on_time"
        assert conn.execute("SELECT amount FROM server_reward_ledger WHERE id=?", (source,)).fetchone()[0] == -20
        service.set_diet(conn, 1, date, "lunch_on_time", "completed", f"{date} 13:30:00",
            datetime(2026, 10, 28, 14, tzinfo=BJ), recorded_at=f"{date} 13:30:00")
        assert conn.execute("SELECT status FROM server_exercise_diet_checkins WHERE user_id=1 AND date=? AND rule_key='lunch_on_time'", (date,)).fetchone()[0] == "completed"
        assert conn.execute("SELECT 1 FROM server_reward_ledger WHERE id=?", (source,)).fetchone() is None
        assert conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()[0] == -20
        service.set_diet(conn, 1, date, "dinner_on_time", "failed", f"{date} 14:00:00", datetime(2026, 10, 28, 14, tzinfo=BJ))
        with pytest.raises(ValueError, match="diet_deadline_passed"):
            service.set_diet(conn, 1, date, "dinner_on_time", "completed", f"{date} 18:59:00",
                datetime(2026, 10, 28, 19, 3, tzinfo=BJ), recorded_at=f"{date} 18:59:00")
        with pytest.raises(ValueError, match="diet_deadline_passed"):
            service.set_diet(conn, 1, date, "dinner_on_time", "completed", f"{date} 19:02:00",
                datetime(2026, 10, 28, 19, 3, tzinfo=BJ), recorded_at=f"{date} 19:02:00")


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


def test_v4_policy_is_a_stable_golden_contract():
    assert PLAN_POLICIES["v4"] == {
        "rule_version": "exercise-score-v4",
        "diet_rules": ("no_snacks", "no_sugary_drinks", "no_refined_staples"),
        "diet_penalty": -20,
        "effective_from": "2026-09-10",
    }


def test_v5_diet_failure_scores_zero_without_negative_coins(tmp_db_path):
    store, _ = _setup(tmp_db_path)
    service = ExerciseV4Service(store.reward_wallet_service, lambda *args: None, "v5")
    date, late = "2026-09-15", datetime(2026, 9, 16, 0, 1, tzinfo=BJ)
    with store._transact() as conn:
        assert service.close_diet(conn, 1, date, late) == 3
        score = service.settle(conn, 1, date, late)
        rows = conn.execute("SELECT rule_key,status,plan_version,penalty_source_id FROM server_exercise_diet_checkins WHERE user_id=1 AND date=?", (date,)).fetchall()
        penalties = conn.execute("SELECT amount FROM server_reward_ledger WHERE user_id=1 AND source_type='exercise_diet_penalty'").fetchall()
    assert {tuple(row) for row in rows} == {(key, "failed", "v5", None) for key in PLAN_POLICIES["v5"]["diet_rules"]}
    assert score["cats"]["饮食约束"] == {"s": 0.0, "m": 15.0}
    assert penalties == []


def test_v4_and_v5_same_day_facts_and_rewards_are_isolated(tmp_db_path):
    store, v4 = _setup(tmp_db_path)
    v5 = ExerciseV4Service(store.reward_wallet_service, lambda *args: None, "v5")
    date, now = "2026-09-15", datetime(2026, 9, 15, 8, tzinfo=BJ)
    with store._transact() as conn:
        for version, service in (("v4", v4), ("v5", v5)):
            conn.execute("""INSERT INTO server_exercise_daily_logs
                (id,user_id,date,plan_version,exercise_type,weight,body_fat_rate,created_at,updated_at)
                VALUES (?,?,?,?, 'daily',100,35,?,?)""", (f"log-{version}", 1, date, version, date, date))
            for row in conn.execute("SELECT sort_order FROM server_exercise_plan_items WHERE user_id=1 AND plan_version=? AND day_key='周二'", (version,)):
                key = f"ex-{date}-g-{row['sort_order']}"
                conn.execute("INSERT INTO server_exercise_checkins(id,user_id,log_id,plan_version,item_key,status,date,created_at,updated_at) VALUES (?,?,?,?,?,1,?,?,?)",
                             (f"check-{version}-{key}", 1, f"log-{version}", version, key, date, date, date))
            for rule in service.diet_rules:
                service.set_diet(conn, 1, date, rule, True, f"{date} 08:00:00", now)
            assert service.settle(conn, 1, date, now)["total"] == 100
        settlements = conn.execute("SELECT plan_version FROM server_exercise_settlements WHERE user_id=1 AND business_date=? ORDER BY plan_version", (date,)).fetchall()
        rewards = conn.execute("SELECT id FROM server_reward_ledger WHERE user_id=1 AND source_type='exercise_completion_reward' ORDER BY id").fetchall()
    assert [row[0] for row in settlements] == ["v4", "v5"]
    assert [row[0] for row in rewards] == [f"exercise-completion-reward:1:v4:{date}", f"exercise-completion-reward:1:v5:{date}"]


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
    with store._transact() as conn:
        conn.execute("UPDATE server_system_config SET value='v4' WHERE user_id=1 AND key='active_exercise_plan_version'")
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


def test_v5_monday_rest_exemption_starts_on_oct_26_and_preserves_older_dates(tmp_db_path):
    store, _ = _setup(tmp_db_path)
    service = ExerciseV4Service(store.reward_wallet_service, lambda *args: None, "v5")
    before, after = "2026-10-19", "2026-10-26"
    with store._transact() as conn:
        service.ensure_diet_rows(conn, 1, before, datetime(2026, 10, 19, 8, tzinfo=BJ))
        old_rows = conn.execute("SELECT COUNT(*) FROM server_exercise_diet_checkins WHERE user_id=1 AND date=?", (before,)).fetchone()[0]
        old_source = f"exercise-diet-penalty:1:{before}:v5:{service.diet_rules[0]}"
        service.wallet.append_ledger_in_txn(conn, 1, -20, "exercise_diet_penalty", old_source, "历史扣款", before, old_source, f"{before} 08:00:00")
        service.wallet.rebuild_wallet_snapshot_in_txn(conn, 1, lambda: f"{before} 08:00:00")
        service.ensure_diet_rows(conn, 1, before, datetime(2026, 10, 19, 9, tzinfo=BJ))
        old_penalties = conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1 AND id=?", (old_source,)).fetchone()[0]
        old_balance = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()[0]
        score = service.settle(conn, 1, after, datetime(2026, 10, 26, 8, tzinfo=BJ))
        new_rows = conn.execute("SELECT COUNT(*) FROM server_exercise_diet_checkins WHERE user_id=1 AND date=?", (after,)).fetchone()[0]
    assert old_rows == len(service.diet_rules) and (old_penalties, old_balance) == (1, -20)
    assert new_rows == 0 and score["cats"]["饮食约束"] == {"s": 0.0, "m": 0.0}
    with store._transact() as conn, pytest.raises(ValueError, match="unknown_diet_rule"):
        service.set_diet(conn, 1, after, service.diet_rules[0], True, f"{after} 08:00:00", datetime(2026, 10, 26, 8, tzinfo=BJ))
    with store._transact() as conn, pytest.raises(ValueError, match="diet_checkin_rest_day"):
        server_module.sync_hub._prepare_exercise_record(conn, "exercise_diet_checkins",
            {"date": after, "plan_version": "v5", "rule_key": service.diet_rules[0], "status": "pending"}, 1)


def test_rest_day_clears_only_effective_date_auto_diet_penalty(tmp_db_path):
    store, _ = _setup(tmp_db_path)
    service = ExerciseV4Service(store.reward_wallet_service, lambda *args: None, "v5")
    date, rule = "2026-10-26", "protein_at_lunch_and_dinner"
    source = f"exercise-diet-penalty:1:{date}:v5:{rule}"
    with store._transact() as conn:
        conn.execute("""INSERT INTO server_exercise_diet_checkins
            (id,user_id,date,plan_version,rule_key,status,deadline_at,created_at,updated_at,failure_reason,penalty_source_id)
            VALUES (?,?,?,'v5',?,'failed',?,?,?,'meal_window_passed',?)""",
            (f"diet:1:{date}:v5:{rule}", 1, date, rule, f"{date} 24:00:00", date, date, source))
        service.wallet.append_ledger_in_txn(conn, 1, -20, "exercise_diet_penalty", source, "旧自动扣款", date, source, f"{date} 00:01:00")
        service.wallet.rebuild_wallet_snapshot_in_txn(conn, 1, lambda: f"{date} 00:01:00")
        service.ensure_diet_rows(conn, 1, date, datetime(2026, 10, 26, 8, tzinfo=BJ))
        assert conn.execute("SELECT COUNT(*) FROM server_exercise_diet_checkins WHERE user_id=1 AND date=?", (date,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1 AND source_type='exercise_diet_penalty'").fetchone()[0] == 0
        assert conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()[0] == 0
