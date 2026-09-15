"""Versioned constraints shared by runtime management planning clients."""
from __future__ import annotations

from pathlib import Path

POLICY_VERSION = "management-planning-v3"
SKILL_VERSION = "management-planning-skill-v2"
SKILL_PATH = Path(__file__).resolve().parents[1] / "skills" / "management-planning" / "SKILL.md"
REVIEW_KEYWORDS = ("总结", "盘点", "分析当前", "评估当前", "复盘当前")
VALID_INTENTS = {"review", "proposal"}


def determine_intent(request_text: str, requested_intent: str | None = None) -> str:
    requested = str(requested_intent or "").strip().lower()
    if requested in VALID_INTENTS:
        return requested
    text = str(request_text or "").strip()
    return "review" if any(keyword in text[:80] for keyword in REVIEW_KEYWORDS) else "proposal"


def skill_prompt() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def system_policy_prompt(intent: str) -> str:
    language_rule = (
        "所有面向用户的自然语言字段（title、summary、reason、description、name 以及 review 三组数组）必须使用简体中文；"
        "必要的英文品牌或技术名词只能出现在中文句子中。logical_key、枚举、ID、时间和数值不受语言要求影响。"
    )
    if intent == "review":
        return (
            f"本次固定为 review 模式，policy_version 为 {POLICY_VERSION}，skill_version 为 {SKILL_VERSION}。"
            "只总结当前管理方案，不创建或修改任何项目。"
            "先核对 review_evidence，再分析；不得编造金币、商品、价格、解锁条件或来源。"
            "返回 review:{strengths:string[],risks:string[],recommendations:string[]} 和 items:[]。"
            + language_rule
            + skill_prompt()
        )
    return (
        f"本次固定为 proposal 模式，policy_version 为 {POLICY_VERSION}，skill_version 为 {SKILL_VERSION}。"
        "必须返回至少一个可执行 items 项；优先调整已有方案，避免重复创建。"
        "睡眠、恢复和现有目标是约束，不承诺自动处罚、扣币、消费或完成结算。"
        "奖励只能是可审阅的建议，必须服从已提供的商品价格与金币边界。"
        "logical_key 只能使用 ASCII；不确定时使用 task.item-1、habit.item-1、goal.item-1 等英文键。"
        "睡眠仅作为约束或 goal 项目，不得使用 sleep 作为 items.type。"
        + language_rule
        + skill_prompt()
    )
