# -*- coding: utf-8 -*-
import importlib.util
from pathlib import Path


REPORT_MODULE = Path(__file__).parents[2] / "server" / "skills" / "time-management" / "generate_full_report.py"
SPEC = importlib.util.spec_from_file_location("sleep_report", REPORT_MODULE)
sleep_report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sleep_report)


def _report_file(tmp_path):
    path = tmp_path / "sleep.md"
    path.write_text(
        "# 睡眠报告\n\n### 1.4 睡眠评分计算与金币结算\n\n> 未评分 · 0 金币\n\n"
        "### 1.5 华为健康建议\n\n建议\n",
        encoding="utf-8",
    )
    return path


def test_report_uses_low_cycle_settlement_snapshot_without_recalculation(tmp_path):
    path = _report_file(tmp_path)
    snapshot = {
        "status": "scored", "score_total": 60, "reward_amount": 10,
        "cycle_penalty": -50, "net_amount": -40,
        "is_all_complete": False, "completion_reward_amount": 0,
        "completion_reason": "存在未满分睡眠指标",
        "ledger_sources": {"reward": "sleep-score:2026-08-28:sleep-score-v1:reward",
                           "cycle_penalty": "sleep-score:2026-08-28:sleep-score-v1:cycle-penalty"},
        "dimensions": {"sleep_cycles": {"raw_value": 3.9, "matched_rule": "<4", "score": 0,
                                          "max_score": 30, "reason": "睡眠周期"}},
    }

    report = sleep_report.apply_sleep_settlement_to_report(path, snapshot)

    assert "睡眠周期 | 3.9 | <4 | 0/30" in report
    assert "睡眠评分奖励**：+10 🪙" in report
    assert "周期不足（<4.0）惩罚**：-50 🪙" in report
    assert "睡眠指标全完成奖励**：+0 🪙" in report
    assert "22:30–23:30 得满分；23:31–00:00 得部分分；其他时段未达标" in report
    assert "净金币**：-40 🪙" in report
    assert "cycle-penalty" not in report


def test_report_marks_missing_snapshot_as_not_scored(tmp_path):
    report = sleep_report.apply_sleep_settlement_to_report(
        _report_file(tmp_path), {"status": "not_scored", "missing_fields": ["awake_count"]}
    )

    assert "未评分（缺失：awake_count）" in report
    assert "总分**" not in report


def test_report_renders_completion_reward_from_snapshot_without_recalculation(tmp_path):
    snapshot = {
        "status": "scored", "score_total": 100, "reward_amount": 80, "cycle_penalty": 0, "net_amount": 180,
        "is_all_complete": True, "completion_reward_amount": 100, "dimensions": {},
        "ledger_sources": {"completion": "sleep-score:2026-08-28:sleep-score-v2:completion"},
    }
    report = sleep_report.apply_sleep_settlement_to_report(_report_file(tmp_path), snapshot)
    assert "睡眠指标全完成奖励**：+100 🪙" in report
    assert "全完成奖励流水来源" not in report


def test_report_explains_each_v4_coin_effect_and_net_penalties(tmp_path):
    effects = {
        "sleep_cycles": "-50 🪙：睡眠周期不足（<4.0）惩罚",
        "on_time_sleep": "-60 🪙：03:01–04:00 入睡，扣60金币",
        "wake_up": "影响睡眠评分奖励；本项无独立金币流水",
        "awake_count": "影响睡眠评分奖励；本项无独立金币流水",
        "deep_sleep": "+0 🪙：深睡时长达标，无惩罚",
        "report_before_nine": "影响睡眠评分奖励；本项无独立金币流水",
        "huawei_sleep_score": "影响睡眠评分奖励；本项无独立金币流水",
        "awake_duration": "影响睡眠评分奖励；本项无独立金币流水",
    }
    labels = {
        "sleep_cycles": "睡眠周期", "on_time_sleep": "未达到按时入睡", "wake_up": "起床用时",
        "awake_count": "清醒次数", "deep_sleep": "深睡时长", "report_before_nine": "9点前生成睡眠报告",
        "huawei_sleep_score": "华为睡眠评分", "awake_duration": "清醒时长",
    }
    dimensions = {
        key: {
            "raw_value": 0,
            "matched_rule": "示例规则",
            "score": 0,
            "max_score": 10,
            "reason": labels[key],
            "coin_effect": effect,
        }
        for key, effect in effects.items()
    }
    snapshot = {
        "status": "scored",
        "score_total": 18,
        "reward_amount": 0,
        "cycle_penalty": -50,
        "deep_sleep_penalty": 0,
        "bedtime_coin_amount": -60,
        "bedtime_coin_reason": "03:01–04:00 入睡，扣60金币",
        "completion_reward_amount": 0,
        "morning_diary_reward_amount": 0,
        "evening_diary_reward_amount": 0,
        "net_amount": -110,
        "is_all_complete": False,
        "dimensions": dimensions,
    }

    report = sleep_report.apply_sleep_settlement_to_report(_report_file(tmp_path), snapshot)

    assert report.count("金币说明") == 1
    for effect in effects.values():
        assert effect in report
    for label in labels.values():
        assert f"| {label} |" in report
    assert "周期不足（<4.0）惩罚**：-50 🪙" in report
    assert "入睡时间结算**：-60 🪙（03:01–04:00 入睡，扣60金币）" in report
    assert "净金币**：-110 🪙" in report
