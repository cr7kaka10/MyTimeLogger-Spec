# -*- coding: utf-8 -*-
"""金币重建的安全诊断、中文错误报告与结构化日志。"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

BEIJING = timezone(timedelta(hours=8))
MAX_REPORT_BYTES = 64 * 1024
SENSITIVE = ("token", "password", "cookie", "authorization", "secret")
TRACE_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
WINDOWS_PATH = re.compile(r"(?i)[A-Z]:\\[^\s\"']+")

ERRORS = {
    "ticktick_pull_incomplete": ("滴答清单数据拉取不完整", "provider_pull", True, "检查分项原因后重试"),
    "candidate_wallet_mismatch": ("候选钱包余额与流水合计不一致", "candidate_validate", False, "请复制诊断信息进行排查"),
    "candidate_reference_invalid": ("候选账存在无效引用", "candidate_validate", False, "请复制诊断信息进行排查"),
    "candidate_action_coverage_incomplete": ("历史主动行为未完整回放", "candidate_validate", False, "请复制诊断信息进行排查"),
    "behavior_revision_changed": ("重建期间行为或规则发生变化", "publish", True, "请重新预览并重试"),
    "server_restarted": ("服务端重启导致重建中断", "restore", True, "旧账核对后可重新发起"),
    "preview_stale": ("预览后数据已发生变化", "job_create", True, "请重新预览"),
    "ticktick_reset_tombstone_conflict": ("清理旧清单同步事件冲突", "ticktick_reset", True, "请重新拉取并重算金币"),
    "ticktick_reset_integrity_error": ("清理旧清单时发生完整性错误", "ticktick_reset", False, "请复制诊断信息进行排查"),
}


def beijing_now() -> str:
    return datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S")


def normalize_trace_id(value: object) -> str:
    raw = str(value or "").strip()
    return raw if TRACE_PATTERN.fullmatch(raw) else uuid.uuid4().hex


def _clean_string(value: object, limit: int = 200) -> str:
    return WINDOWS_PATH.sub("[path]", str(value or ""))[:limit]


def sanitize(value: Any, depth: int = 0) -> Any:
    if depth > 5:
        return "[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _clean_string(value)
    if isinstance(value, dict):
        cleaned = {}
        for key, item in list(value.items())[:50]:
            name = str(key)
            if any(secret in name.lower() for secret in SENSITIVE):
                continue
            cleaned[name[:80]] = sanitize(item, depth + 1)
        return cleaned
    if isinstance(value, (list, tuple, set)):
        return [sanitize(item, depth + 1) for item in list(value)[:20]]
    return _clean_string(type(value).__name__)


def safe_json(value: Any, fallback: dict | None = None) -> str:
    try:
        encoded = json.dumps(sanitize(value), ensure_ascii=False, sort_keys=True)
        if len(encoded.encode("utf-8")) <= MAX_REPORT_BYTES:
            return encoded
    except Exception:
        pass
    minimum = sanitize(fallback or {"code": "diagnostic_truncated"})
    return json.dumps(minimum, ensure_ascii=False, sort_keys=True)


def pull_causes(diagnostics: dict | None) -> list[dict]:
    data = diagnostics if isinstance(diagnostics, dict) else {}
    causes: list[dict] = []
    tasks = data.get("tasks") if isinstance(data.get("tasks"), dict) else {}
    for item in tasks.get("completed_item_errors") or []:
        causes.append({"chain": "tasks", "code": item.get("code") or "task_item_failed",
                       "message_zh": "已完成任务奖励处理失败", **sanitize(item)})
    completed_error = tasks.get("completed_pull_error")
    if completed_error and not causes:
        causes.append({"chain": "tasks", "code": "completed_pull_failed",
                       "message_zh": "已完成任务拉取或处理失败", "detail": completed_error})
    habits = data.get("habits") if isinstance(data.get("habits"), dict) else {}
    if habits.get("missing_checkin_blocks"):
        causes.append({"chain": "habits", "code": "habit_checkin_blocks_omitted",
                       "message_zh": "滴答成功响应省略了部分空习惯块",
                       "expected": habits.get("habits"), "actual": habits.get("checkin_blocks"),
                       "missing": habits.get("missing_checkin_blocks"),
                       "range": habits.get("checkin_range"), "objects": habits.get("missing_checkin_habits")})
    for raw in data.get("errors") or []:
        text = _clean_string(raw)
        if not any(text == cause.get("detail") for cause in causes):
            causes.append({"chain": text.split(":", 1)[0], "code": text,
                           "message_zh": "提供方分链处理失败"})
    return sanitize(causes)[:50]


def error_cause(error: object) -> dict | None:
    details = getattr(error, "reward_rebuild_details", None)
    if not isinstance(details, dict):
        return None
    chain = _clean_string(details.get("chain") or "candidate")
    check = _clean_string(details.get("check") or f"{chain}_check_failed")
    return sanitize({
        "chain": chain, "code": check,
        "message_zh": _clean_string(details.get("message_zh") or ("候选账校验未通过" if chain == "candidate" else "重建阶段校验未通过")), **details,
    })


def failure_report(error: object, *, trace_id: str, job_id: str | None,
                   failed_stage: str | None = None, pull: dict | None = None,
                   recovery: dict | None = None) -> dict:
    code = _clean_string(error) or "unknown_error"
    message, mapped_stage, retryable, suggestion = ERRORS.get(
        code, ("未分类异常", failed_stage or "unknown", False, "请复制诊断信息进行排查"),
    )
    causes = pull_causes(pull)
    if cause := error_cause(error):
        causes.append(cause)
    return sanitize({
        "version": 1, "code": code, "message_zh": message,
        "failed_stage": failed_stage or mapped_stage, "retryable": retryable,
        "trace_id": normalize_trace_id(trace_id), "job_id": job_id,
        "occurred_at": beijing_now(), "causes": causes,
        "recovery": recovery or {"status": "not_required", "verified": True},
        "suggestions": [suggestion],
    })


def log_event(logger: logging.Logger, *, trace_id: str, job_id: str | None,
              user_id: int, stage: str, event: str, outcome: str,
              elapsed_ms: float | None = None, details: dict | None = None,
              level: int = logging.INFO) -> None:
    payload = {"trace_id": normalize_trace_id(trace_id), "job_id": job_id, "user_id": user_id,
               "stage": stage, "event": event, "outcome": outcome, "occurred_at": beijing_now(),
               "elapsed_ms": elapsed_ms, "details": details or {}}
    try:
        logger.log(level, "[RewardRebuildTrace] %s", safe_json(payload))
    except Exception:
        logger.warning("[RewardRebuildTrace] diagnostic_log_failed trace_id=%s stage=%s", trace_id, stage)
