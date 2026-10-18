import json

import pytest

from server.analyzer import SleepAnalyzer, build_vision_candidates, classify_provider_error


def _cfg():
    return {
        "vision_base_url": "https://main.invalid", "vision_api_key": "main-secret", "vision_model": "main",
        "vision_backup_1_base_url": "https://backup.invalid", "vision_backup_1_api_key": "backup-secret", "vision_backup_1_model": "backup",
    }


def _data(light=210):
    return {"sleep_date": "2026-10-03", "sleep_score": 79, "total_sleep_min": 330,
            "deep_sleep_min": 60, "light_sleep_min": light, "rem_sleep_min": 60,
            "deep_sleep_ratio": 18, "sleep_start": "02:12", "sleep_end": "08:23",
            "official_advice": "睡眠时长不足，长期睡眠不足容易导致白天疲劳，建议保持规律作息。"}


def _analyzer(tmp_path):
    image = tmp_path / "sleep_2026-10-03.jpg"
    image.write_bytes(b"image")
    return SleepAnalyzer(_cfg(), image_path=str(image), date_str="2026-10-03")


def test_candidate_builder_skips_incomplete_slots_and_prefers_explicit_backup():
    cfg = _cfg() | {"vision_backup_2_base_url": "url", "vision_backup_2_model": "missing-key",
                    "backup_base_url": "legacy", "backup_api_key": "legacy-key", "backup_model": "legacy"}
    assert build_vision_candidates(cfg) == [("主模型", "vision"), ("备用模型 1", "vision_backup_1")]


def test_math_mismatch_rereads_only_durations_then_stops(tmp_path, monkeypatch):
    analyzer = _analyzer(tmp_path)
    responses, calls = [_data(193), {"total_sleep_min": 330, "deep_sleep_min": 60,
                                   "light_sleep_min": 210, "rem_sleep_min": 60}], []

    def fake_request(prefix, prompt, *_args):
        calls.append((prefix, prompt))
        return responses.pop(0)

    monkeypatch.setattr(analyzer, "_request_vision_json", fake_request)
    result = analyzer._extract_sleep_data()

    assert [call[0] for call in calls] == ["vision", "vision"]
    assert "只重新读取" in calls[1][1] and result["light_sleep_min"] == 210
    assert result["official_advice"].startswith("睡眠时长不足")


def test_bad_20261003_sample_falls_back_and_audit_is_redacted(tmp_path, monkeypatch):
    analyzer = _analyzer(tmp_path)
    responses = [_data(193), {"total_sleep_min": 330, "deep_sleep_min": 60,
                              "light_sleep_min": 193, "rem_sleep_min": 60}, _data(210)]
    monkeypatch.setattr(analyzer, "_request_vision_json", lambda *_: responses.pop(0))

    result = analyzer._extract_sleep_data()
    audit = json.dumps(result["ocr_audit"], ensure_ascii=False)

    assert result["extracted_by"] == "backup"
    assert len(result["ocr_audit"]) == 3
    assert "secret" not in audit and "base64" not in audit


def test_all_invalid_candidates_raise_aggregate_error(tmp_path, monkeypatch):
    analyzer = _analyzer(tmp_path)
    responses = [{"sleep_date": "2026-10-03"}, {"sleep_date": "2026-10-03"}]
    monkeypatch.setattr(analyzer, "_request_vision_json", lambda *_: responses.pop(0))

    with pytest.raises(RuntimeError, match="睡眠OCR全部候选失败") as error:
        analyzer._extract_sleep_data()

    assert "main-secret" not in str(error.value) and "backup-secret" not in str(error.value)


class ProviderFailure(Exception):
    def __init__(self, status, code, message="provider secret response"):
        super().__init__(message)
        self.status_code = status
        self.body = {"code": code, "message": message}


@pytest.mark.parametrize("status,code,category", [
    (402, 30001, "insufficient_balance"), (401, 0, "authentication"),
    (403, 0, "authentication"), (429, 0, "rate_limited"), (404, "model_not_found", "model_unavailable"),
])
def test_provider_error_classification_is_actionable_and_redacted(status, code, category):
    result = classify_provider_error(ProviderFailure(status, code))
    assert result["category"] == category and result["http_status"] == status
    assert "secret" not in json.dumps(result, ensure_ascii=False)


def test_shared_balance_failure_skips_same_credential_but_tries_independent_provider(tmp_path, monkeypatch):
    cfg = _cfg() | {
        "vision_backup_1_base_url": "https://main.invalid", "vision_backup_1_api_key": "main-secret",
        "vision_backup_2_base_url": "https://independent.invalid", "vision_backup_2_api_key": "other-secret", "vision_backup_2_model": "other",
    }
    analyzer = _analyzer(tmp_path)
    analyzer.ai_cfg = cfg
    calls = []
    def fake_request(prefix, *_args):
        calls.append(prefix)
        if prefix == "vision": raise ProviderFailure(402, 30001)
        return _data(210)
    monkeypatch.setattr(analyzer, "_request_vision_json", fake_request)
    result = analyzer._extract_sleep_data()
    assert calls == ["vision", "vision_backup_2"] and result["extracted_by"] == "other"
    assert analyzer.ocr_audit[1]["outcome"] == "skipped_shared_failure"
