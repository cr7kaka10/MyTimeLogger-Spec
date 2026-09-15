"""管理方案的结构校验、规范化和摘要计算。

该模块不执行任何数据库写入，确保 AI 输出和导入文件先经过确定性校验。
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any


LOGICAL_KEY_RE = re.compile(r"^[a-z][a-z0-9-]{1,80}\.[a-z0-9][a-z0-9._-]{0,120}$")
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
SUPPORTED_TYPES = {
    "existing_task_reward",
    "existing_habit_reward",
    "ticktick_task",
    "local_habit",
    "learning",
    "exercise",
    "goal",
    "reward_item",
}
PLAN_MODES = {"review", "proposal"}
PATCH_ACTIONS = {"add", "update", "disable", "keep"}
FORBIDDEN_KEYS = {
    "sql", "query", "table", "table_name", "token", "password", "api_key",
    "raw_json", "source_etag", "source_modified_time", "reward_ledger",
    "wallet", "wallet_balance", "backpack_events", "sync_queue",
    "calendar_event", "calendar_events", "hourly_schedule",
}


class ManagementPlanValidationError(ValueError):
    def __init__(self, code: str, message: str, *, path: str = ""):
        super().__init__(message)
        self.code = code
        self.path = path


_NATURAL_TEXT_KEYS = {
    "title", "summary", "reason", "description", "name",
    "strengths", "risks", "recommendations", "target_description",
}


def _check_simplified_text(value: Any, path: str) -> None:
    if isinstance(value, str) and value.strip() and not HAN_RE.search(value):
        raise ManagementPlanValidationError(
            "management_plan_non_simplified_chinese",
            "管理方案自然语言必须使用简体中文",
            path=path,
        )
    if isinstance(value, list):
        for index, item in enumerate(value):
            _check_simplified_text(item, f"{path}[{index}]")


def validate_simplified_chinese(payload: Any) -> None:
    """检查模型可见自然语言；技术字段和逻辑键由结构校验负责。"""
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_text = str(key)
            if key_text in _NATURAL_TEXT_KEYS:
                _check_simplified_text(value, key_text)
            elif isinstance(value, (dict, list)):
                validate_simplified_chinese(value)
    elif isinstance(payload, list):
        for item in payload:
            validate_simplified_chinese(item)


def _reject_forbidden(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).lower()
            if key_text in FORBIDDEN_KEYS or any(term in key_text for term in ("password", "secret", "api_key", "token")):
                raise ManagementPlanValidationError("forbidden_field", f"不允许字段: {key}", path=f"{path}.{key}".strip("."))
            _reject_forbidden(child, f"{path}.{key}".strip("."))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden(child, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ManagementPlanValidationError("invalid_number", "金额或数值必须是有限数", path=path)


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_canonical(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def digest_payload(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _validate_item(item: Any, index: int, *, patch: bool = False) -> dict:
    if not isinstance(item, dict):
        raise ManagementPlanValidationError("invalid_item", "方案项目必须是对象", path=f"items[{index}]")
    logical_key = str(item.get("logical_key") or "").strip()
    if not LOGICAL_KEY_RE.fullmatch(logical_key):
        raise ManagementPlanValidationError("invalid_logical_key", "logical_key 格式无效", path=f"items[{index}].logical_key")
    if patch:
        action = str(item.get("action") or "").strip()
        if action not in PATCH_ACTIONS:
            raise ManagementPlanValidationError("unsupported_plan_patch", "patch action 不受支持", path=f"items[{index}].action")
        result = {"logical_key": logical_key, "action": action}
        if "value" in item:
            result["value"] = item["value"]
        if "reason" in item:
            result["reason"] = str(item["reason"] or "")[:500]
        _reject_forbidden(result, f"items[{index}]")
        return result

    item_type = str(item.get("type") or "").strip()
    if item_type not in SUPPORTED_TYPES:
        raise ManagementPlanValidationError("unsupported_plan_item", "方案项目类型不受支持", path=f"items[{index}].type")
    action = str(item.get("action") or "keep").strip()
    if action not in {"create", "update", "bind", "keep", "disable"}:
        raise ManagementPlanValidationError("unsupported_plan_item", "方案动作不受支持", path=f"items[{index}].action")
    result = dict(item)
    result["logical_key"] = logical_key
    result["type"] = item_type
    result["action"] = action
    if "reward" in result:
        reward = result["reward"]
        if not isinstance(reward, dict):
            raise ManagementPlanValidationError("invalid_reward", "奖励必须是对象", path=f"items[{index}].reward")
        coins = reward.get("coins", 0)
        if not isinstance(coins, (int, float)) or isinstance(coins, bool) or not math.isfinite(float(coins)) or float(coins) < 0:
            raise ManagementPlanValidationError("invalid_reward", "金币必须是非负有限数", path=f"items[{index}].reward.coins")
        result["reward"] = dict(reward)
        result["reward"]["coins"] = float(coins) if isinstance(coins, float) else int(coins)
    _reject_forbidden(result, f"items[{index}]")
    return result


def validate_plan_payload(payload: Any, *, patch: bool = False) -> dict:
    if not isinstance(payload, dict):
        raise ManagementPlanValidationError("invalid_payload", "方案必须是对象")
    _reject_forbidden(payload)
    items = payload.get("items")
    if not isinstance(items, list):
        raise ManagementPlanValidationError("invalid_payload", "方案 items 必须是数组", path="items")
    if not patch:
        mode = str(payload.get("mode") or "proposal").strip()
        if mode not in PLAN_MODES:
            raise ManagementPlanValidationError("invalid_plan_mode", "方案模式不受支持", path="mode")
        if mode == "review":
            review = payload.get("review")
            if items:
                raise ManagementPlanValidationError("review_must_not_include_items", "总结不能包含可执行项目", path="items")
            if not isinstance(review, dict) or any(not isinstance(review.get(key), list) for key in ("strengths", "risks", "recommendations")):
                raise ManagementPlanValidationError("invalid_review", "总结必须包含现状、风险和建议", path="review")
            result = dict(payload)
            # evidence is server-owned and is never accepted from model/UI/import input.
            result["review"] = {key: review[key] for key in ("strengths", "risks", "recommendations")}
            result["mode"] = mode
            result["items"] = []
            result["schema_version"] = str(payload.get("schema_version") or "1")
            return _canonical(result)
        if not items:
            raise ManagementPlanValidationError("empty_plan_proposal", "生成方案至少需要一项可执行内容", path="items")
    validated_items = [_validate_item(item, index, patch=patch) for index, item in enumerate(items)]
    keys = [item["logical_key"] for item in validated_items]
    if len(keys) != len(set(keys)):
        raise ManagementPlanValidationError("duplicate_logical_key", "方案包含重复 logical_key", path="items")
    result = dict(payload)
    result["items"] = sorted(validated_items, key=lambda item: item["logical_key"])
    if patch:
        result["patch_version"] = str(payload.get("patch_version") or "1")
    else:
        result["mode"] = "proposal"
        result["schema_version"] = str(payload.get("schema_version") or "1")
    return _canonical(result)


def validate_manifest(manifest: Any) -> dict:
    return validate_plan_payload(manifest, patch=False)


def validate_patch(patch: Any) -> dict:
    return validate_plan_payload(patch, patch=True)
