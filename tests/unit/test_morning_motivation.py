import pytest
from server.domain.morning_motivation import validate_message, validate_week, generate_week
import json


def test_morning_message_rejects_shaming_claims_and_bad_format():
    assert validate_message("今天先完成一件小事，让这一天从行动开始。")
    for message in ("你昨天又偷懒了，今天必须补回来。", "你已经连续坚持七天了，继续加油！", "加油", "Visit https://example.com"):
        with pytest.raises(ValueError):
            validate_message(message)


def test_morning_week_requires_seven_distinct_lines():
    with pytest.raises(ValueError, match="duplicate"):
        validate_week(["今天先完成一件小事，让这一天从行动开始。"] * 7)


def test_generate_week_uses_user_config_and_isolates_failures():
    cfg = {"text_base_url": "https://example.invalid/v1", "text_api_key": "secret", "text_model": "text"}
    messages = [f"今天先做第{i}件小事，让行动带来新的节奏。" for i in range(7)]
    assert generate_week(cfg, lambda: json.dumps({"messages": messages}, ensure_ascii=False)) == messages
    with pytest.raises(ValueError, match="ai_config_required"):
        generate_week({}, lambda: "{}")
    with pytest.raises(RuntimeError, match="ai_generation_failed") as error:
        generate_week(cfg, lambda: (_ for _ in ()).throw(TimeoutError("secret")))
    assert "secret" not in str(error.value)
