import pytest
from server.domain.morning_motivation import validate_message, validate_week


def test_morning_message_rejects_shaming_claims_and_bad_format():
    assert validate_message("今天先完成一件小事，让这一天从行动开始。")
    for message in ("你昨天又偷懒了，今天必须补回来。", "你已经连续坚持七天了，继续加油！", "加油", "Visit https://example.com"):
        with pytest.raises(ValueError):
            validate_message(message)


def test_morning_week_requires_seven_distinct_lines():
    with pytest.raises(ValueError, match="duplicate"):
        validate_week(["今天先完成一件小事，让这一天从行动开始。"] * 7)
