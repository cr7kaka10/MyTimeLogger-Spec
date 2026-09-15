# -*- coding: utf-8 -*-
import importlib.util
import logging
import os
import sqlite3


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _load_screenshot_parser_module():
    module_path = os.path.join(
        ROOT_DIR,
        "server",
        "skills",
        "time-management",
        "modules",
        "screenshot_parser.py",
    )
    spec = importlib.util.spec_from_file_location("screenshot_parser_test_module", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_full_report_module():
    module_path = os.path.join(
        ROOT_DIR,
        "server",
        "skills",
        "time-management",
        "generate_full_report.py",
    )
    spec = importlib.util.spec_from_file_location("generate_full_report_transition_test_module", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sleep_transition_keeps_long_cross_day_fall_asleep_duration(caplog):
    module = _load_screenshot_parser_module()
    parser = module.ScreenshotParser()
    sleep_data = {
        "date": "2026-07-05",
        "sleep_start": "02:58",
        "sleep_end": "06:58",
    }
    activities = [
        {
            "type": "睡觉",
            "start": "2026-07-04T23:30:00+08:00",
            "finish": "2026-07-05T07:20:00+08:00",
        }
    ]

    with caplog.at_level(logging.INFO):
        fall_asleep_min, wake_up_min, atm_start, atm_end = parser.calculate_sleep_transition_times(sleep_data, activities)

    assert fall_asleep_min == 208
    assert wake_up_min == 22
    assert atm_start == "23:30"
    assert atm_end == "07:20"
    assert any("[sleep-report] transition final" in record.message for record in caplog.records)
    assert "no_range_filter" in "\n".join(sleep_data["calc_trace"])


def test_full_report_duration_threshold_uses_seconds():
    report_module = _load_full_report_module()

    assert report_module.tracked_duration_seconds({"activities": [{"duration": 20 * 60 * 60 - 1}]}) < report_module.FULL_REPORT_MIN_TRACKED_SECONDS
    assert report_module.tracked_duration_seconds({"activities": [{"duration": 20 * 60 * 60}]}) == report_module.FULL_REPORT_MIN_TRACKED_SECONDS


def test_full_report_keeps_sleep_data_when_tracking_is_insufficient():
    report_module = _load_full_report_module()
    saved = {}

    class FakeDb:
        def get_atm_data(self, date_str):
            return {"activities": [{"duration": report_module.FULL_REPORT_MIN_TRACKED_SECONDS - 1}]}

        def save_huawei_sleep_data(self, date_str, data):
            saved.update(data)

    sleep_data = {"date": "2026-07-05", "report_status": 1, "analysis_report": "sleep report"}
    result = report_module.generate_comprehensive_report("2026-07-05", injected_sleep_data=sleep_data, include_time_analysis=True, db=FakeDb())

    assert result is None
    assert saved["analysis_report"] == "sleep report"
    assert saved["full_report_state"] == "insufficient_time_records"
    assert saved["tracked_duration_seconds"] == report_module.FULL_REPORT_MIN_TRACKED_SECONDS - 1


def test_generate_report_saves_transition_trace_and_derived_fields(tmp_path, monkeypatch):
    report_module = _load_full_report_module()
    report_path = tmp_path / "sleep_report.md"
    report_path.write_text("# report", encoding="utf-8")
    saved = {}

    class FakeDb:
        db_type = "sqlite"

        def get_atm_data(self, date_str):
            return {
                "activities": [{
                    "type": "睡觉",
                    "start": "2026-07-04T23:30:00+08:00",
                    "finish": "2026-07-05T07:20:00+08:00",
                }]
            }

        def save_atm_data(self, date_str, data):
            return True

        def get_huawei_sleep_data(self, date_str):
            return None

        def _get_connection(self):
            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            conn.execute(
                "CREATE TABLE huawei_sleep_data (date TEXT, sleep_score INTEGER, total_sleep_min INTEGER, sleep_cycles REAL, fall_asleep_min INTEGER, wake_up_min INTEGER, deep_sleep_ratio INTEGER, awake_count INTEGER)"
            )
            return conn

        def save_huawei_sleep_data(self, date_str, data):
            saved["date"] = date_str
            saved["data"] = dict(data)
            return True

    monkeypatch.setattr(report_module, "perform_deep_analysis", lambda data, ai_config=None: {"insights": [], "issues": [], "recommendations": []})
    monkeypatch.setattr(report_module, "generate_full_report_file", lambda *args, **kwargs: str(report_path))

    report_module.generate_comprehensive_report(
        "2026-07-05",
        injected_sleep_data={
            "date": "2026-07-05",
            "sleep_score": 80,
            "total_sleep_min": 240,
            "deep_sleep_min": 90,
            "light_sleep_min": 120,
            "rem_sleep_min": 30,
            "sleep_start": "02:58",
            "sleep_end": "06:58",
            "official_advice": "睡眠质量有待改善。建议保持规律作息。",
        },
        force_pull=False,
        include_time_analysis=False,
        db=FakeDb(),
    )

    assert saved["date"] == "2026-07-05"
    assert saved["data"]["fall_asleep_min"] == 208
    assert saved["data"]["wake_up_min"] == 22
    assert saved["data"]["atm_sleep_start"] == "23:30"
    assert saved["data"]["atm_sleep_end"] == "07:20"
    assert any("no_range_filter" in item for item in saved["data"]["calc_trace"])
