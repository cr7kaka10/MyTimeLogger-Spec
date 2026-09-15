#!/usr/bin/env python3
"""
生成完整的时间管理分析报告 (V4.2)
优化：支持仅生成睡眠报告模式。
"""

import sys
import os
import json
from datetime import datetime, timedelta
from collections import defaultdict
import logging
import httpx
from openai import OpenAI
try:
    import markdown
except Exception:
    markdown = None

logger = logging.getLogger(__name__)
FULL_REPORT_MIN_TRACKED_SECONDS = 20 * 60 * 60

def _sleep_report_log(message, *args, level=logging.INFO):
    logger.log(level, "[sleep-report] " + message, *args)

def _trace_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        return [value]
    return [str(value)]


def _load_legacy_report_config():
    """仅在旧技能配置存在时读取，以兼容离线历史部署。"""
    config_path = os.path.join(SKILL_DIR, "config.json")
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        _sleep_report_log("legacy skill config unavailable: %s", type(exc).__name__, level=logging.WARNING)
        return {}


def _resolve_report_config(provider_config=None):
    """合并可选旧技能配置与当前用户 Provider 配置，后者始终优先。"""
    legacy = _load_legacy_report_config()
    provider = provider_config if isinstance(provider_config, dict) else {}
    resolved = dict(legacy)

    for section in ("atimelogger", "huawei_health"):
        legacy_section = legacy.get(section) if isinstance(legacy.get(section), dict) else {}
        provider_section = provider.get(section) if isinstance(provider.get(section), dict) else {}
        resolved[section] = {**legacy_section, **provider_section}

    legacy_ai = legacy.get("ai_model_config") if isinstance(legacy.get("ai_model_config"), dict) else {}
    provider_ai = provider.get("ai_model_config") if isinstance(provider.get("ai_model_config"), dict) else {}
    resolved["ai_model_config"] = {**legacy_ai, **provider_ai}
    return resolved

def format_val(v):
    if v is None: return "N/A"
    try:
        fv = float(v)
        if fv == int(fv): return str(int(fv))
        return f"{fv:.2f}".rstrip('0').rstrip('.')
    except: return str(v)

def _to_float(value):
    try:
        if value is None or value == "--":
            return None
        return float(value)
    except Exception:
        return None

def _duration_hm(seconds):
    seconds = int(seconds or 0)
    return f"{seconds // 3600:02d}:{(seconds % 3600) // 60:02d}"


def tracked_duration_seconds(atimelogger_data):
    activities = atimelogger_data.get('activities', []) if isinstance(atimelogger_data, dict) else (atimelogger_data or [])
    return sum(int(float(activity.get('duration') or ((activity.get('duration_minutes') or 0) * 60))) for activity in activities)

def _band(value, bands, missing="缺失"):
    val = _to_float(value)
    if val is None:
        return missing
    for predicate, label in bands:
        if predicate(val):
            return label
    return "待评估"

def _trend_text(history_list, key, higher_better=True):
    if not history_list or len(history_list) < 2:
        return "趋势样本不足"
    current = _to_float(history_list[-1].get(key))
    previous = _to_float(history_list[-2].get(key))
    if current is None or previous is None:
        return "趋势样本不足"
    diff = current - previous
    if diff == 0:
        return "较上次持平"
    improved = diff > 0 if higher_better else diff < 0
    return f"较上次{'改善' if improved else '恶化'} {_trend_percent_badge(previous, current)}"

def _trend_percent_badge(previous, current):
    try:
        prev = float(previous)
        cur = float(current)
    except (TypeError, ValueError):
        return "百分比变化无法计算"
    diff = cur - prev
    label = "增长" if diff > 0 else "减少" if diff < 0 else "持平"
    if prev == 0:
        if diff == 0:
            return "持平 0.00%"
        return _trend_badge(f"{label} 无法计算百分比", diff)
    pct = abs(diff) / abs(prev) * 100
    text = f"{label} {pct:.2f}%"
    if diff == 0:
        return text
    return _trend_badge(text, diff)

def _trend_badge(text, diff):
    try:
        numeric_diff = float(diff)
    except (TypeError, ValueError):
        return text
    if numeric_diff == 0:
        return text
    arrow = "↑" if numeric_diff > 0 else "↓"
    color, bg, border = (
        ("#dc2626", "#fee2e2", "#fecaca")
        if numeric_diff > 0
        else ("#16a34a", "#dcfce7", "#bbf7d0")
    )
    return (
        f"<span style=\"display:inline-block;padding:1px 8px;border-radius:6px;"
        f"border:1px solid {border};background:{bg};color:{color};"
        f"font-weight:800;white-space:nowrap;\">{text} {arrow}</span>"
    )

def _parse_score_snapshot(raw):
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}

def _official_advice_from_sleep(sleep):
    advice = (
        sleep.get("official_advice")
        or sleep.get("huawei_advice")
        or sleep.get("huawei_official_advice")
    )
    advice = str(advice or "").strip()
    if not advice:
        raise ValueError("未识别到华为运动健康截图中的官方建议原文，报告生成中止。请上传包含建议区域的截图，或重新 OCR。")
    return advice

def _markdown_quote_lines(text):
    lines = str(text or "").splitlines()
    if not lines:
        return [">"]
    return [f"> {line}" if line.strip() else ">" for line in lines]

