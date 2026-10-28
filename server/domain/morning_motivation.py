"""07:30 激励文案的版本化提示词和保守校验。"""
from __future__ import annotations

import re

PROMPT_VERSION = "morning-motivation-v1"
SYSTEM_PROMPT = (
    "你为自我管理应用写每天早上7:30的一句话鼓励。只返回 JSON 对象，格式为 "
    '{"messages":["短句1",...,"短句7"]}。每句12到48个汉字或常用中文标点，'
    "温暖、具体、各不重复；鼓励今天可做的小行动。不要责备、羞辱、命令、承诺结果、"
    "声称知道用户昨天或过去的表现、身体状态、身份或私人经历。不要医疗建议、网址、营销或表情符号。"
)
BLOCKED = ("废物", "懒惰", "失败者", "没用", "必须", "保证", "一定成功", "你昨天", "你已经", "你上次", "你之前", "你的体重", "你的病", "自杀", "伤害自己")


def validate_message(raw: object) -> str:
    if not isinstance(raw, str):
        raise ValueError("morning_message_not_text")
    message = raw.strip()
    if not 12 <= len(message) <= 48 or not re.search(r"[\u4e00-\u9fff]", message):
        raise ValueError("morning_message_length_or_language")
    if any(token in message for token in BLOCKED) or re.search(r"https?://|[A-Za-z0-9_]{12,}|\d{6,}", message):
        raise ValueError("morning_message_unsafe")
    return message


def validate_week(raw: object) -> list[str]:
    if not isinstance(raw, list) or len(raw) != 7:
        raise ValueError("morning_week_size")
    messages = [validate_message(item) for item in raw]
    if len(set(messages)) != 7:
        raise ValueError("morning_week_duplicate")
    return messages
