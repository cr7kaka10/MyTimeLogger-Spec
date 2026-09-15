import asyncio
import inspect
import json
import sqlite3
from datetime import datetime, timedelta, timezone

from server.domain.exercise_v4_service import ExerciseV4Service
from server.domain.reward_candidate_builder import RewardCandidateBuilder
from server.domain.sample_data_initialization_service import SampleDataInitializationService
from server.domain.reward_rebuild_diagnostics import failure_report
from server.domain.reward_rebuild_service import RewardRebuildService
from server.domain.reward_rebuild_service import RewardRebuildError
from server.db_wrapper import ServerDBWrapper
from server.models.server_schema import ensure_server_schema
from server.store import ServerSleepStore
from server.sync_hub import SyncHub


BJ = timezone(timedelta(hours=8))


def test_wallet_snapshot_rebuild_skips_unchanged_balance_and_version_write(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','p','2026-09-12')")
        conn.execute("INSERT INTO server_user_wallets(user_id,balance,updated_at) VALUES(1,0,'2026-09-12 10:00:00')")
        before = (
            conn.execute("SELECT COUNT(*) FROM server_change_log WHERE user_id=1").fetchone()[0],
            conn.execute("SELECT current_version FROM server_version_counters WHERE user_id=1").fetchone(),
        )
        snapshot = store.reward_wallet_service.rebuild_wallet_snapshot_in_txn(conn, 1, lambda: "2026-09-12 10:00:01")
        after = (
            conn.execute("SELECT COUNT(*) FROM server_change_log WHERE user_id=1").fetchone()[0],
            conn.execute("SELECT current_version FROM server_version_counters WHERE user_id=1").fetchone(),
            conn.execute("SELECT balance,updated_at FROM server_user_wallets WHERE user_id=1").fetchone(),
        )

    assert snapshot["balance"] == 0
    assert after[:2] == before
    assert tuple(after[2]) == (0.0, "2026-09-12 10:00:00")


def _candidate_task_rows(tmp_db_path, completed_times):
    store = ServerSleepStore(db_path=tmp_db_path)
    stamp = "2026-08-25 12:00:00"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','p',?)", (stamp,))
        conn.execute("INSERT INTO server_tasks(id,user_id,title,status,raw_json,updated_at) VALUES('task-1',1,'任务',2,?,?)", (json.dumps({"completedTime": completed_times[0]}), stamp))
        conn.execute("INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty,updated_at) VALUES(1,'task','task-1',0.1,0.1,?)", (stamp,))
        for index, completed in enumerate(completed_times):
            conn.execute("INSERT INTO server_reward_ledger(id,user_id,amount,source_type,source_id,description,target_date,occurred_at,created_at,updated_at) VALUES(?,1,0.1,'task_complete',?,'√ 清单 任务','2026-08-25',?,?,?)", (f"old-{index}", f"task-1#{completed}", stamp, stamp, stamp))
    RewardCandidateBuilder(store).build(1, "2026-08-17")
    with store._connect() as conn:
        return [row[0] for row in conn.execute("SELECT source_id FROM server_reward_ledger WHERE user_id=1 AND source_type='task_complete' ORDER BY source_id")]


def test_candidate_replays_v4_diet_and_body_deadline_facts_without_schedule_scores(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','p','2026-09-01')")
    SampleDataInitializationService(tmp_db_path).ensure_user_sample_data(1)
    service = ExerciseV4Service(store.reward_wallet_service, lambda *_args: None)
    target_date = "2026-09-09"
    with store._transact() as conn:
        service.close_diet(conn, 1, target_date, datetime(2026, 9, 10, 0, 0, 1, tzinfo=BJ))
        service.settle_body_deadline(conn, 1, target_date, datetime(2026, 9, 9, 9, 0, 1, tzinfo=BJ))
        conn.execute("""INSERT INTO server_exercise_item_scores
            (id,user_id,date,plan_version,item_key,earned_points,max_points,score_scope,status,created_at,updated_at)
            VALUES('poison',1,?,'v4','sc-poison',999,999,'schedule','active',?,?)""",
            (target_date, target_date, target_date))
        live = [tuple(row) for row in conn.execute("""SELECT id,source_type,amount FROM server_reward_ledger
            WHERE user_id=1 AND source_type IN ('exercise_diet_penalty','body_metric_deadline_penalty') ORDER BY id""")]

    RewardCandidateBuilder(store).build(1, "2026-09-01")
    with store._connect() as conn:
        rebuilt = [tuple(row) for row in conn.execute("""SELECT id,source_type,amount FROM server_reward_ledger
            WHERE user_id=1 AND source_type IN ('exercise_diet_penalty','body_metric_deadline_penalty') ORDER BY id""")]
        completion = conn.execute("SELECT amount FROM server_reward_ledger WHERE source_type='exercise_completion_reward'").fetchone()[0]
    assert rebuilt == live
    assert sorted(row[2] for row in rebuilt) == [-50.0, -20.0, -20.0, -20.0]
    assert completion == 0


def test_candidate_reference_report_keeps_stable_check_and_safe_suffix():
    error = RewardRebuildService._candidate_error("orphan_backpack_event", "sensitive-record-123456")

    report = failure_report(error, trace_id="trace-1234", job_id="job-1")

    assert report["code"] == "candidate_reference_invalid"
    assert report["causes"][-1]["code"] == "orphan_backpack_event"
    assert report["causes"][-1]["record_id_suffix"] == "123456"


def test_candidate_failure_path_records_its_current_stage():
    source = inspect.getsource(RewardRebuildService.build_and_publish)

    assert 'stage=current_stage, event="finish", outcome="failure"' in source


def test_behavior_revision_report_is_publish_specific_and_lists_changed_tables():
    error = RewardRebuildError("behavior_revision_changed")
    error.reward_rebuild_details = {
        "chain": "publish", "check": "behavior_revision_changed",
        "message_zh": "重建期间以下金币事实发生变化", "changed_tables": ["server_tasks"],
    }
    report = failure_report(error, trace_id="trace-1234", job_id="job-1", failed_stage="publish")
    assert report["causes"][-1]["chain"] == "publish"
    assert report["causes"][-1]["changed_tables"] == ["server_tasks"]


def test_candidate_validation_accepts_fragment_events_only_with_fragment_provenance():
    source = inspect.getsource(RewardRebuildService.build_and_publish)

    assert "event.event_type NOT GLOB 'fragment_*'" in source
    assert "event.event_type IN" in source
    assert "fragment.id=event.fragment_id AND fragment.reward_id=event.reward_id" in source
    assert 'self._candidate_error("orphan_fragment_backpack_event"' in source


def test_snapshot_stage_has_paired_trace_events():
    source = inspect.getsource(RewardRebuildService.start)

    assert 'stage="snapshot", event="start", outcome="running"' in source
    assert 'stage="snapshot", event="finish", outcome="success"' in source


def test_restore_deletes_checkins_before_their_habit_parent():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u', 'p', '2026-08-25')")
    conn.execute("INSERT INTO server_habits (id, user_id, name, created_at, updated_at) VALUES ('current', 1, '当前', '2026-08-25', '2026-08-25')")
    conn.execute("INSERT INTO server_habit_checkins (id, user_id, habit_id, updated_at) VALUES ('current-checkin', 1, 'current', '2026-08-25')")
    service = RewardRebuildService.__new__(RewardRebuildService)
    snapshot = {"tables": {
        "server_habits": [{"id": "saved", "user_id": 1, "name": "已保存", "created_at": "2026-08-25", "updated_at": "2026-08-25"}],
        "server_habit_checkins": [{"id": "saved-checkin", "user_id": 1, "habit_id": "saved", "updated_at": "2026-08-25"}],
    }, "sync_state": [], "configs": []}

    service._restore_snapshot_in_txn(conn, 1, snapshot)

    assert conn.execute("SELECT habit_id FROM server_habit_checkins").fetchone()[0] == "saved"


def test_habit_pull_keeps_raw_valid_and_unique_checkin_block_counts(tmp_path):
    database_path = tmp_path / "habit-block-counts.db"
    conn = sqlite3.connect(database_path)
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users (id, username, password_hash, created_at) VALUES (1, 'u', 'p', '2026-08-25')")
    conn.commit()
    conn.close()
    db = ServerDBWrapper()
    db.log_path = str(database_path)
    hub = SyncHub(db)

    class Client:
        async def get_habits(self):
            return [{"id": "habit-a", "name": "A", "status": 0, "etag": "a"}]

        async def get_habit_sections(self):
            return []

        async def get_habit_checkins(self, *_):
            return [{"habitId": "habit-a", "checkins": []}, {"habitId": "habit-a", "checkins": []}, {}]

    stats = asyncio.run(hub._pull_habits(Client(), 1))

    assert stats["checkin_blocks_raw"] == 3
    assert stats["checkin_blocks_with_habit_id"] == 2
    assert stats["checkin_blocks_unique_habit_id"] == stats["checkin_blocks"] == 1


def test_candidate_rebuild_merges_only_equivalent_task_completion_times(tmp_db_path):
    same = _candidate_task_rows(tmp_db_path, ["2026-08-25T04:00:00.000+0000", "2026-08-25 12:00:00+08:00"])
    assert same == ["task-1#2026-08-25 12:00:00"]

    distinct = _candidate_task_rows(tmp_db_path + ".distinct", ["2026-08-25T04:00:00.000+0000", "2026-08-25T04:00:01.000+0000"])
    assert len(distinct) == 2


def test_candidate_replays_sleep_and_exercise_settlement_ledgers(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    stamp = "2026-08-25 12:00:00"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','p',?)", (stamp,))
        conn.execute("""INSERT INTO server_sleep_score_settlements
            (id,user_id,sleep_date,metrics_snapshot,score_breakdown,score_total,reward_amount,cycle_penalty,net_amount,settlement_status,missing_fields,rule_version,occurred_at,created_at,updated_at,completion_reward_amount,is_all_complete)
            VALUES('sleep',1,'2026-08-25','{}','{}',100,80,0,80,'scored','[]','sleep-score-v2',?,?,?,0,0)""", (stamp, stamp, stamp))
        conn.execute("""INSERT INTO server_exercise_settlements
            (id,user_id,business_date,plan_version,score_total,completed_items,total_items,settlement_status,rule_version,coin_amount,is_all_complete,completion_reward_amount,occurred_at,created_at,updated_at)
            VALUES('exercise',1,'2026-08-25','v1',100,4,4,'settled_reward','v1',0,0,0,?,?,?)""", (stamp, stamp, stamp))
        conn.execute("""INSERT INTO server_exercise_daily_logs
            (id,user_id,date,plan_version,exercise_type,day_name,created_at,updated_at)
            VALUES('log',1,'2026-08-25','v1','daily','一',?,?)""", (stamp, stamp))
        conn.execute("""INSERT INTO server_exercise_checkins
            (id,user_id,log_id,plan_version,item_key,status,date,locked_at,deadline_penalty_source_id,deadline_penalty_amount,created_at,updated_at)
            VALUES('deadline',1,'log','v1','sc-2026-08-25-0',-1,'2026-08-25',?,'body-metric-deadline:2026-08-25',-50,?,?)""", (stamp, stamp, stamp))
        conn.execute("""INSERT INTO server_reward_ledger
            (id,user_id,amount,source_type,source_id,description,target_date,created_at,updated_at)
            VALUES('old-deadline',1,-50,'body_metric_deadline_penalty','body-metric-deadline:2026-08-25','体重体脂逾期未填写（09:00）','2026-08-25',?,?)""", (stamp, stamp))

    RewardCandidateBuilder(store).build(1, "2026-08-17")

    with store._connect() as conn:
        rows = conn.execute("SELECT source_type,amount FROM server_reward_ledger ORDER BY source_type").fetchall()
    assert [(row[0], row[1]) for row in rows] == [
        ("body_metric_deadline_penalty", -50.0),
        ("exercise_completion_reward", 0.0), ("exercise_score", 0.0),
        ("sleep_completion_reward", 0.0), ("sleep_cycle_penalty", 0.0),
        ("sleep_settlement_reward", 80.0),
    ]


def test_candidate_rebuild_keeps_only_current_sleep_version_and_is_repeatable(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    date = "2026-09-01"
    stamp = "2026-09-01 22:40:16"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'versioned-sleep','p',?)", (stamp,))
        for version, score, updated in (("sleep-score-v1", 38, "2026-09-01 17:11:56"), ("sleep-score-v2", 28, stamp)):
            conn.execute("""INSERT INTO server_sleep_score_settlements
                (id,user_id,sleep_date,metrics_snapshot,score_breakdown,score_total,reward_amount,cycle_penalty,net_amount,settlement_status,missing_fields,rule_version,occurred_at,created_at,updated_at,completion_reward_amount,is_all_complete)
                VALUES(?,1,?,'{}','{}',?,0,-50,-50,'scored','[]',?,?,?,?,0,0)""", (f"settlement-{version}", date, score, version, updated, updated, updated))
        for version in ("sleep-score-v1", "sleep-score-v2"):
            conn.execute("""INSERT INTO server_reward_ledger
                (id,user_id,amount,source_type,source_id,description,target_date,created_at,updated_at)
                VALUES(?,1,-50,'sleep_cycle_penalty',?,'睡眠周期不足（<4.0）',?,?,?)""", (f"sleep-cycle-penalty:1:{date}:{version}", f"sleep-score:{date}:{version}:cycle-penalty", date, stamp, stamp))

    first = RewardCandidateBuilder(store).build(1, date)
    with store._connect() as conn:
        first_rows = [tuple(row) for row in conn.execute("SELECT id,amount,source_type FROM server_reward_ledger ORDER BY id")]
        first_wallet = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()["balance"]
    second = RewardCandidateBuilder(store).build(1, date)
    with store._connect() as conn:
        second_rows = [tuple(row) for row in conn.execute("SELECT id,amount,source_type FROM server_reward_ledger ORDER BY id")]
        second_wallet = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=1").fetchone()["balance"]

    assert first_rows == second_rows == [
        (f"sleep-completion-reward:1:{date}:sleep-score-v2", 0.0, "sleep_completion_reward"),
        (f"sleep-cycle-penalty:1:{date}:sleep-score-v2", -50.0, "sleep_cycle_penalty"),
        (f"sleep-reward:1:{date}:sleep-score-v2", 0.0, "sleep_settlement_reward"),
    ]
    assert first["balance"] == second["balance"] == first_wallet == second_wallet == -50.0


def test_candidate_rebuild_keeps_independent_diary_rewards_without_scored_metrics(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    date = "2026-09-06"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'diary-rebuild','p',?)", (date,))
    store.save_huawei_sleep_data(1, date, {"morning_diary": "晨记", "evening_diary": "晚记"})

    first = RewardCandidateBuilder(store).build(1, date)
    second = RewardCandidateBuilder(store).build(1, date)
    with store._connect() as conn:
        rows = conn.execute("SELECT id,source_type,amount FROM server_reward_ledger WHERE user_id=1").fetchall()
        settlement = conn.execute("SELECT morning_diary_reward_status,evening_diary_reward_status FROM server_sleep_score_settlements WHERE user_id=1").fetchone()
    assert sorted(tuple(row) for row in rows) == [
        (f"sleep-evening-diary-reward:1:{date}:v1", "sleep_evening_diary_reward", 10.0),
        (f"sleep-morning-diary-reward:1:{date}:v1", "sleep_morning_diary_reward", 10.0),
    ]
    assert tuple(settlement) == ("completed", "completed")
    assert first["balance"] == second["balance"] == 20.0


def test_candidate_refuses_uncovered_ledger_source_before_clearing(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','p','2026-08-25')")
        conn.execute("""INSERT INTO server_reward_ledger
            (id,user_id,amount,source_type,description,target_date,created_at,updated_at)
            VALUES('unknown',1,1,'unknown_source','未知','2026-08-25','2026-08-25','2026-08-25')""")

    try:
        RewardCandidateBuilder(store).build(1, "2026-08-17")
    except ValueError as error:
        assert str(error) == "unsupported_ledger_sources:unknown_source"
    else:
        raise AssertionError("uncovered source must reject candidate rebuild")

    with store._connect() as conn:
        assert conn.execute("SELECT id FROM server_reward_ledger").fetchone()[0] == "unknown"


def test_candidate_does_not_retroactively_create_body_metric_penalty(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    stamp = "2026-08-25 12:00:00"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','p',?)", (stamp,))
        conn.execute("INSERT INTO server_exercise_daily_logs(id,user_id,date,plan_version,exercise_type,day_name,created_at,updated_at) VALUES('log',1,'2026-08-25','v1','daily','一',?,?)", (stamp, stamp))
        conn.execute("INSERT INTO server_exercise_checkins(id,user_id,log_id,plan_version,item_key,status,date,locked_at,created_at,updated_at) VALUES('old-lock',1,'log','v1','sc-2026-08-25-0',-1,'2026-08-25',?,?,?)", (stamp, stamp, stamp))

    RewardCandidateBuilder(store).build(1, "2026-08-17")

    with store._connect() as conn:
        assert conn.execute("SELECT 1 FROM server_reward_ledger WHERE source_type='body_metric_deadline_penalty'").fetchone() is None


def test_candidate_backfills_historical_body_metric_penalty_from_date_bound_plan(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    stamp = "2026-09-02 12:00:00"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','p',?)", (stamp,))
        conn.execute("INSERT INTO server_exercise_daily_logs(id,user_id,date,plan_version,exercise_type,day_name,created_at,updated_at) VALUES('log',1,'2026-09-01','v1','daily','一',?,?)", (stamp, stamp))
        conn.execute("INSERT INTO server_exercise_plan_schedule_items(id,user_id,plan_version,schedule_type,sort_order,time,item,created_at,updated_at) VALUES('weight',1,'v1','weekday',0,'07:30','起床后空腹称体重、体脂并记录',?,?)", (stamp, stamp))
    RewardCandidateBuilder(store).build(1, "2026-09-01")
    RewardCandidateBuilder(store).build(1, "2026-09-01")
    with store._connect() as conn:
        lock = conn.execute("SELECT status,deadline_penalty_amount FROM server_exercise_checkins WHERE date='2026-09-01'").fetchone()
        rows = conn.execute("SELECT amount FROM server_reward_ledger WHERE source_type='body_metric_deadline_penalty'").fetchall()
    assert tuple(lock) == (-1, -50.0)
    assert [row[0] for row in rows] == [-50.0]


def test_candidate_replays_learning_and_claimed_external_reward_without_erasing_queue(tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    stamp = "2026-08-25 12:00:00"
    with store._transact() as conn:
        conn.execute("INSERT INTO users(id,username,password_hash,created_at) VALUES(1,'u','p',?)", (stamp,))
        conn.execute("INSERT INTO server_learning_objectives(id,user_id,title,status,created_at,updated_at) VALUES('objective',1,'目标',0,?,?)", (stamp, stamp))
        conn.execute("INSERT INTO server_learning_krs(id,user_id,objective_id,title,created_at,updated_at) VALUES('kr',1,'objective','KR',?,?)", (stamp, stamp))
        conn.execute("INSERT INTO server_learning_tasks(id,user_id,kr_id,title,status,created_at,updated_at) VALUES('learn',1,'kr','学习',2,?,?)", (stamp, stamp))
        conn.execute("INSERT INTO server_reward_config(user_id,item_type,item_id,coins,penalty,updated_at) VALUES(1,'learning','learn',3,0,?)", (stamp,))
        conn.execute("INSERT INTO server_external_rewards(id,ext_id,user_id,item_type,item_name,coins,status,created_at,updated_at) VALUES('external','ext',1,'other','外部奖励',2,1,?,?)", (stamp, stamp))
        conn.execute("INSERT INTO server_reward_ledger(id,user_id,amount,source_type,source_id,description,target_date,created_at,updated_at) VALUES('old-learn',1,3,'learning_checkin','learn','学习','2026-08-25',?,?)", (stamp, stamp))
        conn.execute("INSERT INTO server_reward_ledger(id,user_id,amount,source_type,source_id,description,target_date,created_at,updated_at) VALUES('old-ext',1,2,'external_claim','ext','外部奖励','2026-08-25',?,?)", (stamp, stamp))

    RewardCandidateBuilder(store).build(1, "2026-08-17")

    with store._connect() as conn:
        sources = conn.execute("SELECT source_type,amount FROM server_reward_ledger ORDER BY source_type").fetchall()
        assert [(row[0], row[1]) for row in sources] == [("external_claim", 2.0), ("learning_checkin", 3.0)]
        assert conn.execute("SELECT status FROM server_external_rewards WHERE ext_id='ext'").fetchone()[0] == 1