def _build_exercise_summary(db, date_str, user_id=None):
    empty = {
        "date": date_str,
        "weight": None,
        "daily_score": None,
        "plan_version": None,
        "categories": {},
        "trend": {"status": "样本不足"},
        "history": [],
    }
    if not db or not (hasattr(db, "_connect") or hasattr(db, "_get_connection")):
        return empty
    conn = None
    try:
        conn = db._connect() if hasattr(db, "_connect") else db._get_connection()
        if getattr(db, "requires_report_user_id", False):
            if not isinstance(user_id, int):
                raise ValueError("server_sleep_report_user_id_required")
            rows = conn.execute(
                """SELECT date, plan_version, weight, score_snapshot, updated_at
                   FROM server_exercise_daily_logs WHERE user_id = ? AND date <= ?
                   ORDER BY date DESC, updated_at DESC LIMIT 14""",
                (user_id, date_str),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT date, plan_version, weight, score_snapshot, updated_at
                   FROM server_exercise_daily_logs WHERE date <= ?
                   ORDER BY date DESC, updated_at DESC LIMIT 14""",
                (date_str,),
            ).fetchall()
    except Exception as exc:
        logger.warning("读取运动日报数据失败: %s", exc)
        return empty
    finally:
        if conn:
            conn.close()

    by_date = {}
    for row in rows:
        item = dict(row)
        by_date.setdefault(item.get("date"), item)
    history = [by_date[key] for key in sorted(by_date.keys())]
    current = by_date.get(date_str) or (history[-1] if history and history[-1].get("date") == date_str else None)
    summary = dict(empty)
    summary["history"] = [
        {
            "date": item.get("date"),
            "weight": item.get("weight"),
            "daily_score": _parse_score_snapshot(item.get("score_snapshot")).get("total"),
            "plan_version": item.get("plan_version"),
        }
        for item in history
    ]
    if current:
        snapshot = _parse_score_snapshot(current.get("score_snapshot"))
        summary.update({
            "weight": current.get("weight"),
            "daily_score": snapshot.get("total"),
            "plan_version": current.get("plan_version"),
            "categories": snapshot.get("cats") or {},
        })

    trend = {"status": "样本不足"}
    weight_history = [item for item in summary["history"] if item.get("weight") is not None]
    if summary.get("weight") is not None and len(weight_history) >= 2 and weight_history[-1].get("date") == date_str:
        prev = weight_history[-2]
        cur = weight_history[-1]
        trend["weight_previous"] = float(prev["weight"])
        trend["weight_current"] = float(cur["weight"])
        trend["weight_delta"] = round(trend["weight_current"] - trend["weight_previous"], 2)

    score_history = [item for item in summary["history"] if item.get("daily_score") is not None]
    if summary.get("daily_score") is not None and len(score_history) >= 2 and score_history[-1].get("date") == date_str:
        prev = score_history[-2]
        cur = score_history[-1]
        trend["score_previous"] = float(prev["daily_score"])
        trend["score_current"] = float(cur["daily_score"])
        trend["score_delta"] = round(trend["score_current"] - trend["score_previous"], 2)

    if "weight_delta" in trend or "score_delta" in trend:
        trend["status"] = "ok"
        summary["trend"] = trend
    return summary

def _build_improvement_points(data, analysis):
    points = list(analysis.get("issues") or [])
    sleep = data.get("sleep") or {}
    summary = data.get("summary") or {}
    exercise = data.get("exercise") or {}

    cycles = _to_float(sleep.get("sleep_cycles"))
    if cycles is not None and cycles < 5:
        points.append(f"睡眠周期只有 {format_val(cycles)} 个，今晚需要把睡眠窗口补到至少 5 个周期。")
    fall_asleep = _to_float(sleep.get("fall_asleep_min"))
    if fall_asleep is not None and fall_asleep > 30:
        points.append(f"入睡用时 {format_val(fall_asleep)} 分钟偏长，睡前 60 分钟要减少高刺激输入。")
    wake_up = _to_float(sleep.get("wake_up_min"))
    if wake_up is not None and wake_up > 30:
        points.append(f"起床用时 {format_val(wake_up)} 分钟偏长，明早需要固定开灯、喝水、离床流程。")
    awake_min = _to_float(sleep.get("awake_min"))
    if awake_min is not None and awake_min > 30:
        points.append(f"清醒时长 {format_val(awake_min)} 分钟偏高，需要排查晚间压力、咖啡因或屏幕刺激。")

    breakdown = summary.get("activity_breakdown") or {}
    if breakdown:
        drain = _sum_group(breakdown, TIME_VALUE_GROUPS.get("消耗性投入", []))
        improve = _sum_group(breakdown, TIME_VALUE_GROUPS.get("自我提升", []))
        money = _sum_group(breakdown, TIME_VALUE_GROUPS.get("经济价值", []))
        if drain > improve + money:
            points.append("消耗性投入高于自我提升和经济价值投入，明天要先安排产出，再安排娱乐。")
        if improve + money <= 0:
            points.append("自我提升和经济价值投入接近 0，明天至少补一段输出或副业生产时间。")

    if exercise.get("weight") is None:
        points.append("体重记录缺失，明天补上体重，避免运动复盘没有趋势基准。")
    if exercise.get("daily_score") is None:
        points.append("运动评分缺失，明天完成打卡后确认评分已同步到服务端。")

    if not points:
        points.append("今天没有明显失误，但仍需继续压缩低价值分心时间，给睡眠和产出留出更稳定的窗口。")

    deduped = []
    for item in points:
        if item and item not in deduped:
            deduped.append(item)
    return deduped[:5]

def build_exercise_report_lines(exercise):
    categories = exercise.get("categories") or {}
    trend = exercise.get("trend") or {}
    lines = [
        "### 2.4 运动与体重复盘",
        "",
        "| 指标 | 数值 |",
        "| :--- | :--- |",
        f"| 体重 | {format_val(exercise.get('weight')) if exercise.get('weight') is not None else '未记录'} kg |",
        f"| 每日运动评分 | {format_val(exercise.get('daily_score')) if exercise.get('daily_score') is not None else '未记录'} 分 |",
        f"| 评分来源计划 | {exercise.get('plan_version') or '未记录'} |",
    ]
    for name, value in categories.items():
        if isinstance(value, dict):
            lines.append(f"| {name} | {format_val(value.get('s'))}/{format_val(value.get('m'))} |")
    lines.append("")
    if trend.get("status") != "ok":
        lines.append("- **趋势判断**：趋势样本不足，暂时只分析当日体重和评分。")
    else:
        if exercise.get("weight") is not None and "weight_delta" in trend:
            weight_badge = _trend_percent_badge(trend.get("weight_previous"), trend.get("weight_current"))
            lines.append(f"- **体重趋势**：较上次变化 {weight_badge}。")
        if "score_delta" in trend:
            score_badge = _trend_percent_badge(trend.get("score_previous"), trend.get("score_current"))
            lines.append(f"- **评分趋势**：较上次变化 {score_badge}。")
    lines.append("")
    return lines

SLEEP_SCORE_RULES = [
    ("睡眠周期", "sleep_cycles", "个", True, [
        (lambda v: v >= 6, "优秀"),
        (lambda v: v >= 5, "合格"),
        (lambda v: v >= 4, "不足"),
        (lambda v: v < 4, "严重不足"),
    ]),
    ("总睡眠", "total_sleep_min", "分钟", True, [
        (lambda v: v >= 450, "优秀"),
        (lambda v: v >= 420, "合格"),
        (lambda v: v >= 360, "不足"),
        (lambda v: v < 360, "严重不足"),
    ]),
    ("睡眠评分", "sleep_score", "分", True, [
        (lambda v: v >= 85, "优秀"),
        (lambda v: v >= 75, "良好"),
        (lambda v: v >= 60, "一般"),
        (lambda v: v < 60, "较差"),
    ]),
    ("入睡时长", "fall_asleep_min", "分钟", False, [
        (lambda v: v <= 10, "优秀"),
        (lambda v: v <= 20, "合格"),
        (lambda v: v <= 40, "偏慢"),
        (lambda v: v > 40, "严重拖延"),
    ]),
    ("起床时长", "wake_up_min", "分钟", False, [
        (lambda v: v <= 5, "优秀"),
        (lambda v: v <= 10, "合格"),
        (lambda v: v <= 20, "偏慢"),
        (lambda v: v > 20, "严重赖床"),
    ]),
    ("清醒时长", "awake_min", "分钟", False, [
        (lambda v: v <= 10, "优秀"),
        (lambda v: v <= 15, "合格"),
        (lambda v: v <= 30, "偏高"),
        (lambda v: v > 30, "严重干扰"),
    ]),
    ("清醒次数", "awake_count", "次", False, [
        (lambda v: v == 0, "优秀"),
        (lambda v: v <= 1, "合格"),
        (lambda v: v <= 3, "偏多"),
        (lambda v: v >= 4, "严重破碎"),
    ]),
]

TIME_VALUE_GROUPS = {
    "自我提升": ["输入", "输出", "运动"],
    "经济价值": ["副业生产", "副业营销", "副业研发"],
    "维护性投入": ["吃饭", "家庭", "车", "生活杂事", "状态切换", "拉屎"],
    "消耗性投入": ["娱乐", "松鼠病"],
    "恢复性投入": ["睡觉"],
}

def _hours(seconds):
    return float(seconds or 0) / 3600

def _sum_group(breakdown, names):
    return sum(float(breakdown.get(name, 0) or 0) for name in names)

def build_sleep_coaching_lines(sleep, history_list, analysis):
    lines = [
        "### 1.5 AI 睡眠解读",
        "",
        "| 指标 | 当前值 | 区间评价 | 趋势评价 |",
        "| :--- | :--- | :--- | :--- |",
    ]
    severe = []
    for label, key, unit, higher_better, bands in SLEEP_SCORE_RULES:
        value = sleep.get(key)
        band = _band(value, bands)
        trend = _trend_text(history_list, key, higher_better)
        lines.append(f"| {label} | {format_val(value)}{unit} | {band} | {trend} |")
        if "严重" in band or band in ("较差",):
            severe.append(f"{label}{band}")

    cycles = _to_float(sleep.get("sleep_cycles")) or 0
    if cycles < 3:
        lines.extend([
            "",
            f"> ⚠️ 严重预警：今天睡眠周期只有 {format_val(cycles)} 个，连 3 个都不到，恢复窗口已经被明显压缩。今晚必须优先把睡眠周期救回 5 个，娱乐和分心输入全部后置。",
        ])
    elif cycles < 4:
        lines.extend([
            "",
            f"> ⚠️ 严重预警：今天睡眠周期只有 {format_val(cycles)} 个，低于 4 个就是严重不足，离 5 个合格线差得很远。这会直接削弱第二天的清醒度和执行稳定性。",
        ])
    elif cycles < 5:
        lines.extend([
            "",
            f"> ⚠️ 需要调整：睡眠周期 {format_val(cycles)} 个仍未达标，今晚先把睡眠窗口补到 5 个周期，再安排低优先级活动。",
        ])

    if severe:
        lines.extend([
            "",
            f"- **问题定性**：{', '.join(severe)}。这些不是小瑕疵，是会直接拖垮执行力的硬伤。",
        ])

    insight_items = analysis.get("insights", [])[:3]
    for item in insight_items:
        lines.append(f"- {item}")

    lines.extend([
        "- **次日纠偏动作**：睡前 60 分钟停止娱乐和分心输入；起床后 15 分钟内离开床边；如果做不到，就直接删掉一项低价值娱乐时间。",
        "",
    ])
    return lines

def build_time_value_lines(summary, analysis):
    breakdown = summary.get('activity_breakdown', {}) or {}
    total = sum(float(v or 0) for v in breakdown.values()) or 1
    lines = [
        "### 2.3 AI 时间管理解读",
        "",
        "| 价值类型 | 包含分类 | 用时 | 占比 | 评价 |",
        "| :--- | :--- | :---: | :---: | :--- |",
    ]
    group_seconds = {}
    for group, names in TIME_VALUE_GROUPS.items():
        seconds = _sum_group(breakdown, names)
        group_seconds[group] = seconds
        pct = seconds / total * 100
        if group in ("自我提升", "经济价值"):
            comment = "越高越好，持续增加才有复利"
        elif group == "消耗性投入":
            comment = "越低越好，挤压睡眠时明显扣分"
        elif group == "恢复性投入":
            comment = "结合睡眠周期判断，优先保证恢复质量"
        else:
            comment = "合理即可，过高说明被杂事吞噬"
        lines.append(f"| {group} | {'、'.join(names)} | {_hours(seconds):.1f}h | {pct:.1f}% | {comment} |")

    self_improve = group_seconds.get("自我提升", 0)
    money_value = group_seconds.get("经济价值", 0)
    drain = group_seconds.get("消耗性投入", 0)
    sleep_seconds = group_seconds.get("恢复性投入", 0)
    lines.append("")
    if drain > self_improve + money_value and drain > 3600:
        lines.append("- **关键提醒**：消耗性投入已经压过自我提升和经济价值，这不是有效恢复。明天先压缩娱乐/松鼠病，再谈效率。")
    if self_improve <= 0 and money_value <= 0:
        lines.append("- **关键提醒**：自我提升和经济价值投入接近 0，今天几乎没有给未来的自己增加筹码，别再用忙碌掩盖低价值消耗。")
    if sleep_seconds and drain and drain > sleep_seconds * 0.3:
        lines.append("- **睡眠窗口**：消耗性投入已经有挤压睡眠的风险，今晚必须先保护睡眠周期，再安排娱乐。")
    tm_comment = analysis.get("time_management_comment")
    if tm_comment:
        lines.append(f"- **时间管理点评**：{tm_comment}")
    lines.extend([
        "- **次日纠偏动作**：至少安排一段输出或副业生产，再安排娱乐；娱乐和松鼠病只能放在完成自我提升/经济价值之后。",
        "",
    ])
    return lines

def build_sleep_trend_insights(history_list):
    if not history_list or len(history_list) < 2:
        return ["历史睡眠样本不足，暂时无法判断 7 天变化趋势；建议连续同步至少 3 天后再观察评分、周期和入睡效率。"]

    current = history_list[-1]
    previous = history_list[-2]
    metric_defs = [
        ("睡眠评分", "sleep_score", "分", True),
        ("总睡眠", "total_sleep_min", "分钟", True),
        ("睡眠周期", "sleep_cycles", "个", True),
        ("入睡用时", "fall_asleep_min", "分钟", False),
        ("起床用时", "wake_up_min", "分钟", False),
        ("深睡比例", "deep_sleep_ratio", "%", True),
        ("清醒次数", "awake_count", "次", False),
    ]
    lines = ["### 1.3 关键指标变化解读", ""]
    added = 0
    for label, key, unit, higher_better in metric_defs:
        cur = _to_float(current.get(key))
        prev = _to_float(previous.get(key))
        if cur is None or prev is None:
            continue
        diff = cur - prev
        if diff == 0:
            quality = "保持稳定"
        else:
            is_better = diff > 0 if higher_better else diff < 0
            quality = "改善" if is_better else "走弱"
        pct_badge = _trend_percent_badge(prev, cur)
        lines.append(f"- **{label}**：上一次 {format_val(prev)}{unit}，当前 {format_val(cur)}{unit}，{pct_badge}，趋势判断：{quality}。")
        added += 1
        if added >= 5:
            break

    if added < 3:
        values = [_to_float(item.get("sleep_score")) for item in history_list if _to_float(item.get("sleep_score")) is not None]
        if values:
            avg = sum(values) / len(values)
            lines.append(f"- **近期均值**：最近 {len(values)} 条睡眠评分均值约 {avg:.1f} 分，当前 {format_val(current.get('sleep_score', '--'))} 分，可作为后续观察基准。")
    return lines

def build_sleep_settlement_lines(settlement):
    """只渲染服务端结算快照，绝不在报告层重算分数或金币。"""
    lines = ["### 1.4 睡眠评分计算与金币结算", ""]
    diary_lines = []
    for diary_type, label in (("morning", "晨间"), ("evening", "晚间")):
        status = (settlement or {}).get(f"{diary_type}_diary_reward_status")
        if status == "completed":
            diary_lines.append(f"- **{label}日记奖励**：{settlement.get(f'{diary_type}_diary_reward_amount', 0):+g} 🪙")
        else:
            reason = (settlement or {}).get(f"{diary_type}_diary_reward_reason") or f"{label}日记尚未完成"
            diary_lines.append(f"- **{label}日记奖励**：+0 🪙（{reason}）")
    if not settlement or settlement.get("status") == "not_scored":
        missing = (settlement or {}).get("missing_fields") or ["结算快照"]
        return lines + [f"> 未评分（缺失：{'、'.join(missing)}）", *diary_lines, f"- **净金币**：{(settlement or {}).get('net_amount', 0):+g} 🪙", ""]
    lines += ["| 指标 | 原始值 | 命中规则 | 得分 | 金币说明 |", "| :--- | :--- | :--- | :---: | :--- |"]
    dimensions = settlement.get("dimensions") or {}
    ordered_dimensions = sorted(dimensions.items(), key=lambda entry: -float((entry[1] or {}).get("max_score") or 0))
    for key, item in ordered_dimensions:
        item = item or {"reason": key, "raw_value": "--", "matched_rule": "未生成", "score": 0, "max_score": 0}
        coin_effect = item.get("coin_effect") or "影响睡眠评分奖励；本项无独立金币流水"
        lines.append(f"| {item.get('reason','--')} | {format_val(item.get('raw_value'))} | {item.get('matched_rule','--')} | {item.get('score',0)}/{item.get('max_score',0)} | {coin_effect} |")
    report_completed_at = settlement.get("report_completed_at") or "未生成完整报告"
    max_total = sum(float((item or {}).get("max_score") or 0) for item in dimensions.values())
    lines += ["", f"- **报告时效**：{report_completed_at}", f"- **总分**：{settlement.get('score_total', 0)}/{max_total:g}", f"- **睡眠评分奖励**：{settlement.get('reward_amount', 0):+g} 🪙"]
    lines.append(f"- **睡眠周期不足（<4.0）惩罚**：{settlement.get('cycle_penalty', 0):+g} 🪙")
    lines.append(f"- **深睡时长不足（<60分钟）惩罚**：{settlement.get('deep_sleep_penalty', 0):+g} 🪙")
    bedtime_status = settlement.get("bedtime_coin_status")
    bedtime_reason = settlement.get("bedtime_coin_reason") or ("等待有效入睡记录，未结算" if bedtime_status != "settled" else "入睡时间结算")
    lines.append(f"- **入睡时间结算**：{settlement.get('bedtime_coin_amount', 0):+g} 🪙（{bedtime_reason}）")
    if settlement.get("is_all_complete"):
        lines.append(f"- **睡眠指标全完成奖励**：{settlement.get('completion_reward_amount', 0):+g} 🪙")
    else:
        lines.append(f"- **睡眠指标全完成奖励**：+0 🪙（{settlement.get('completion_reason') or '全部指标须全部满分'}）")
    lines.extend(diary_lines)
    lines.append("- **按时入睡标准**：华为 sleep_start 在 22:30–23:30 得满分；23:31–00:00 得部分分；其他时段未达标。")
    lines.append(f"- **净金币**：{settlement.get('net_amount', 0):+g} 🪙")
    lines.append("")
    return lines


def apply_sleep_settlement_to_report(report_path, settlement):
    """以服务端已结算快照替换报告中的评分段，不在报告层计算规则或金额。"""
    with open(report_path, "r", encoding="utf-8") as report_file:
        report = report_file.read()
    section_start = report.find("### 1.4 睡眠评分计算与金币结算")
    section_end = report.find("### 1.5 华为健康建议", section_start)
    if section_start < 0 or section_end < 0:
        raise ValueError("睡眠报告缺少评分结算段边界")
    rendered = "\n".join(build_sleep_settlement_lines(settlement))
    updated = report[:section_start] + rendered + "\n" + report[section_end:]
    with open(report_path, "w", encoding="utf-8") as report_file:
        report_file.write(updated)
    return updated

def _merge_current_sleep_into_history(history_data, date_str, sleep_data):
    if not sleep_data:
        return history_data
    current_date = sleep_data.get("date") or sleep_data.get("sleep_date") or date_str
    current = dict(sleep_data)
    current["date"] = current_date
    merged = [dict(item) for item in history_data or [] if item.get("date") != current_date]
    merged.append(current)
    merged = [item for item in merged if item.get("date") and item.get("date") <= date_str]
    merged.sort(key=lambda item: item.get("date") or "")
    return merged[-7:]

def _activity_summary_text(data):
    breakdown = data.get('summary', {}).get('activity_breakdown', {})
    if not breakdown:
        return "当日 aTimeLogger 数据不足，暂时无法建立时间分配与睡眠状态的完整关联。"
    total = sum(breakdown.values()) or 1
    top = sorted(breakdown.items(), key=lambda x: x[1], reverse=True)[:3]
    parts = [f"{name} {seconds/3600:.1f}h（{seconds/total*100:.1f}%）" for name, seconds in top]
    return "；".join(parts)

def ensure_rich_analysis(analysis, data):
    sleep = data.get('sleep') or {}
    history = data.get('history_7day') or []
    insights = list(analysis.get('insights') or analysis.get('key_insights') or [])
    recommendations = list(analysis.get('recommendations') or [])
    score = sleep.get('sleep_score', '--')
    cycles = sleep.get('sleep_cycles', '--')
    total_hours = format_val((float(sleep.get('total_sleep_min') or 0) / 60) if sleep.get('total_sleep_min') is not None else '--')
    activity_summary = _activity_summary_text(data)
    fallback_insights = [
        f"⚠️ 今日睡眠评分为 {score} 分，总睡眠约 {total_hours} 小时，睡眠周期 {cycles} 个；每天至少要完成 5 个睡眠周期，达不到就不是“小问题”，而是在透支第二天的清醒度和执行力。",
        f"⚠️ 入睡用时 {sleep.get('fall_asleep_min', '--')} 分钟、起床用时 {sleep.get('wake_up_min', '--')} 分钟；这两项是坏习惯暴露点，睡前拖延和醒后赖床都会直接吞掉恢复质量。",
        f"⚠️ 清醒时长 {sleep.get('awake_min', '--')} 分钟、清醒次数 {sleep.get('awake_count', '--')} 次；如果这两项偏高，别再只说“昨晚没睡好”，要立刻排查晚间压力、咖啡因和睡前屏幕刺激。",
        f"时间分配前三项为：{activity_summary}。这些高占比活动会直接影响睡眠窗口是否被压缩，也会决定第二天恢复后的产出空间。",
        "最近 7 天趋势必须重点看五个方向：睡眠周期是否达到 5 个、是否早睡早起、入睡用时是否收敛、起床用时是否缩短、清醒时长和清醒次数是否下降；单日分数好看但这些指标走弱，也要严肃处理。",
    ]
    for item in fallback_insights:
        if len(insights) >= 5:
            break
        insights.append(item)

    fallback_recommendations = [
        "今晚必须设置固定睡前收尾点：睡前 60 分钟停止高刺激输入，睡前 30 分钟只保留洗漱、整理、低亮度阅读；做不到就明确删掉一项低价值娱乐。",
        "明早前 15 分钟执行固定起床流程：开灯、喝水、离开床边，不在床上处理手机消息；起床用时继续拉长就说明流程没有执行。",
        "明天必须优先保证至少 5 个睡眠周期；如果无法早睡，就压缩低价值娱乐或分心活动，而不是继续压缩睡眠。",
        "用 aTimeLogger 给睡前最后 90 分钟打标签，连续三天观察哪些活动最容易推迟入睡，再决定要限制的具体项目。",
        "第二天上午安排一个 25-45 分钟的轻启动任务，避免恢复不足时直接进入高压任务造成拖延和补偿性分心。",
    ]
    for item in fallback_recommendations:
        if len(recommendations) >= 5:
            break
        recommendations.append(item)

    analysis['insights'] = insights
    analysis['recommendations'] = recommendations
    if not analysis.get('time_management_comment'):
        analysis['time_management_comment'] = f"今日时间分配概览：{activity_summary}。建议把睡眠窗口与最高占比活动放在同一张时间表里看，优先处理挤压睡眠的活动。"
    return analysis

# 路径配置
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)

project_root = os.path.abspath(os.path.join(SKILL_DIR, "..", "..", ".."))
if project_root not in sys.path: sys.path.append(project_root)

try:
    from server.models.database import StudyLogger
except ImportError:
    try:
        from database import StudyLogger
    except ImportError:
        StudyLogger = None

from modules.atimelogger_extractor import AtimeloggerExtractor
from modules.screenshot_parser import ScreenshotParser
from modules.report_paths import resolve_reports_dir

SLEEP_DATA_DIR = os.path.join(SKILL_DIR, "huawei_health_data")

def _report_db_call(db, method, user_id, *args):
    """服务端包装器必须显式传入账号；本地客户端数据库保持原有签名。"""
    target = getattr(db, method)
    if getattr(db, "requires_report_user_id", False):
        if not isinstance(user_id, int):
            raise ValueError("server_sleep_report_user_id_required")
        return target(user_id, *args)
    return target(*args)


def generate_comprehensive_report(date_str, injected_sleep_data=None, force_pull=False, include_time_analysis=True, db=None, provider_config=None, user_id=None):
    """
    生成综合分析报告
    include_time_analysis: 是否包含 Part 2 时间管理部分
    """
    print(f"\n📊 开始生成 {date_str} 深度复盘报告 (模式: {'完整' if include_time_analysis else '仅睡眠'})...")
    _sleep_report_log(
        "generate_comprehensive_report start date=%s include_time_analysis=%s injected_sleep_data=%s force_pull=%s",
        date_str,
        include_time_analysis,
        injected_sleep_data is not None,
        force_pull,
    )

    config = _resolve_report_config(provider_config)

    # 如果没传 db，才尝试自动创建
    if db is None and StudyLogger:
        db = StudyLogger(config)

    # 1. 提取 aTimeLogger 数据
    atimelogger_data = None
    atimelogger_failure_reason = None
    # 核心改进：只要有睡眠数据注入（正在进行 AI 分析），就必须拉取 aTimeLogger 以计算入睡/起床用时
    need_atm = include_time_analysis or (injected_sleep_data is not None)

    if need_atm:
        cached_atimelogger_data = None
        # 如果是强制刷新模式，或者数据库里没有，则直接拉取最新的
        if db:
            cached_atimelogger_data = _report_db_call(db, "get_atm_data", user_id, date_str)
            if cached_atimelogger_data and not cached_atimelogger_data.get('activities'):
                cached_atimelogger_data = None # 数据库里的空记录也视为无效
            if not force_pull:
                atimelogger_data = cached_atimelogger_data
            _sleep_report_log(
                "atimelogger cache date=%s hit=%s force_pull=%s",
                date_str,
                bool(cached_atimelogger_data),
                force_pull,
            )

        if not atimelogger_data or force_pull:
            print(f"🔄 正在从 aTimeLogger 云端同步 {date_str} 的全天记录...")
            _sleep_report_log("atimelogger pull start date=%s", date_str)
            extractor = AtimeloggerExtractor(config.get('atimelogger', {}))
            atimelogger_data = extractor.extract_daily_data(date_str)
            if not atimelogger_data:
                atimelogger_failure_reason = getattr(extractor, "failure_reason", None)
            # 及时回写数据库，覆盖旧缓存
            if atimelogger_data and db:
                _report_db_call(db, "save_atm_data", user_id, date_str, atimelogger_data)
                _sleep_report_log("atimelogger cache save date=%s", date_str)
            if not atimelogger_data and cached_atimelogger_data:
                print("⚠️ 云端 aTimeLogger 返回空数据，改用本地缓存活动记录。")
                _sleep_report_log("atimelogger pull empty fallback_cache date=%s", date_str, level=logging.WARNING)
                atimelogger_data = cached_atimelogger_data

        has_activities = False
        if atimelogger_data:
            if isinstance(atimelogger_data, dict):
                has_activities = bool(atimelogger_data.get('activities'))
            elif isinstance(atimelogger_data, list):
                has_activities = bool(atimelogger_data)

        if include_time_analysis and not has_activities and atimelogger_failure_reason:
            raise RuntimeError(atimelogger_failure_reason)

        if not has_activities:
            print("⚠️ 警告: 未获取到 aTimeLogger 数据，将跳过时间管理部分分析。")
            _sleep_report_log("atimelogger no_activities date=%s include_time_analysis=%s", date_str, include_time_analysis, level=logging.WARNING)

    # 2. 加载华为健康睡眠数据
    sleep_data = injected_sleep_data
    if not sleep_data and db:
        sleep_data = _report_db_call(db, "get_huawei_sleep_data", user_id, date_str)
    tracked_seconds = tracked_duration_seconds(atimelogger_data)
    if include_time_analysis and tracked_seconds < FULL_REPORT_MIN_TRACKED_SECONDS:
        if sleep_data:
            sleep_data['full_report_state'] = 'insufficient_time_records'
            sleep_data['tracked_duration_seconds'] = tracked_seconds
            if db:
                if hasattr(db, "save_huawei_sleep_data"):
                    _report_db_call(db, "save_huawei_sleep_data", user_id, date_str, sleep_data)
        _sleep_report_log("full report skipped date=%s tracked_seconds=%s", date_str, tracked_seconds, level=logging.WARNING)
        if not has_activities:
            raise RuntimeError("当日记录为空，无法生成完整时间管理报告")
        return None

    if sleep_data:
        _sleep_report_log(
            "sleep_data ready date=%s source=%s keys=%s",
            date_str,
            sleep_data.get("source") or sleep_data.get("extracted_by") or "unknown",
            sorted(sleep_data.keys()),
        )
        report_content = sleep_data.get("analysis_report", "")
        if not sleep_data.get("analysis") or not sleep_data["analysis"].get("summary"):
            sleep_data["analysis"] = {"summary": report_content}

    if sleep_data:
        # 归一化计算
        total_min = float(sleep_data.get('total_sleep_min', 0))
        if total_min > 0:
            sleep_data['sleep_cycles'] = round(total_min / 90.0, 2)



        parser = ScreenshotParser()
        activities = atimelogger_data.get('activities', []) if atimelogger_data else []
        _sleep_report_log("transition calculate start date=%s activity_count=%s", date_str, len(activities))
        fall_asleep_min, wake_up_min, atm_start, atm_end = parser.calculate_sleep_transition_times(sleep_data, activities)
        sleep_data['fall_asleep_min'] = int(round(float(fall_asleep_min)))
        sleep_data['wake_up_min'] = int(round(float(wake_up_min)))
        sleep_data['atm_sleep_start'] = atm_start
        sleep_data['atm_sleep_end'] = atm_end
        _sleep_report_log(
            "transition calculate finish date=%s fall_asleep_min=%s wake_up_min=%s atm_start=%s atm_end=%s",
            date_str,
            sleep_data['fall_asleep_min'],
            sleep_data['wake_up_min'],
            atm_start,
            atm_end,
        )

        # ====== 核心步骤: 数据计算 (Data Calculation Trace) ======
        calc_trace = _trace_list(sleep_data.get('calc_trace'))
        try:
            print("\n" + "="*30)
            print(f"🧮 正在执行 {date_str} 数据逻辑复核...")
            _sleep_report_log("calculation trace start date=%s", date_str)

            s_t = sleep_data.get('sleep_start')
            e_t = sleep_data.get('sleep_end')
            t_min = float(sleep_data.get('total_sleep_min', 0))

            # 1. 睡眠周期
            cycles = round(t_min / 90.0, 2)
            sleep_data['sleep_cycles'] = cycles
            trace_item = f"1. 睡眠周期: {t_min}min / 90 = {cycles}个"
            print(f"  [OK] {trace_item}")
            calc_trace.append(trace_item)

            if s_t and e_t:
                sh, sm = map(int, s_t.split(':'))
                eh, em = map(int, e_t.split(':'))
                start_total = sh * 60 + sm
                end_total = eh * 60 + em
                if end_total < start_total: end_total += 24 * 60

                # 2. 清醒时长
                in_bed_min = end_total - start_total
                awake_min = max(0, in_bed_min - t_min)
                sleep_data['awake_min'] = int(awake_min)
                trace_item = f"2. 清醒时长: ({e_t} - {s_t})[{in_bed_min}min] - 睡眠{t_min}min = {int(awake_min)}min"
                print(f"  [OK] {trace_item}")
                calc_trace.append(trace_item)

            # 3. 入睡/起床用时 (从 atimelogger 联动)
            # 注意：内部逻辑已在 parser 中打印日志
            sleep_data['fall_asleep_min'] = int(round(float(fall_asleep_min)))
            sleep_data['wake_up_min'] = int(round(float(wake_up_min)))
            calc_trace.append(f"3. 入睡用时: {sleep_data['fall_asleep_min']}min (由 aTimeLogger 记录计算)")
            calc_trace.append(f"4. 起床用时: {sleep_data['wake_up_min']}min (由 aTimeLogger 记录计算)")
            print(f"  [OK] 关联计算完成: 入睡{sleep_data['fall_asleep_min']}m, 起床{sleep_data['wake_up_min']}m")

            sleep_data['calc_trace'] = calc_trace # 存入字典供报告使用
            print("="*30 + "\n")
            _sleep_report_log("calculation trace finish date=%s trace_count=%s", date_str, len(calc_trace))

        except Exception as e:
            print(f"  ❌ [数据计算] 严重异常: {e}")
            _sleep_report_log("calculation trace failed date=%s error=%s", date_str, e, level=logging.ERROR)
        # ====================================================

    # 3. 分析
    # 4. 强制数据落库：获取到 aTimeLogger 数据后立即存入数据库，确保持久化
    if atimelogger_data and db:
        # 注意：atimelogger_data 本身就是活动列表
        _report_db_call(db, "save_atm_data", user_id, date_str, atimelogger_data)
        logger.info(f"✅ aTimeLogger 原始数据已同步至数据库: {date_str}")
        _sleep_report_log("atimelogger db save date=%s", date_str)

    # 提取最近 7 天的睡眠数据，包含当天，按日期升序排列
    history_data = []
    if db:
        try:
            conn = db._get_connection()
            is_sqlite = (db.db_type == "sqlite")
            if is_sqlite:
                import sqlite3
                old_row_factory = conn.row_factory
                conn.row_factory = sqlite3.Row

            cursor = conn.cursor()
            ph = "%s" if db.db_type == "mysql" else "?"
            if getattr(db, "requires_report_user_id", False):
                if not isinstance(user_id, int):
                    raise ValueError("server_sleep_report_user_id_required")
                cursor.execute(
                    f"SELECT * FROM huawei_sleep_data WHERE user_id = {ph} AND date <= {ph} ORDER BY date DESC LIMIT 7",
                    (user_id, date_str),
                )
            else:
                cursor.execute(f"SELECT * FROM huawei_sleep_data WHERE date <= {ph} ORDER BY date DESC LIMIT 7", (date_str,))

            if is_sqlite:
                rows = [dict(r) for r in cursor.fetchall()]
                conn.row_factory = old_row_factory
            else:
                columns = [desc[0] for desc in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

            cursor.close()
            if is_sqlite:
                conn.close()

            history_data = _merge_current_sleep_into_history(list(reversed(rows)), date_str, sleep_data)
        except Exception as he:
            logger.error(f"获取 7 天睡眠历史趋势失败: {he}")

    combined_data = combine_data(atimelogger_data, sleep_data, date_str, history_7day=history_data)
    combined_data["exercise"] = _build_exercise_summary(db, date_str, user_id)
    analysis = perform_deep_analysis(combined_data, config.get("ai_model_config"))

    # 5. 生成报告文件
    report_path = generate_full_report_file(combined_data, analysis, date_str, include_time_analysis, user_id=user_id)
    _sleep_report_log("report file generated date=%s path=%s", date_str, report_path)

    # 6. 回写睡眠分析报告
    if sleep_data and db and os.path.exists(report_path):
        with open(report_path, 'r', encoding='utf-8') as f:
            full_content = f.read()
        sleep_data["report_status"] = max(int(sleep_data.get("report_status") or 0), 2 if include_time_analysis else 1)
        if include_time_analysis:
            sleep_data["full_report_state"] = "generated"
            sleep_data["tracked_duration_seconds"] = tracked_seconds
        db_data = sleep_data.copy()
        db_data["analysis_report"] = full_content
        if markdown:
            db_data["analysis_html"] = markdown.markdown(full_content, extensions=["fenced_code", "tables"])
        _report_db_call(db, "save_huawei_sleep_data", user_id, date_str, db_data)
        _sleep_report_log(
            "sleep db save date=%s report_status=%s has_html=%s trace_count=%s",
            date_str,
            db_data.get("report_status"),
            bool(db_data.get("analysis_html")),
            len(_trace_list(db_data.get("calc_trace"))),
        )

    return report_path

def combine_data(atimelogger_data, sleep_data, date_str, history_7day=None):
    activities = []
    if isinstance(atimelogger_data, dict):
        activities = atimelogger_data.get('activities', [])
    elif isinstance(atimelogger_data, list):
        activities = atimelogger_data

    normalized_activities = []
    type_durations = defaultdict(int)
    for act in activities:
        a = act.copy()

        # 统一活动类型名称
        a_type = a.get('type') or a.get('activity_type') or '未知'
        a['type'] = a_type
        a['activity_type'] = a_type

        # 统一时间字段 (start/start_time, finish/end_time)
        st = a.get('start') or a.get('start_time') or ''
        et = a.get('finish') or a.get('end_time') or a.get('finish_time') or ''

        # 将 datetime 转为 iso format 字符串，方便统一处理
        if isinstance(st, datetime):
            st = st.isoformat()
        if isinstance(et, datetime):
            et = et.isoformat()

        a['start'] = st
        a['start_time'] = st
        a['finish'] = et
        a['end_time'] = et

        # 统一时长字段 (duration 为秒数)
        dur = a.get('duration') or ((a.get('duration_minutes') or 0) * 60)
        a['duration'] = dur
        a['duration_minutes'] = dur // 60

        normalized_activities.append(a)
        type_durations[a_type] += dur

    norm_atimelogger = {
        'date': date_str,
        'activities': normalized_activities,
        'summary': {
            'total_activities': len(normalized_activities),
            'total_duration': sum(type_durations.values()),
            'type_durations': dict(type_durations)
        }
    }

    return {
        'date': date_str,
        'atimelogger': norm_atimelogger,
        'sleep': sleep_data,
        'history_7day': history_7day or [],
        'summary': {
            'total_tracked_time': sum(type_durations.values()),
            'activity_breakdown': dict(type_durations)
        }
    }

def perform_deep_analysis(data, ai_config=None):
    """
    根据 SKILL.md 的指导思想，调用文本大模型进行深度复盘。
    如果没有配置 AI，则回退到基础统计逻辑。
    """
    import json
    import os

    # 1. 使用调用方传入的当前用户配置；旧技能文件仅作兼容回退。
    config = ai_config if isinstance(ai_config, dict) else _resolve_report_config().get("ai_model_config", {})

    # 2. 从 SKILL.md 读取分析指令
    prompt_tpl = ""
    try:
        skill_path = os.path.join(os.path.dirname(__file__), "SKILL.md")
        if os.path.exists(skill_path):
            with open(skill_path, "r", encoding="utf-8") as f:
                content = f.read()
                if "```analysis_prompt" in content:
                    prompt_tpl = content.split("```analysis_prompt")[1].split("```")[0].strip()
    except: pass

    # 3. 如果有 AI 配置且有提示词，发起请求
    api_key = config.get("text_api_key")
    if api_key and prompt_tpl:
        try:
            base_url = config.get("text_base_url")
            model = config.get("text_model", "glm-4-flash")

            # 准备脱敏数据
            # 准备脱敏数据并处理 datetime 序列化问题
            clean_activities = []
            raw_atm = data.get("atimelogger", {})
            raw_list = raw_atm.get("activities", []) if isinstance(raw_atm, dict) else raw_atm
            if not isinstance(raw_list, list): raw_list = []

            for act in raw_list:
                clean_act = act.copy()
                if isinstance(clean_act.get('start_time'), datetime):
                    clean_act['start_time'] = clean_act['start_time'].isoformat()
                if isinstance(clean_act.get('end_time'), datetime):
                    clean_act['end_time'] = clean_act['end_time'].isoformat()
                clean_activities.append(clean_act)

            # 准备历史睡眠数据脱敏注入
            history_7day = data.get("history_7day", [])
            clean_history = []
            for h in history_7day:
                clean_h = {
                    "date": h.get("date"),
                    "sleep_score": h.get("sleep_score"),
                    "total_sleep_min": h.get("total_sleep_min"),
                    "sleep_cycles": h.get("sleep_cycles"),
                    "fall_asleep_min": h.get("fall_asleep_min"),
                    "wake_up_min": h.get("wake_up_min"),
                    "deep_sleep_ratio": h.get("deep_sleep_ratio"),
                    "awake_count": h.get("awake_count")
                }
                clean_history.append(clean_h)

            input_data = {
                "sleep_metrics": data.get("sleep", {}),
                "time_stats": data.get("summary", {}),
                "exercise_metrics": data.get("exercise", {}),
                "raw_activities": clean_activities[:50],
                "history_7day": clean_history
            }

            client = OpenAI(api_key=api_key, base_url=base_url, http_client=httpx.Client(verify=False))
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt_tpl},
                    {"role": "user", "content": f"请基于以下数据生成分析结果：\n{json.dumps(input_data, ensure_ascii=False)}"}
                ],
                temperature=0.7,
                # 某些模型支持 json_object，不支持的也会因为 prompt 要求返回 JSON
            )

            content = resp.choices[0].message.content
            if not content:
                raise Exception("大模型返回分析内容为空")
            raw_content = content.strip()
            # 清理可能的 markdown 标签
            if "```json" in raw_content:
                raw_content = raw_content.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_content:
                raw_content = raw_content.split("```")[1].split("```")[0].strip()

            result = json.loads(raw_content)
            print(f"✅ AI 深度分析完成 (Model: {model})")
            return ensure_rich_analysis(result, data)
        except Exception as e:
            print(f"⚠️ AI 分析调用失败，回退到基础逻辑: {e}")

    # 4. 基础兜底逻辑 (计算得分)
    activity_breakdown = data.get('summary', {}).get('activity_breakdown', {})
    productive_hrs = activity_breakdown.get('生产', 0) / 3600
    sleep_score = data.get('sleep', {}).get('sleep_score', 0)

    score = 60
    if productive_hrs > 3: score += 20
    if sleep_score > 80: score += 20

    return ensure_rich_analysis({
        'efficiency_score': min(100, score),
        'summary': "今天表现不错，继续保持！" if score >= 80 else "还有提升空间，加油！",
        'insights': ["保持专注是提升效率的关键。", "合理的睡眠能显著提升次日状态。"],
        'recommendations': ["建议睡前 1 小时放下手机。", "明天尝试增加一个番茄钟的生产时间。"],
        'issues': ["睡眠时长不足"] if sleep_score < 70 else []
    }, data)

def generate_full_report_file(data, analysis, date_str, include_time_analysis=True, user_id=None):
    """生成完整报告文件"""
    sleep = data.get('sleep', {})
    summary = data.get('summary', {})
    activities = data.get('atimelogger', {}).get('activities', []) if data.get('atimelogger') else []
    exercise = data.get('exercise') or {}

    model_info = sleep.get('extracted_by', '未知模型')
    lines = [
        f"# 📔 深度复盘报告 - {date_str}",
        "",
        f"> **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | **解析模型**: `{model_info}`",
        "",
        "---",
        "",
        "## 🌙 [Part 1: 睡眠健康报告]",
        "",
    ]

    if sleep:
        lines.extend([
            "### 1.1 核心数据",
            "",
            "| 指标 | 详细数据 | 状态评估 |",
            "| :--- | :--- | :--- |",
            f"| 🔄 **睡眠周期** | {format_val(sleep.get('sleep_cycles', 0))} 个 | {'✅ 达标' if float(sleep.get('sleep_cycles') or 0) >= 5 else '⚠️ 略少'} |",
            f"| 💤 **深睡时长** | {sleep.get('deep_sleep_min', '--')} min | {'参考: 60-120' if float(sleep.get('deep_sleep_min') or 0) > 0 else '-'} |",
            f"| ☕ **清醒时长** | {sleep.get('awake_min', '--')} min | {'参考: < 15' if float(sleep.get('awake_min') or 0) > 0 else '-'} |",
            f"| 😲 **清醒次数** | {sleep.get('awake_count', '--')} 次 | {'优秀' if int(sleep.get('awake_count') or 0) <= 1 else '正常'} |",
            f"| 🌙 **入睡用时** | {sleep.get('fall_asleep_min', '--')} min | {'✅ 极快' if float(sleep.get('fall_asleep_min') or 0) < 20 else '正常'} |",
            f"| ☀️ **起床用时** | {sleep.get('wake_up_min', '--')} min | {'✅ 迅速' if float(sleep.get('wake_up_min') or 0) < 15 else '赖床'} |",
            f"| 🛌 **上床时间** | {sleep.get('atm_sleep_start', '--')} | - |",
            f"| 🛌 **入睡时间** | {sleep.get('sleep_start', '--')} | - |",
            f"| ⏰ **醒来时间** | {sleep.get('sleep_end', '--')} | - |",
            f"| ⏰ **下床时间** | {sleep.get('atm_sleep_end', '--')} | - |",
            "",
            f"> 💡 *注：以上原始数据由 `{model_info}` 视觉提取，经公式核验自洽。*",
            "",
        ])

        # 生成最近 7 天睡眠指标变化趋势表
        trend_lines = [
            "### 1.2 最近 7 天睡眠变化趋势",
            "",
            "| 日期 | 睡眠评分 | 总时长 (小时) | 睡眠周期 (个) | 入睡用时 (分钟) | 起床用时 (分钟) | 深睡比例 (%) | 清醒次数 (次) |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |"
        ]
        history_list = data.get('history_7day', [])
        if history_list:
            for item in history_list:
                h_date = item.get('date', '--')
                h_score = format_val(item.get('sleep_score', '--'))
                h_total_hrs = format_val(round(float(item.get('total_sleep_min') or 0)/60, 2)) if item.get('total_sleep_min') is not None else '--'
                h_cycles = format_val(item.get('sleep_cycles', '--'))
                h_fall_asleep = format_val(item.get('fall_asleep_min', '--'))
                h_wake_up = format_val(item.get('wake_up_min', '--'))
                h_deep_ratio = format_val(item.get('deep_sleep_ratio', '--'))
                h_awake_count = format_val(item.get('awake_count', '--'))

                trend_lines.append(
                    f"| {h_date} | {h_score} 分 | {h_total_hrs} 小时 | {h_cycles} 个 | {h_fall_asleep} min | {h_wake_up} min | {h_deep_ratio} % | {h_awake_count} 次 |"
                )
        else:
            trend_lines.append("| -- | 暂无历史趋势数据 | -- | -- | -- | -- | -- | -- |")

        trend_lines.append("")
        trend_lines.extend(build_sleep_trend_insights(history_list))
        trend_lines.append("")
        lines.extend(trend_lines)

        lines.extend(build_sleep_settlement_lines(sleep.get("score_settlement")))

        interp = _official_advice_from_sleep(sleep)

        lines.extend([
            "",
            "### 1.5 华为健康建议",
        ])
        lines.extend(_markdown_quote_lines(interp))
        lines.extend([
            "",
            "#### 1.5.1 🧮 逻辑复核 Trace",
            "```text",
        ])
        for t in sleep.get('calc_trace', []):
            lines.append(t)
        lines.append("```")
        lines.append("")

        lines.extend(build_sleep_coaching_lines(sleep, history_list, analysis))

    else:
        lines.append("> ⚠️ 今日未同步睡眠数据\n")

    if include_time_analysis and sleep:
        refl = (sleep.get('morning_diary') or sleep.get('sleep_reflection') or '').strip()
        lines.extend([
            "### 1.6 晨间日记",
            f"> {refl if refl else '*今日未记录晨间日记*'}",
            "",
        ])

    if include_time_analysis:
        lines.extend([
            "---",
            "",
            "## ⏱️ [Part 2: 时间管理报告]",
            "",
            "### 2.1 原始记录流水",
            "",
            "| 开始 | 结束 | 项目 | 时长(min) |",
            "| :--- | :--- | :--- | :--- |"
        ])

        for act in activities:
            start = act.get('start_time', '').split('T')[-1][:5]
            end = act.get('end_time', '').split('T')[-1][:5]
            duration = round(act.get('duration', 0) / 60, 1)
            lines.append(f"| {start} | {end} | {act.get('type', '未知')} | {duration} |")

        lines.extend([
            "",
            "### 2.2 时间分配汇总",
            "",
        ])

        activity_breakdown = summary.get('activity_breakdown', {})
        total_seconds = sum(activity_breakdown.values())
        if total_seconds > 0:
            lines.append("```")
            for activity_type, seconds in sorted(activity_breakdown.items(), key=lambda x: x[1], reverse=True):
                percentage = (seconds / total_seconds) * 100
                bar = '█' * int(percentage / 3)
                lines.append(f"{activity_type:8s} {bar:30s} {seconds/3600:5.1f}h ({percentage:4.1f}%)")
            lines.append("```")

        lines.extend(build_time_value_lines(summary, analysis))
        lines.extend(build_exercise_report_lines(exercise))
    elif not include_time_analysis:
        lines.extend([
            "",
            "### 🎯 睡眠行动建议",
            "",
        ])
        for rec in analysis.get('recommendations', [])[:5]:
            lines.append(f"- {rec}")
        lines.append("")
        if sleep:
            refl = (sleep.get('morning_diary') or sleep.get('sleep_reflection') or '').strip()
            lines.extend([
                "### 1.6 晨间日记",
                f"> {refl if refl else '*今日未记录晨间日记*'}",
                "",
            ])

    if include_time_analysis:
        lines.extend([
            "",
            "### 2.5 待改善点",
            "",
        ])
        for issue in _build_improvement_points(data, analysis):
            lines.append(f"- {issue}")
        lines.append("")

        lines.extend([
            "### 2.6 行动建议",
            "",
        ])
        recommendations = analysis.get('recommendations', [])
        if recommendations:
            for rec in recommendations[:5]:
                lines.append(f"- {rec}")
        else:
            lines.append("- 暂无新增行动建议。")
        lines.append("")

        if sleep:
            eve = (sleep.get('evening_diary') or '').strip()
            lines.extend([
                "### 2.7 晚间日记",
                f"> {eve if eve else '*今日未记录晚间复盘*'}",
                "",
            ])

    report_path = generate_report_filename(date_str, user_id=user_id)
    temp_path = f"{report_path}.tmp-{os.getpid()}"
    with open(temp_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    os.replace(temp_path, report_path)
    return str(report_path)

def generate_report_filename(date_str, user_id=None):
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    weekday_cn = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][date_obj.weekday()]
    week_number = date_obj.isocalendar()[1]
    filename = f"{date_str} {weekday_cn} w{week_number:02d}.md"
    reports_dir = resolve_reports_dir() if user_id is None else resolve_reports_dir(user_id=user_id)
    return str(reports_dir / filename)

if __name__ == '__main__':
    d_str = sys.argv[1] if len(sys.argv) > 1 else (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    generate_comprehensive_report(d_str)
