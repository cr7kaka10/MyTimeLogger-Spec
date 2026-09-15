# -*- coding: utf-8 -*-
import asyncio
from pathlib import Path
from types import SimpleNamespace

import server.server as server_module
from server.analyzer import NO_MAIN_SLEEP_WARNING, SleepAnalyzer
from server.store import ServerSleepStore
from server.db_wrapper import ServerDBWrapper
from server.sync_hub import SyncHub


def _sleep_data():
    return {
        "date": "2026-08-28", "sleep_start": "23:00", "sleep_end": "07:00",
        "sleep_score": 90, "deep_sleep_min": 95, "sleep_cycles": 5.5,
        "awake_min": 10, "awake_count": 1, "fall_asleep_min": 20, "wake_up_min": 10,
    }


def _run_with_result(monkeypatch, tmp_db_path, tmp_path, result, completed_at="2026-08-28 08:59:00", full=True):
    store = ServerSleepStore(tmp_db_path)
    store.create_user("sleep_analysis_reward", "password123")
    image_path = tmp_path / "sleep.jpg"
    image_path.write_bytes(b"image")
    store.create_job("sleep-reward-job", str(image_path), user_id=1, date="2026-08-28")

    class FakeAnalyzer:
        def __init__(self, *args, **kwargs):
            pass

        def analyze(self):
            return result

    monkeypatch.setattr(server_module, "store", store)
    monkeypatch.setattr(server_module, "SleepAnalyzer", FakeAnalyzer)
    monkeypatch.setattr(server_module, "build_ai_cfg_for_user", lambda _user_id: {})
    monkeypatch.setattr(server_module, "ATTACHMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(server_module, "_cleanup_queue", lambda *args, **kwargs: None)
    monkeypatch.setattr(server_module, "_beijing_now", lambda: __import__("datetime").datetime.strptime(completed_at, "%Y-%m-%d %H:%M:%S"))
    server_module._run_analysis("sleep-reward-job", str(image_path), user_id=1, full=full)
    return store


def test_done_analysis_creates_one_server_sleep_settlement(monkeypatch, tmp_db_path, tmp_path):
    sleep_data = _sleep_data() | {"report_status": 2, "full_report_state": "generated"}
    report_path = tmp_path / "complete-report.md"
    report_path.write_text("### 1.4 睡眠评分计算与金币结算\n旧结算\n### 1.5 华为健康建议\n", encoding="utf-8")
    store = _run_with_result(monkeypatch, tmp_db_path, tmp_path, SimpleNamespace(
        status="done", date="2026-08-28", sleep_data=sleep_data,
        analysis_report="", report_path=str(report_path), error=None,
    ))

    with store._connect() as conn:
        settlement_count = conn.execute("SELECT COUNT(*) FROM server_sleep_score_settlements").fetchone()[0]
    job = store.get_job("sleep-reward-job", user_id=1)
    assert settlement_count == 1
    assert job["sleep_data"]["score_settlement"]["score_total"] == 100
    assert job["sleep_data"]["score_settlement"]["report_completed_at"] == "2026-08-28 08:59:00"
    rendered = report_path.read_text(encoding="utf-8")
    assert "**报告时效**：2026-08-28 08:59:00" in rendered
    assert "**按时入睡标准**" in rendered
    assert [rendered.index(label) for label in ["9点前生成睡眠报告", "按时入睡", "起床规律", "华为睡眠评分", "深睡时长", "睡眠周期", "清醒时长", "清醒次数", "入睡用时", "起床用时"]] == sorted(rendered.index(label) for label in ["9点前生成睡眠报告", "按时入睡", "起床规律", "华为睡眠评分", "深睡时长", "睡眠周期", "清醒时长", "清醒次数", "入睡用时", "起床用时"])


def test_final_full_report_is_the_synced_markdown_and_html(monkeypatch, tmp_db_path, tmp_path):
    report_path = tmp_path / "complete-report.md"
    report_path.write_text(
        "### 1.4 睡眠评分计算与金币结算\n旧结算\n### 1.5 华为健康建议\n"
        "## ⏱️ [Part 2: 时间管理报告]\n### 2.1 时间分配\n完整时间分析\n",
        encoding="utf-8",
    )
    data = _sleep_data() | {
        "report_status": 2, "full_report_state": "generated",
        "analysis_html": "<h3>1.5 华为健康建议</h3>",
    }
    store = _run_with_result(monkeypatch, tmp_db_path, tmp_path, SimpleNamespace(
        status="done", date="2026-08-28", sleep_data=data,
        analysis_report=report_path.read_text(encoding="utf-8"), report_path=str(report_path), error=None,
    ))
    final_report = report_path.read_text(encoding="utf-8")
    synced = store.get_huawei_sleep_data(1, "2026-08-28")
    assert store.get_job("sleep-reward-job", user_id=1)["analysis_report"] == final_report
    assert synced["analysis_report"] == final_report
    assert "Part 2" in synced["analysis_html"] and "旧结算" not in synced["analysis_html"]
    with store._connect() as conn:
        versions = [row[0] for row in conn.execute(
            "SELECT server_version FROM server_change_log WHERE user_id=1 AND table_name='huawei_sleep_data' ORDER BY server_version"
        )]
    assert len(versions) >= 2, "最终报告必须产生独立于初稿的新同步版本"
    db = ServerDBWrapper()
    db.log_path = tmp_db_path
    core_pull = asyncio.run(SyncHub(db).handle_pull_by_version(versions[-2], user_id=1))
    assert core_pull["to_version"] >= versions[-1]
    assert core_pull["tables"]["huawei_sleep_data"][0]["analysis_report"] == final_report
    assert "Part 2" in core_pull["tables"]["huawei_sleep_data"][0]["analysis_html"]


def test_late_full_report_does_not_receive_report_timeliness_points(monkeypatch, tmp_db_path, tmp_path):
    sleep_data = _sleep_data() | {"report_status": 2, "full_report_state": "generated"}
    store = _run_with_result(monkeypatch, tmp_db_path, tmp_path, SimpleNamespace(
        status="done", date="2026-08-28", sleep_data=sleep_data,
        analysis_report="", report_path="", error=None,
    ), completed_at="2026-08-28 09:00:01")
    settlement = store.get_job("sleep-reward-job", user_id=1)["sleep_data"]["score_settlement"]
    assert settlement["dimensions"]["report_before_nine"]["score"] == 0
    assert settlement["score_total"] == 95


def test_ordinary_sleep_report_before_nine_receives_report_timeliness_points(monkeypatch, tmp_db_path, tmp_path):
    store = _run_with_result(monkeypatch, tmp_db_path, tmp_path, SimpleNamespace(
        status="done", date="2026-08-28", sleep_data=_sleep_data(),
        analysis_report="# 普通睡眠报告", report_path="", error=None,
    ), full=False)
    settlement = store.get_job("sleep-reward-job", user_id=1)["sleep_data"]["score_settlement"]
    assert settlement["report_completed_at"] == "2026-08-28 08:59:00"
    assert settlement["dimensions"]["report_before_nine"]["score"] == 5


def test_missing_full_report_does_not_use_client_sync_time(monkeypatch, tmp_db_path, tmp_path):
    store = _run_with_result(monkeypatch, tmp_db_path, tmp_path, SimpleNamespace(
        status="done", date="2026-08-28", sleep_data=_sleep_data(),
        analysis_report="", report_path="", error=None,
    ))
    settlement = store.get_job("sleep-reward-job", user_id=1)["sleep_data"]["score_settlement"]
    assert settlement["dimensions"]["report_before_nine"]["score"] == 0


def test_error_analysis_does_not_create_sleep_settlement(monkeypatch, tmp_db_path, tmp_path):
    notifications = []
    monkeypatch.setattr(server_module.sync_hub, "_notify_clients", lambda *args: notifications.append(args))
    store = _run_with_result(monkeypatch, tmp_db_path, tmp_path, SimpleNamespace(
        status="error", date="", sleep_data={}, analysis_report="", report_path="", error="analysis failed",
    ))

    with store._connect() as conn:
        settlement_count = conn.execute("SELECT COUNT(*) FROM server_sleep_score_settlements").fetchone()[0]
    assert settlement_count == 0
    assert notifications == []


def test_report_commit_broadcasts_sleep_and_coin_versions(monkeypatch, tmp_db_path, tmp_path):
    notifications = []
    monkeypatch.setattr(server_module.sync_hub, "_notify_clients", lambda tables, user_id: notifications.append((tables, user_id)))
    store = _run_with_result(monkeypatch, tmp_db_path, tmp_path, SimpleNamespace(
        status="done", date="2026-08-28", sleep_data=_sleep_data(),
        analysis_report="# 普通睡眠报告", report_path="", error=None,
    ), full=False)
    with store._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM server_huawei_sleep_data WHERE user_id=1").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM server_sleep_score_settlements WHERE user_id=1").fetchone()[0] == 1
    assert notifications == [(["huawei_sleep_data", "sleep_score_settlements", "reward_ledger", "user_wallets"], 1)]


