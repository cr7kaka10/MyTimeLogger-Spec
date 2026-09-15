import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

from server.analyzer import SleepAnalyzer
from server.server import _model_candidates


MODULE_PATH = Path(__file__).resolve().parents[2] / "server" / "skills" / "time-management" / "generate_full_report.py"
spec = importlib.util.spec_from_file_location("generate_full_report_config_resolution_test", MODULE_PATH)
report_module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(report_module)


def test_vision_candidates_use_primary_then_explicit_backups_and_legacy_compatibility():
    cfg = {"vision_base_url": "main-url", "vision_api_key": "main-key", "vision_model": "main", "backup_base_url": "legacy-url", "backup_api_key": "legacy-key", "backup_model": "legacy", "vision_backup_2_base_url": "backup2-url", "vision_backup_2_api_key": "backup2-key", "vision_backup_2_model": "backup2"}
    assert [(item["slot"], item["model"]) for item in _model_candidates(cfg, "vision")] == [("主模型", "main"), ("备用模型 1", "legacy"), ("备用模型 2", "backup2")]


def _stub_report_pipeline(monkeypatch):
    monkeypatch.setattr(report_module, "combine_data", lambda *args, **kwargs: {"sleep": {}, "summary": {}, "atimelogger": {}})
    monkeypatch.setattr(report_module, "_build_exercise_summary", lambda *args, **kwargs: {})
    monkeypatch.setattr(report_module, "perform_deep_analysis", lambda *args, **kwargs: {})
    monkeypatch.setattr(report_module, "generate_full_report_file", lambda *args, **kwargs: "safe-report.md")


def test_report_generation_does_not_require_legacy_skill_config(tmp_path, monkeypatch):
    monkeypatch.setattr(report_module, "SKILL_DIR", str(tmp_path / "missing-skill-config"))
    _stub_report_pipeline(monkeypatch)

    report_path = report_module.generate_comprehensive_report(
        "2026-07-19",
        include_time_analysis=False,
    )

    assert report_path == "safe-report.md"


def test_report_uses_passed_user_provider_config_before_legacy_file(tmp_path, monkeypatch):
    captured = {}
    skill_dir = tmp_path / "legacy-skill-config"
    skill_dir.mkdir()
    (skill_dir / "config.json").write_text(json.dumps({
        "atimelogger": {"base_url": "https://legacy.invalid", "region": "legacy-only"},
    }), encoding="utf-8")
    monkeypatch.setattr(report_module, "SKILL_DIR", str(skill_dir))
    _stub_report_pipeline(monkeypatch)

    class FakeExtractor:
        def __init__(self, config):
            captured["atimelogger"] = config

        def extract_daily_data(self, _date):
            return {"activities": []}

    class FakeParser:
        def calculate_sleep_transition_times(self, _sleep_data, _activities):
            return 0, 0, "", ""

    def fake_analysis(_data, ai_config=None):
        captured["ai_model"] = ai_config
        return {}

    monkeypatch.setattr(report_module, "AtimeloggerExtractor", FakeExtractor)
    monkeypatch.setattr(report_module, "ScreenshotParser", FakeParser)
    monkeypatch.setattr(report_module, "perform_deep_analysis", fake_analysis)

    provider_config = {
        "ai_model_config": {"text_model": "test-model"},
        "atimelogger": {"base_url": "https://example.invalid"},
    }
    report_module.generate_comprehensive_report(
        "2026-07-19",
        injected_sleep_data={"date": "2026-07-19", "total_sleep_min": 420},
        include_time_analysis=False,
        provider_config=provider_config,
    )

    assert captured["atimelogger"] == {
        "base_url": "https://example.invalid",
        "region": "legacy-only",
    }
    assert captured["ai_model"] == provider_config["ai_model_config"]


def test_sleep_analyzer_passes_user_provider_config_to_report_entry(tmp_path, monkeypatch):
    captured = {}
    report_path = tmp_path / "safe-report.md"
    report_path.write_text("safe", encoding="utf-8")

    def generate_report(*_args, provider_config=None, **_kwargs):
        captured["provider_config"] = provider_config
        return str(report_path)

    fake_report_module = types.ModuleType("generate_full_report")
    fake_report_module.generate_comprehensive_report = generate_report
    monkeypatch.setitem(sys.modules, "generate_full_report", fake_report_module)

    provider_config = {
        "ai_model_config": {"text_model": "test-model"},
        "atimelogger": {"base_url": "https://example.invalid"},
    }
    analyzer = SleepAnalyzer(
        ai_cfg=provider_config["ai_model_config"],
        sleep_data={
            "sleep_date": "2026-07-19",
            "sleep_score": 80,
            "deep_sleep_min": 100,
            "light_sleep_min": 250,
            "rem_sleep_min": 70,
            "deep_sleep_ratio": 25,
            "sleep_start": "00:00",
            "sleep_end": "07:00",
            "total_sleep_min": 420,
            "official_advice": "测试建议",
        },
        date_str="2026-07-19",
        report_provider_config=provider_config,
    )

    result = analyzer.analyze()

    assert result.status == "done"
    assert captured["provider_config"] == provider_config


def test_report_exposes_safe_atimelogger_reauthorization_reason(monkeypatch):
    class FakeExtractor:
        failure_reason = "aTimeLogger 授权已失效，请在设置中重新保存账号密码后重试。"

        def __init__(self, _config):
            pass

        def extract_daily_data(self, _date):
            return None

    class FakeDb:
        def get_atm_data(self, _date):
            return None

        def save_atm_data(self, _date, _data):
            return True

    monkeypatch.setattr(report_module, "AtimeloggerExtractor", FakeExtractor)

    with pytest.raises(RuntimeError) as error:
        report_module.generate_comprehensive_report(
            "2026-07-18",
            injected_sleep_data={"date": "2026-07-18", "total_sleep_min": 420},
            include_time_analysis=True,
            db=FakeDb(),
        )

    assert str(error.value) == FakeExtractor.failure_reason


def test_report_keeps_empty_activity_error_after_successful_auth(monkeypatch):
    class FakeExtractor:
        failure_reason = None

        def __init__(self, _config):
            pass

        def extract_daily_data(self, _date):
            return {"activities": []}

    class FakeDb:
        def get_atm_data(self, _date):
            return None

        def save_atm_data(self, _date, _data):
            return True

    monkeypatch.setattr(report_module, "AtimeloggerExtractor", FakeExtractor)

    with pytest.raises(RuntimeError) as error:
        report_module.generate_comprehensive_report(
            "2026-07-18",
            injected_sleep_data={"date": "2026-07-18", "total_sleep_min": 420},
            include_time_analysis=True,
            db=FakeDb(),
        )

    assert "当日记录为空" in str(error.value)