def test_skill_reserves_fixed_sleep_settlement_block_for_server_renderer():
    skill = (Path(__file__).parents[2] / "server" / "skills" / "time-management" / "SKILL.md").read_text(encoding="utf-8")
    assert "固定睡眠结算区（代码拥有）" in skill
    assert "不得生成、改写、省略或重排" in skill
    assert "服务端会以 `sleep-score-v2` 结算快照确定性替换这一区块" in skill


def test_no_main_sleep_sentinel_short_circuits_report_pipeline():
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("no_main_sleep 不得进入缓存报告或文本报告流程")

    analyzer = SleepAnalyzer(
        {}, date_str="2026-09-12",
        sleep_data={"sleep_date": "2026-09-12", "record_state": "no_main_sleep"},
        pre_report_callback=fail_if_called,
    )
    result = analyzer.analyze()

    assert result.status == "done"
    assert result.analysis_report == NO_MAIN_SLEEP_WARNING
    assert result.sleep_data["full_report_state"] == "no_main_sleep"
    assert result.sleep_data["sleep_start"] is None
    assert result.sleep_data["sleep_end"] is None
    assert all(result.sleep_data[key] == 0 for key in (
        "sleep_score", "total_sleep_min", "deep_sleep_min", "light_sleep_min",
        "rem_sleep_min", "sleep_cycles", "fall_asleep_min", "wake_up_min",
    ))


def test_no_main_sleep_requires_explicit_state_and_keeps_short_main_sleep_normal():
    cropped = {"sleep_date": "2026-09-12", "sleep_score": 0}
    assert SleepAnalyzer.validate_data(cropped)[0] is False
    assert SleepAnalyzer.is_no_main_sleep(cropped) is False

    short_main_sleep = {
        "sleep_date": "2026-09-12", "record_state": "normal",
        "sleep_score": 40, "deep_sleep_min": 10, "light_sleep_min": 40,
        "rem_sleep_min": 10, "deep_sleep_ratio": 17, "sleep_start": "05:00",
        "sleep_end": "06:00", "total_sleep_min": 60,
        "official_advice": "睡眠时长严重不足。建议今晚提前入睡。",
    }
    assert SleepAnalyzer.validate_data(short_main_sleep)[0] is True
    assert SleepAnalyzer.is_no_main_sleep(short_main_sleep) is False
