# -*- coding: utf-8 -*-
"""服务端唯一的睡眠评分规则。客户端和报告只能读取其结算快照。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import uuid


RULE_VERSION = "sleep-score-v3"
LEGACY_RULE_VERSION = "sleep-score-v2"
V3_EFFECTIVE_DATE = "2026-09-10"
V4_RULE_VERSION = "sleep-score-v4"
V4_EFFECTIVE_DATE = "2026-09-12"
DIARY_REWARD_EFFECTIVE_DATE = "2026-09-06"
DIARY_REWARD_VERSION = "v1"
DIARY_REWARD_AMOUNT = 10.0
BEDTIME_COIN_EFFECTIVE_DATE = "2026-09-08"
BEDTIME_COIN_RULE_VERSION = "bedtime-coin-v1"
REQUIRED_FIELDS = (
    "sleep_start", "sleep_end", "sleep_score", "deep_sleep_min", "sleep_cycles",
    "awake_min", "awake_count", "fall_asleep_min", "wake_up_min",
)


def report_available(metrics: dict) -> bool:
    """报告成功状态与持久化正文必须同时存在，评分才可见。"""
    metrics = metrics or {}
    try:
        successful = int(metrics.get("report_status") or 0) >= 1
    except (TypeError, ValueError):
        successful = False
    body = str(metrics.get("analysis_report") or metrics.get("analysis_html") or "").strip()
    return successful and bool(body)


def rule_version_for_date(sleep_date) -> str:
    date = str(sleep_date or "")[:10]
    if date >= V4_EFFECTIVE_DATE:
        return V4_RULE_VERSION
    return RULE_VERSION if date >= V3_EFFECTIVE_DATE else LEGACY_RULE_VERSION


def _not_scored(missing_fields, rule_version=RULE_VERSION) -> dict:
    return {"status": "not_scored", "missing_fields": list(missing_fields), "dimensions": {}, "score_total": 0,
            "reward_amount": 0, "cycle_penalty": 0, "deep_sleep_penalty": 0, "no_sleep_penalty": 0,
            "completion_reward_amount": 0, "is_all_complete": False,
            "completion_reason": "等待可见睡眠报告", "net_amount": 0, "rule_version": rule_version}


def select_authoritative_sleep_settlements(rows) -> dict[str, dict]:
    """每个睡眠日只返回一条可以影响金币的已评分结算。"""
    grouped: dict[str, list[dict]] = {}
    for raw in rows:
        row = dict(raw)
        if row.get("settlement_status") != "scored":
            continue
        sleep_date = str(row.get("sleep_date") or "")[:10]
        if sleep_date:
            grouped.setdefault(sleep_date, []).append(row)

    def rank(row: dict):
        return (
            int(str(row.get("rule_version") or "") == rule_version_for_date(row.get("sleep_date"))),
            str(row.get("updated_at") or ""),
            str(row.get("created_at") or ""),
            str(row.get("rule_version") or ""),
        )

    return {sleep_date: max(candidates, key=rank) for sleep_date, candidates in grouped.items()}


def select_authoritative_sleep_diary_settlements(rows) -> dict[str, dict]:
    """日记完成可以在评分资料不齐时独立成为当前规则事实。"""
    grouped: dict[str, list[dict]] = {}
    for raw in rows:
        row = dict(raw)
        sleep_date = str(row.get("sleep_date") or "")[:10]
        if sleep_date:
            grouped.setdefault(sleep_date, []).append(row)
    def rank(row: dict):
        return (int(str(row.get("rule_version") or "") == rule_version_for_date(row.get("sleep_date"))),
                str(row.get("updated_at") or ""), str(row.get("created_at") or ""))
    return {sleep_date: max(candidates, key=rank) for sleep_date, candidates in grouped.items()}


def _number(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _time_minutes(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.strptime(value.strip()[:5], "%H:%M")
    except ValueError:
        return None
    return parsed.hour * 60 + parsed.minute


def calculate_bedtime_coin(sleep_start) -> dict:
    """按主睡眠入睡时刻返回独立金币结果。"""
    minute = _time_minutes(sleep_start)
    if minute is None:
        return {"status": "pending", "amount": 0.0, "reason": "等待有效入睡记录"}
    if 18 * 60 <= minute <= 23 * 60:
        amount, reason = 20.0, "18:00–23:00入睡，获得满额奖励"
    elif 23 * 60 < minute <= 23 * 60 + 30:
        amount, reason = 12.0, "23:01–23:30入睡，获得六折奖励"
    elif minute > 23 * 60 + 30 or minute == 0:
        amount, reason = 6.0, "23:31–00:00入睡，获得三折奖励"
    elif minute <= 60:
        amount, reason = 0.0, "00:01–01:00入睡，不奖不罚"
    elif minute <= 120:
        amount, reason = -20.0, "01:01–02:00入睡，扣20金币"
    elif minute <= 180:
        amount, reason = -40.0, "02:01–03:00入睡，扣40金币"
    elif minute <= 240:
        amount, reason = -60.0, "03:01–04:00入睡，扣60金币"
    elif minute <= 300:
        amount, reason = -80.0, "04:01–05:00入睡，扣80金币"
    else:
        amount, reason = -100.0, "05:01后入睡或白天记录无效，扣100金币"
    return {"status": "settled", "amount": amount, "reason": reason}


def _row(raw, matched_rule, score, maximum, reason):
    return {
        "raw_value": raw,
        "matched_rule": matched_rule,
        "score": score,
        "max_score": maximum,
        "reason": reason,
    }


def _coin_text(amount, reason):
    """结算快照内的稳定展示文案；金额从规则事实读取，不由展示层重算。"""
    return f"{float(amount or 0):+g} 🪙：{reason}"


def _add_v4_coin_attribution(dimensions: dict, metrics: dict) -> dict:
    """为 V4 的八项评分保存金币归因，供 PC、Android 与完整报告共同读取。"""
    dimensions = {key: dict(value or {}) for key, value in (dimensions or {}).items()}
    cycles = _number(metrics.get("sleep_cycles"))
    deep = _number(metrics.get("deep_sleep_min"))
    bedtime = calculate_bedtime_coin(metrics.get("sleep_start"))
    for key, row in dimensions.items():
        row["coin_effect"] = "影响睡眠评分奖励；本项无独立金币流水"
        if key == "sleep_cycles":
            row["coin_effect"] = _coin_text(-50 if cycles is not None and cycles < 4 else 0,
                                             "睡眠周期不足（<4.0）惩罚" if cycles is not None and cycles < 4 else "未触发周期惩罚")
        elif key == "deep_sleep":
            row["coin_effect"] = _coin_text(-20 if deep is not None and deep < 60 else 0,
                                             "深睡时长不足（<60分钟）惩罚" if deep is not None and deep < 60 else "未触发深睡惩罚")
        elif key == "on_time_sleep":
            reason = bedtime["reason"] if bedtime["status"] == "settled" else "等待有效入睡记录，未结算"
            row["coin_effect"] = _coin_text(bedtime["amount"], reason)
    return dimensions


def _report_before_nine(sleep_date: str | None, completed_at) -> bool:
    """仅按服务端完成时刻判定睡眠日北京时间 09:00 的报告时效。"""
    if not sleep_date or not completed_at:
        return False
    try:
        deadline = datetime.strptime(str(sleep_date)[:10], "%Y-%m-%d").replace(
            hour=9, tzinfo=timezone(timedelta(hours=8)),
        )
        text = str(completed_at).strip().replace("Z", "+00:00")
        completed = datetime.fromisoformat(text)
        if completed.tzinfo is None:
            completed = completed.replace(tzinfo=timezone(timedelta(hours=8)))
        return completed.astimezone(timezone(timedelta(hours=8))) <= deadline
    except (TypeError, ValueError):
        return False


def _calculate_sleep_score_v4(metrics: dict) -> dict:
    """V4 固定八项评分；规则尚未配置化，结算快照仍是展示唯一来源。"""
    rule_version = V4_RULE_VERSION
    if _is_no_main_sleep(metrics):
        fields = (
            ("sleep_cycles", "sleep_cycles", 30, "睡眠周期"),
            ("on_time_sleep", "sleep_start", 20, "按时入睡"),
            ("wake_up", "wake_up_min", 15, "起床用时"),
            ("awake_count", "awake_count", 10, "清醒次数"),
            ("deep_sleep", "deep_sleep_min", 10, "深睡时长"),
            ("report_before_nine", "report_completed_at", 5, "9点前生成睡眠报告"),
            ("huawei_sleep_score", "sleep_score", 5, "华为睡眠评分"),
            ("awake_duration", "awake_min", 5, "清醒时长"),
        )
        dimensions = _add_v4_coin_attribution({key: _row(metrics.get(raw), "无有效主睡眠", 0, maximum, reason)
                                                for key, raw, maximum, reason in fields}, metrics)
        return {"status": "scored", "missing_fields": [], "dimensions": dimensions, "score_total": 0,
                "reward_amount": 0, "cycle_penalty": -50, "deep_sleep_penalty": -20,
                "no_sleep_penalty": -200, "completion_reward_amount": 0, "is_all_complete": False,
                "completion_reason": "无有效主睡眠，八项均为0分", "report_completed_at": None,
                "net_amount": -270, "rule_version": rule_version}
    if not report_available(metrics):
        return _not_scored(["report"], rule_version)
    required = ("sleep_start", "sleep_score", "deep_sleep_min", "sleep_cycles", "awake_min", "awake_count", "wake_up_min")
    missing = [field for field in required if metrics.get(field) in (None, "")]
    missing.extend(field for field in required[1:] if field not in missing and _number(metrics.get(field)) is None)
    if _time_minutes(metrics.get("sleep_start")) is None:
        missing.append("sleep_start")
    missing = sorted(set(missing))
    if missing:
        return _not_scored(missing, rule_version)

    start = _time_minutes(metrics["sleep_start"])
    score = _number(metrics["sleep_score"])
    deep = _number(metrics["deep_sleep_min"])
    cycles = _number(metrics["sleep_cycles"])
    awake_min = _number(metrics["awake_min"])
    awake_count = _number(metrics["awake_count"])
    wake = _number(metrics["wake_up_min"])
    completed_at = metrics.get("report_completed_at")
    report_on_time = _report_before_nine(metrics.get("sleep_date") or metrics.get("date"), completed_at)
    dimensions = {}
    dimensions["sleep_cycles"] = _row(cycles, ">=5.5" if cycles >= 5.5 else "5–<5.5" if cycles >= 5 else "<5", 30 if cycles >= 5.5 else 25 if cycles >= 5 else 0, 30, "睡眠周期")
    if 22 * 60 + 30 <= start <= 23 * 60 + 30:
        dimensions["on_time_sleep"] = _row(metrics["sleep_start"], "22:30–23:30", 20, 20, "按时入睡")
    elif start >= 23 * 60 + 31 or start == 0:
        dimensions["on_time_sleep"] = _row(metrics["sleep_start"], "23:31–00:00", 10, 20, "较晚入睡")
    else:
        dimensions["on_time_sleep"] = _row(metrics["sleep_start"], "其他时段", 0, 20, "未达到按时入睡")
    dimensions["wake_up"] = _row(wake, "<=20分钟" if wake <= 20 else "21–40分钟" if wake <= 40 else ">40分钟", 15 if wake <= 20 else 6 if wake <= 40 else 0, 15, "起床用时")
    dimensions["awake_count"] = _row(awake_count, "0次" if awake_count == 0 else "1次" if awake_count == 1 else ">1次", 10 if awake_count == 0 else 5 if awake_count == 1 else 0, 10, "清醒次数")
    dimensions["deep_sleep"] = _row(deep, ">=120分钟" if deep >= 120 else "90–119分钟" if deep >= 90 else "60–89分钟" if deep >= 60 else "<60分钟", 10 if deep >= 120 else 6 if deep >= 90 else 2 if deep >= 60 else 0, 10, "深睡时长")
    report_rule = "09:00前已生成" if report_on_time else ("09:00后生成" if completed_at else "未生成完整报告")
    dimensions["report_before_nine"] = _row(completed_at, report_rule, 5 if report_on_time else 0, 5, "9点前生成睡眠报告")
    dimensions["huawei_sleep_score"] = _row(score, ">=85" if score >= 85 else "75–84" if score >= 75 else "65–74" if score >= 65 else "<65", 5 if score >= 85 else 3 if score >= 75 else 1 if score >= 65 else 0, 5, "华为睡眠评分")
    dimensions["awake_duration"] = _row(awake_min, "0分钟" if awake_min == 0 else "1–9分钟" if awake_min < 10 else ">=10分钟", 5 if awake_min == 0 else 2 if awake_min < 10 else 0, 5, "清醒时长")
    dimensions = _add_v4_coin_attribution(dimensions, metrics)
    total = sum(item["score"] for item in dimensions.values())
    reward = 80 if total >= 90 else 50 if total >= 80 else 30 if total >= 70 else 10 if total >= 60 else 0
    cycle_penalty = -50 if cycles < 4 else 0
    deep_sleep_penalty = -20 if deep < 60 else 0
    is_all_complete = all(item["score"] == item["max_score"] for item in dimensions.values())
    completion_reward = 200 if is_all_complete else 0
    return {"status": "scored", "missing_fields": [], "dimensions": dimensions, "score_total": total,
            "reward_amount": reward, "cycle_penalty": cycle_penalty, "deep_sleep_penalty": deep_sleep_penalty, "no_sleep_penalty": 0,
            "completion_reward_amount": completion_reward, "is_all_complete": is_all_complete,
            "completion_reason": "八项睡眠指标均满分" if is_all_complete else "存在未满分睡眠指标",
            "report_completed_at": completed_at, "net_amount": reward + completion_reward + cycle_penalty + deep_sleep_penalty,
            "rule_version": rule_version}
def calculate_sleep_score(metrics: dict) -> dict:
    """返回可持久化的十维评分；报告时效由服务端完成时刻提供。"""
    metrics = metrics or {}
    rule_version = rule_version_for_date(metrics.get("sleep_date") or metrics.get("date"))
    if rule_version == V4_RULE_VERSION:
        return _calculate_sleep_score_v4(metrics)
    if not report_available(metrics):
        return _not_scored(["report"], rule_version)
    missing = [field for field in REQUIRED_FIELDS if metrics.get(field) in (None, "")]
    numeric_fields = REQUIRED_FIELDS[2:]
    missing.extend(field for field in numeric_fields if field not in missing and _number(metrics.get(field)) is None)
    if _time_minutes(metrics.get("sleep_start")) is None:
        missing.append("sleep_start")
    if _time_minutes(metrics.get("sleep_end")) is None:
        missing.append("sleep_end")
    missing = sorted(set(missing))
    if missing:
        return _not_scored(missing, rule_version)

    start = _time_minutes(metrics["sleep_start"])
    end = _time_minutes(metrics["sleep_end"])
    atm_end = _time_minutes(metrics.get("atm_sleep_end"))
    score = _number(metrics["sleep_score"])
    deep = _number(metrics["deep_sleep_min"])
    cycles = _number(metrics["sleep_cycles"])
    awake_min = _number(metrics["awake_min"])
    awake_count = _number(metrics["awake_count"])
    fall = _number(metrics["fall_asleep_min"])
    wake = _number(metrics["wake_up_min"])

    dimensions = {}
    completed_at = metrics.get("report_completed_at")
    report_on_time = _report_before_nine(metrics.get("sleep_date") or metrics.get("date"), completed_at)
    report_rule = "09:00前已生成" if report_on_time else ("09:00后生成" if completed_at else "未生成完整报告")
    dimensions["report_before_nine"] = _row(completed_at, report_rule, 5 if report_on_time else 0, 5, "9点前生成睡眠报告")
    if 22 * 60 + 30 <= start <= 23 * 60 + 30:
        dimensions["on_time_sleep"] = _row(metrics["sleep_start"], "22:30–23:30", 10, 10, "按时入睡")
    elif start >= 23 * 60 + 31 or start <= 0:
        dimensions["on_time_sleep"] = _row(metrics["sleep_start"], "23:31–00:00", 5, 10, "较晚入睡")
    else:
        dimensions["on_time_sleep"] = _row(metrics["sleep_start"], "其他时段", 0, 10, "未达到按时入睡")
    wake_value = atm_end if rule_version == RULE_VERSION else end
    wake_raw = metrics.get("atm_sleep_end") if rule_version == RULE_VERSION else metrics["sleep_end"]
    wake_rule = "缺少 aTimeLogger 睡眠结束记录" if wake_value is None else "06:00–08:30" if 360 <= wake_value <= 510 else "08:31–09:30" if 511 <= wake_value <= 570 else "其他时段"
    dimensions["wake_regular"] = _row(wake_raw, wake_rule, 10 if wake_value is not None and 360 <= wake_value <= 510 else 5 if wake_value is not None and 511 <= wake_value <= 570 else 0, 10, "起床规律（aTimeLogger截止时刻）" if rule_version == RULE_VERSION else "起床规律")
    dimensions["huawei_sleep_score"] = _row(score, ">=85" if score >= 85 else "75–84" if score >= 75 else "65–74" if score >= 65 else "<65", 5 if score >= 85 else 3 if score >= 75 else 1 if score >= 65 else 0, 5, "华为睡眠评分")
    dimensions["deep_sleep"] = _row(deep, ">=90分钟" if deep >= 90 else "60–89分钟" if deep >= 60 else "<60分钟", 10 if deep >= 90 else 5 if deep >= 60 else 0, 10, "深睡时长")
    dimensions["sleep_cycles"] = _row(cycles, ">=5.5" if cycles >= 5.5 else "5–<5.5" if cycles >= 5 else "4–<5" if cycles >= 4 else "<4", 30 if cycles >= 5.5 else 25 if cycles >= 5 else 0, 30, "睡眠周期")
    dimensions["awake_duration"] = _row(awake_min, "<=20分钟" if awake_min <= 20 else "21–40分钟" if awake_min <= 40 else ">40分钟", 5 if awake_min <= 20 else 2 if awake_min <= 40 else 0, 5, "清醒时长")
    dimensions["awake_count"] = _row(awake_count, "<=2次" if awake_count <= 2 else "3次" if awake_count == 3 else ">=4次", 5 if awake_count <= 2 else 2 if awake_count == 3 else 0, 5, "清醒次数")
    dimensions["fall_asleep"] = _row(fall, "<=30分钟" if fall <= 30 else "31–60分钟" if fall <= 60 else ">60分钟", 15 if fall <= 30 else 6 if fall <= 60 else 0, 15, "入睡用时")
    dimensions["wake_up"] = _row(wake, "<=20分钟" if wake <= 20 else "21–40分钟" if wake <= 40 else ">40分钟", 5 if wake <= 20 else 2 if wake <= 40 else 0, 5, "起床用时")
    total = sum(item["score"] for item in dimensions.values())
    reward = 80 if total >= 90 else 50 if total >= 80 else 30 if total >= 70 else 10 if total >= 60 else 0
    penalty = -50 if cycles < 4 else 0
    is_all_complete = all(item["score"] == item["max_score"] for item in dimensions.values())
    completion_reward = 100 if is_all_complete else 0
    return {"status": "scored", "missing_fields": [], "dimensions": dimensions, "score_total": total,
            "reward_amount": reward, "cycle_penalty": penalty, "deep_sleep_penalty": 0, "no_sleep_penalty": 0, "completion_reward_amount": completion_reward,
            "is_all_complete": is_all_complete,
            "completion_reason": "十项睡眠指标均满分" if is_all_complete else "存在未满分睡眠指标",
            "report_completed_at": completed_at, "net_amount": reward + completion_reward + penalty,
            "rule_version": rule_version}


def _deep_sleep_penalty_from_snapshot(rule_version, dimensions) -> float:
    """V4 的深睡处罚随评分快照重放，避免给旧结算增加新处罚。"""
    if rule_version != V4_RULE_VERSION:
        return 0.0
    if isinstance(dimensions, str):
        dimensions = json.loads(dimensions or "{}")
    item = (dimensions or {}).get("deep_sleep") or {}
    raw = _number(item.get("raw_value"))
    return -20.0 if raw is not None and raw < 60 else 0.0


def _is_no_main_sleep(metrics) -> bool:
    return isinstance(metrics, dict) and (
        metrics.get("full_report_state") == "no_main_sleep"
        or metrics.get("record_state") == "no_main_sleep"
    )


def _no_sleep_penalty_from_snapshot(rule_version, metrics_snapshot) -> float:
    if rule_version != V4_RULE_VERSION:
        return 0.0
    if isinstance(metrics_snapshot, str):
        metrics_snapshot = json.loads(metrics_snapshot or "{}")
    return -200.0 if _is_no_main_sleep(metrics_snapshot) else 0.0


class SleepRewardService:
    """结算快照和钱包流水在同一服务端事务内生成。"""

    def __init__(self, transact, now_fn, wallet, record_change):
        self._transact, self._now, self._wallet, self._record_change = transact, now_fn, wallet, record_change

    def settle(self, user_id: int, sleep_date: str, metrics: dict) -> dict:
        with self._transact() as conn:
            return self.settle_in_txn(conn, user_id, sleep_date, metrics)

    def settle_in_txn(self, conn, user_id: int, sleep_date: str, metrics: dict) -> dict:
        rule_version = rule_version_for_date(sleep_date)
        existing = conn.execute(
            "SELECT * FROM server_sleep_score_settlements WHERE user_id=? AND sleep_date=? AND rule_version=?",
            (user_id, sleep_date, rule_version),
        ).fetchone()
        if existing:
            saved = self._result_from_existing(existing)
            completed_at = metrics.get("report_completed_at")
            if not report_available(metrics) or saved.get("report_completed_at"):
                if saved["status"] == "scored":
                    self.reconcile_sleep_ledger_in_txn(conn, user_id, sleep_date)
                return saved
            result = calculate_sleep_score(metrics)
            now = self._now()
            result["net_amount"] += sum(float(existing[key] or 0) for key in (
                "diary_completion_reward_amount", "morning_diary_reward_amount", "evening_diary_reward_amount",
                "bedtime_coin_amount"))
            conn.execute(
                """UPDATE server_sleep_score_settlements SET metrics_snapshot=?,score_breakdown=?,score_total=?,
                   reward_amount=?,cycle_penalty=?,net_amount=?,settlement_status=?,missing_fields=?,
                   report_completed_at=?,completion_reward_amount=?,is_all_complete=?,completion_reason=?,updated_at=?
                   WHERE id=?""",
                (json.dumps(metrics, ensure_ascii=False, sort_keys=True), json.dumps(result["dimensions"], ensure_ascii=False, sort_keys=True),
                 result["score_total"], result["reward_amount"], result["cycle_penalty"], result["net_amount"], result["status"],
                 json.dumps(result["missing_fields"], ensure_ascii=False), completed_at, result.get("completion_reward_amount", 0),
                 int(bool(result.get("is_all_complete"))), result.get("completion_reason"), now, existing["id"]),
            )
            self._record_change(conn, user_id, "server_sleep_score_settlements", existing["id"], "upsert", {
                "id": existing["id"], "sleep_date": sleep_date, "score_total": result["score_total"],
                "report_completed_at": completed_at,
            })
            if result["status"] == "scored":
                self.reconcile_sleep_ledger_in_txn(conn, user_id, sleep_date)
            return {**saved, **result}
        result = calculate_sleep_score(metrics)
        now = self._now()
        settlement_id = f"sleep-score:{user_id}:{sleep_date}:{rule_version}"
        conn.execute(
            """INSERT INTO server_sleep_score_settlements
               (id,user_id,sleep_date,metrics_snapshot,score_breakdown,score_total,reward_amount,cycle_penalty,net_amount,
                settlement_status,missing_fields,rule_version,occurred_at,created_at,updated_at,report_completed_at,
                completion_reward_amount,is_all_complete,completion_reason)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (settlement_id, user_id, sleep_date, json.dumps(metrics, ensure_ascii=False, sort_keys=True),
             json.dumps(result["dimensions"], ensure_ascii=False, sort_keys=True), result["score_total"],
             result["reward_amount"], result["cycle_penalty"], result["net_amount"], result["status"],
             json.dumps(result["missing_fields"], ensure_ascii=False), rule_version, now, now, now,
             result.get("report_completed_at"), result.get("completion_reward_amount", 0),
             int(bool(result.get("is_all_complete"))), result.get("completion_reason")),
        )
        self._record_change(conn, user_id, "server_sleep_score_settlements", settlement_id, "upsert", {
            "id": settlement_id, "sleep_date": sleep_date, "score_total": result["score_total"],
            "reward_amount": result["reward_amount"], "cycle_penalty": result["cycle_penalty"],
            "completion_reward_amount": result.get("completion_reward_amount", 0),
            "is_all_complete": bool(result.get("is_all_complete")),
        })
        if result["status"] == "scored":
            self.reconcile_sleep_ledger_in_txn(conn, user_id, sleep_date)
        return {"id": settlement_id, "sleep_date": sleep_date, "ledger_sources": self._ledger_sources(sleep_date, rule_version), **result}

    def reconcile_bedtime_coin(self, user_id: int, sleep_date: str, deadline_reached: bool = False) -> dict:
        with self._transact() as conn:
            return self.reconcile_bedtime_coin_in_txn(conn, user_id, sleep_date, deadline_reached)

    def reconcile_bedtime_coin_in_txn(self, conn, user_id: int, sleep_date: str, deadline_reached: bool = False) -> dict:
        """用一条稳定流水调和入睡金币；补录只改结果，不重复累计。"""
        if sleep_date < BEDTIME_COIN_EFFECTIVE_DATE:
            return {}
        score_rule_version = rule_version_for_date(sleep_date)
        sleep = conn.execute(
            "SELECT * FROM server_huawei_sleep_data WHERE user_id=? AND date=?", (user_id, sleep_date),
        ).fetchone()
        settlement = conn.execute(
            "SELECT * FROM server_sleep_score_settlements WHERE user_id=? AND sleep_date=? AND rule_version=?",
            (user_id, sleep_date, score_rule_version),
        ).fetchone()
        if not settlement:
            metrics = dict(sleep or {})
            metrics["sleep_date"] = sleep_date
            self.settle_in_txn(conn, user_id, sleep_date, metrics)
            settlement = conn.execute(
                "SELECT * FROM server_sleep_score_settlements WHERE user_id=? AND sleep_date=? AND rule_version=?",
                (user_id, sleep_date, score_rule_version),
            ).fetchone()
        sleep_start = sleep["sleep_start"] if sleep else None
        no_sleep_penalty = _no_sleep_penalty_from_snapshot(score_rule_version, settlement["metrics_snapshot"])
        result = calculate_bedtime_coin(sleep_start)
        amount, now = float(result["amount"]), self._now()
        net_amount = sum(float(settlement[key] or 0) for key in (
            "reward_amount", "cycle_penalty", "completion_reward_amount", "diary_completion_reward_amount",
            "morning_diary_reward_amount", "evening_diary_reward_amount",
        )) + _deep_sleep_penalty_from_snapshot(score_rule_version, json.loads(settlement["score_breakdown"] or "{}")) + no_sleep_penalty + amount
        current = (
            settlement["bedtime_coin_status"], float(settlement["bedtime_coin_amount"] or 0),
            settlement["bedtime_coin_reason"], settlement["bedtime_coin_rule_version"],
            float(settlement["net_amount"] or 0),
        )
        expected = (result["status"], amount, result["reason"],
                    BEDTIME_COIN_RULE_VERSION if result["status"] == "settled" else None, net_amount)
        if current != expected:
            conn.execute(
                """UPDATE server_sleep_score_settlements SET bedtime_coin_status=?,bedtime_coin_amount=?,
                   bedtime_coin_reason=?,bedtime_coin_rule_version=?,net_amount=?,updated_at=? WHERE id=?""",
                (*expected, now, settlement["id"]),
            )
            self._record_change(conn, user_id, "server_sleep_score_settlements", settlement["id"], "upsert", {
                "id": settlement["id"], "bedtime_coin_status": result["status"], "bedtime_coin_amount": amount,
            })
        ledger_id = f"sleep-bedtime-adjustment:{user_id}:{sleep_date}:{BEDTIME_COIN_RULE_VERSION}"
        ledger = conn.execute(
            "SELECT * FROM server_reward_ledger WHERE user_id=? AND id=?", (user_id, ledger_id),
        ).fetchone()
        ledger_changed = False
        if amount and not ledger:
            self._wallet.append_ledger_in_txn(
                conn, user_id, amount, "sleep_bedtime_adjustment", ledger_id, result["reason"], sleep_date,
                ledger_id, now,
            )
            ledger_changed = True
        elif amount and ledger and (
            float(ledger["amount"] or 0) != amount or ledger["description"] != result["reason"]
            or ledger["target_date"] != sleep_date
        ):
            conn.execute(
                """UPDATE server_reward_ledger SET amount=?,source_type='sleep_bedtime_adjustment',source_id=?,
                   description=?,target_date=?,occurred_at=?,updated_at=? WHERE user_id=? AND id=?""",
                (amount, ledger_id, result["reason"], sleep_date, now, now, user_id, ledger_id),
            )
            self._record_change(conn, user_id, "server_reward_ledger", ledger_id, "upsert", {"id": ledger_id})
            ledger_changed = True
        elif not amount and ledger:
            conn.execute("DELETE FROM server_reward_ledger WHERE user_id=? AND id=?", (user_id, ledger_id))
            self._record_change(conn, user_id, "server_reward_ledger", ledger_id, "delete", {"id": ledger_id})
            ledger_changed = True
        if ledger_changed:
            wallet = self._wallet.rebuild_wallet_snapshot_in_txn(conn, user_id, self._now)
            self._record_change(conn, user_id, "server_user_wallets", user_id, "upsert", {
                "user_id": user_id, "balance": wallet["balance"], "updated_at": now,
            })
        row = conn.execute("SELECT * FROM server_sleep_score_settlements WHERE id=?", (settlement["id"],)).fetchone()
        return self._result_from_existing(row)

    def reconcile_diary_completion_in_txn(self, conn, user_id: int, sleep_date: str) -> dict:
        score_rule_version = rule_version_for_date(sleep_date)
        sleep = conn.execute(
            "SELECT * FROM server_huawei_sleep_data WHERE user_id=? AND date=?", (user_id, sleep_date),
        ).fetchone()
        settlement = conn.execute(
            "SELECT * FROM server_sleep_score_settlements WHERE user_id=? AND sleep_date=? AND rule_version=?",
            (user_id, sleep_date, score_rule_version),
        ).fetchone()
        if not settlement:
            metrics = dict(sleep or {})
            metrics["sleep_date"] = sleep_date
            self.settle_in_txn(conn, user_id, sleep_date, metrics)
            settlement = conn.execute(
                "SELECT * FROM server_sleep_score_settlements WHERE user_id=? AND sleep_date=? AND rule_version=?",
                (user_id, sleep_date, score_rule_version),
            ).fetchone()
        if sleep_date >= DIARY_REWARD_EFFECTIVE_DATE:
            return self._reconcile_independent_diaries_in_txn(conn, user_id, sleep_date, sleep, settlement)
        complete = bool(sleep and str(sleep["morning_diary"] or "").strip() and str(sleep["evening_diary"] or "").strip())
        amount, status = (10.0, "completed") if complete else (0.0, "pending")
        reason = "晨间与晚间日记均已完成" if complete else "晨间与晚间日记尚未全部完成"
        now = self._now()
        net_amount = (float(settlement["reward_amount"] or 0) + float(settlement["cycle_penalty"] or 0)
                      + _deep_sleep_penalty_from_snapshot(score_rule_version, json.loads(settlement["score_breakdown"] or "{}"))
                      + _no_sleep_penalty_from_snapshot(score_rule_version, settlement["metrics_snapshot"])
                      + float(settlement["completion_reward_amount"] or 0) + float(settlement["bedtime_coin_amount"] or 0) + amount)
        if (settlement["diary_completion_status"], float(settlement["diary_completion_reward_amount"] or 0), settlement["diary_completion_reason"]) != (status, amount, reason):
            conn.execute(
                """UPDATE server_sleep_score_settlements SET diary_completion_status=?,diary_completion_reward_amount=?,
                   diary_completion_reason=?,diary_completion_rule_version=?,net_amount=?,updated_at=? WHERE id=?""",
                (status, amount, reason, score_rule_version, net_amount, now, settlement["id"]),
            )
            self._record_change(conn, user_id, "server_sleep_score_settlements", settlement["id"], "upsert", {"id": settlement["id"], "diary_completion_status": status, "diary_completion_reward_amount": amount})
        ledger_id = f"sleep-diary-completion-reward:{user_id}:{sleep_date}:{score_rule_version}"
        ledger = conn.execute("SELECT id FROM server_reward_ledger WHERE user_id=? AND id=?", (user_id, ledger_id)).fetchone()
        changed = False
        if complete and not ledger:
            self._wallet.append_ledger_in_txn(conn, user_id, amount, "sleep_diary_completion_reward", self._ledger_sources(sleep_date)["diary_completion"], reason, sleep_date, ledger_id, now)
            changed = True
        elif not complete and ledger:
            conn.execute("DELETE FROM server_reward_ledger WHERE user_id=? AND id=?", (user_id, ledger_id))
            self._record_change(conn, user_id, "server_reward_ledger", ledger_id, "delete", {"id": ledger_id})
            changed = True
        if changed:
            wallet = self._wallet.rebuild_wallet_snapshot_in_txn(conn, user_id, self._now)
            self._record_change(conn, user_id, "server_user_wallets", user_id, "upsert", {"user_id": user_id, "balance": wallet["balance"], "updated_at": now})
        return self._result_from_existing(conn.execute("SELECT * FROM server_sleep_score_settlements WHERE id=?", (settlement["id"],)).fetchone())

    def _reconcile_independent_diaries_in_txn(self, conn, user_id, sleep_date, sleep, settlement) -> dict:
        now, ledger_changed, states = self._now(), False, {}
        for diary_type, label in (("morning", "晨间"), ("evening", "晚间")):
            completed = bool(sleep and str(sleep[f"{diary_type}_diary"] or "").strip())
            amount = DIARY_REWARD_AMOUNT if completed else 0.0
            status, reason = ("completed", f"{label}日记已完成") if completed else ("pending", f"{label}日记尚未完成")
            ledger_id = f"sleep-{diary_type}-diary-reward:{user_id}:{sleep_date}:{DIARY_REWARD_VERSION}"
            row = conn.execute("SELECT * FROM server_reward_ledger WHERE user_id=? AND id=?", (user_id, ledger_id)).fetchone()
            if completed and not row:
                self._wallet.append_ledger_in_txn(conn, user_id, amount, f"sleep_{diary_type}_diary_reward", ledger_id, f"{label}日记奖励", sleep_date, ledger_id, now)
                ledger_changed = True
            elif not completed and row:
                conn.execute("DELETE FROM server_reward_ledger WHERE user_id=? AND id=?", (user_id, ledger_id))
                self._record_change(conn, user_id, "server_reward_ledger", ledger_id, "delete", {"id": ledger_id})
                ledger_changed = True
            states[diary_type] = (status, amount, reason, DIARY_REWARD_VERSION)
        legacy = conn.execute("SELECT id FROM server_reward_ledger WHERE user_id=? AND target_date=? AND source_type='sleep_diary_completion_reward'", (user_id, sleep_date)).fetchall()
        for row in legacy:
            conn.execute("DELETE FROM server_reward_ledger WHERE user_id=? AND id=?", (user_id, row["id"]))
            self._record_change(conn, user_id, "server_reward_ledger", row["id"], "delete", {"id": row["id"]})
            ledger_changed = True
        morning, evening = states["morning"], states["evening"]
        net_amount = sum((float(settlement["reward_amount"] or 0), float(settlement["cycle_penalty"] or 0),
                          _deep_sleep_penalty_from_snapshot(settlement["rule_version"], json.loads(settlement["score_breakdown"] or "{}")),
                          _no_sleep_penalty_from_snapshot(settlement["rule_version"], settlement["metrics_snapshot"]),
                          float(settlement["completion_reward_amount"] or 0), float(settlement["bedtime_coin_amount"] or 0), morning[1], evening[1]))
        current = tuple(settlement[key] for key in (
            "morning_diary_reward_status", "morning_diary_reward_amount", "morning_diary_reward_reason", "morning_diary_reward_rule_version",
            "evening_diary_reward_status", "evening_diary_reward_amount", "evening_diary_reward_reason", "evening_diary_reward_rule_version",
            "diary_completion_status", "diary_completion_reward_amount", "diary_completion_reason", "diary_completion_rule_version", "net_amount"))
        expected = (*morning, *evening, "pending", 0.0, "已改为晨间与晚间独立奖励", DIARY_REWARD_VERSION, net_amount)
        if current != expected:
            conn.execute("""UPDATE server_sleep_score_settlements SET
                morning_diary_reward_status=?,morning_diary_reward_amount=?,morning_diary_reward_reason=?,morning_diary_reward_rule_version=?,
                evening_diary_reward_status=?,evening_diary_reward_amount=?,evening_diary_reward_reason=?,evening_diary_reward_rule_version=?,
                diary_completion_status=?,diary_completion_reward_amount=?,diary_completion_reason=?,diary_completion_rule_version=?,net_amount=?,updated_at=? WHERE id=?""",
                (*expected, now, settlement["id"]))
            self._record_change(conn, user_id, "server_sleep_score_settlements", settlement["id"], "upsert", {"id": settlement["id"], "morning_diary_reward_status": morning[0], "evening_diary_reward_status": evening[0]})
        if ledger_changed:
            wallet = self._wallet.rebuild_wallet_snapshot_in_txn(conn, user_id, self._now)
            self._record_change(conn, user_id, "server_user_wallets", user_id, "upsert", {"user_id": user_id, "balance": wallet["balance"], "updated_at": now})
        return self._result_from_existing(conn.execute("SELECT * FROM server_sleep_score_settlements WHERE id=?", (settlement["id"],)).fetchone())

    def migrate_effective_date_diary_rewards(self) -> int:
        """幂等调和生效日后的既有日记；历史日期不触碰。"""
        with self._transact() as conn:
            rows = conn.execute("SELECT user_id,date FROM server_huawei_sleep_data WHERE date>=? ORDER BY user_id,date", (DIARY_REWARD_EFFECTIVE_DATE,)).fetchall()
            for row in rows:
                self.reconcile_diary_completion_in_txn(conn, int(row["user_id"]), str(row["date"])[:10])
            return len(rows)

    def audit_bedtime_coins(self) -> dict:
        """仅审计可由结算快照确认是旧 noon 规则的流水。"""
        with self._transact() as conn:
            rows = conn.execute(
                """SELECT ledger.user_id,COUNT(*) AS ledger_count,COALESCE(SUM(ledger.amount),0) AS amount
                   FROM server_reward_ledger AS ledger
                   JOIN server_sleep_score_settlements AS settlement
                     ON settlement.user_id=ledger.user_id AND settlement.sleep_date=ledger.target_date
                   WHERE ledger.source_type='sleep_bedtime_adjustment' AND ledger.id LIKE ?
                     AND settlement.bedtime_coin_reason=?
                   GROUP BY ledger.user_id ORDER BY ledger.user_id""",
                ("sleep-bedtime-adjustment:%", "截至北京时间12:00仍无有效睡眠记录"),
            ).fetchall()
            return {"rule_version": BEDTIME_COIN_RULE_VERSION, "users": [dict(row) for row in rows]}

    def rollback_bedtime_coins(self) -> dict:
        """只撤销可由结算快照确认的旧 noon 规则流水。"""
        with self._transact() as conn:
            rows = conn.execute(
                """SELECT ledger.id,ledger.user_id FROM server_reward_ledger AS ledger
                   JOIN server_sleep_score_settlements AS settlement
                     ON settlement.user_id=ledger.user_id AND settlement.sleep_date=ledger.target_date
                   WHERE ledger.source_type='sleep_bedtime_adjustment' AND ledger.id LIKE ?
                     AND settlement.bedtime_coin_reason=?""",
                ("sleep-bedtime-adjustment:%", "截至北京时间12:00仍无有效睡眠记录"),
            ).fetchall()
            affected = sorted({int(row["user_id"]) for row in rows})
            for row in rows:
                conn.execute("DELETE FROM server_reward_ledger WHERE user_id=? AND id=?", (row["user_id"], row["id"]))
                self._record_change(conn, row["user_id"], "server_reward_ledger", row["id"], "delete", {"id": row["id"]})
            settlements = conn.execute(
                """SELECT id,user_id,bedtime_coin_amount FROM server_sleep_score_settlements
                   WHERE bedtime_coin_reason=?""",
                ("截至北京时间12:00仍无有效睡眠记录",),
            ).fetchall()
            for row in settlements:
                conn.execute(
                    """UPDATE server_sleep_score_settlements SET net_amount=net_amount-bedtime_coin_amount,
                       bedtime_coin_status='pending',bedtime_coin_amount=0,bedtime_coin_reason=NULL,
                       bedtime_coin_rule_version=NULL,updated_at=? WHERE id=?""", (self._now(), row["id"]),
                )
                self._record_change(conn, row["user_id"], "server_sleep_score_settlements", row["id"], "upsert", {"id": row["id"], "bedtime_coin_status": "pending"})
                if int(row["user_id"]) not in affected:
                    affected.append(int(row["user_id"]))
            for user_id in affected:
                wallet = self._wallet.rebuild_wallet_snapshot_in_txn(conn, user_id, self._now)
                self._record_change(conn, user_id, "server_user_wallets", user_id, "upsert", {"user_id": user_id, "balance": wallet["balance"]})
            return {"rule_version": BEDTIME_COIN_RULE_VERSION, "deleted_ledgers": len(rows), "affected_users": len(set(affected))}

    def audit_unreported_scores_in_txn(self, conn):
        return conn.execute(
            """SELECT s.user_id,s.sleep_date,s.id FROM server_sleep_score_settlements s
               LEFT JOIN server_huawei_sleep_data d ON d.user_id=s.user_id AND d.date=s.sleep_date
               WHERE s.settlement_status='scored' AND
                 (COALESCE(d.report_status,0)<1 OR (TRIM(COALESCE(d.analysis_report,''))='' AND TRIM(COALESCE(d.analysis_html,''))=''))
               ORDER BY s.user_id,s.sleep_date"""
        ).fetchall()

    def reconcile_unreported_scores(self) -> dict:
        """撤销无可见报告的分数事实；日记奖励与原始睡眠数据保持不动。"""
        with self._transact() as conn:
            rows = self.audit_unreported_scores_in_txn(conn)
            affected_users = set()
            for row in rows:
                affected_users.add(int(row["user_id"])); now = self._now()
                settlement = conn.execute("SELECT * FROM server_sleep_score_settlements WHERE id=?", (row["id"],)).fetchone()
                diary_total = sum(float(settlement[key] or 0) for key in (
                    "diary_completion_reward_amount", "morning_diary_reward_amount", "evening_diary_reward_amount",
                    "bedtime_coin_amount"))
                conn.execute("""UPDATE server_sleep_score_settlements SET score_breakdown='{}',score_total=0,reward_amount=0,
                    cycle_penalty=0,net_amount=?,settlement_status='not_scored',missing_fields='[\"report\"]',
                    report_completed_at=NULL,completion_reward_amount=0,is_all_complete=0,completion_reason='等待可见睡眠报告',updated_at=? WHERE id=?""",
                    (diary_total, now, row["id"]))
                self._record_change(conn, row["user_id"], "server_sleep_score_settlements", row["id"], "upsert", {"id": row["id"], "settlement_status": "not_scored"})
                ledgers = conn.execute("""SELECT id FROM server_reward_ledger WHERE user_id=? AND target_date=?
                    AND source_type IN ('sleep_settlement_reward','sleep_cycle_penalty','sleep_deep_penalty','sleep_no_sleep_penalty','sleep_completion_reward')""", (row["user_id"], row["sleep_date"])).fetchall()
                for ledger in ledgers:
                    conn.execute("DELETE FROM server_reward_ledger WHERE user_id=? AND id=?", (row["user_id"], ledger["id"]))
                    self._record_change(conn, row["user_id"], "server_reward_ledger", ledger["id"], "delete", {"id": ledger["id"]})
            for user_id in affected_users:
                wallet = self._wallet.rebuild_wallet_snapshot_in_txn(conn, user_id, self._now)
                self._record_change(conn, user_id, "server_user_wallets", user_id, "upsert", {"user_id": user_id, "balance": wallet["balance"]})
            return {"candidates": len(rows), "users": len(affected_users)}

    @staticmethod
    def _ledger_sources(sleep_date: str, rule_version: str = RULE_VERSION) -> dict:
        prefix = f"sleep-score:{sleep_date}:{rule_version}"
        return {
            "reward": f"{prefix}:reward", "cycle_penalty": f"{prefix}:cycle-penalty",
            "deep_sleep_penalty": f"{prefix}:deep-sleep-penalty", "completion": f"{prefix}:completion",
            "no_sleep_penalty": f"{prefix}:no-main-sleep-penalty",
            "diary_completion": f"{prefix}:diary-completion",
        }

    def reconcile_sleep_ledger_in_txn(self, conn, user_id: int, sleep_date: str) -> bool:
        """以当前权威结算调和单日睡眠金币，不让历史版本叠加进钱包。"""
        settlements = conn.execute(
            "SELECT * FROM server_sleep_score_settlements WHERE user_id=? AND sleep_date=?",
            (user_id, sleep_date),
        ).fetchall()
        selected = select_authoritative_sleep_settlements(settlements).get(sleep_date)
        if not selected:
            return False
        version = str(selected.get("rule_version") or rule_version_for_date(sleep_date))
        sources = self._ledger_sources(sleep_date, version)
        deep_sleep_penalty = _deep_sleep_penalty_from_snapshot(version, selected.get("score_breakdown"))
        no_sleep_penalty = _no_sleep_penalty_from_snapshot(version, selected.get("metrics_snapshot"))
        now = self._now()
        expected = {
            f"sleep-reward:{user_id}:{sleep_date}:{version}": (
                float(selected.get("reward_amount") or 0), "sleep_settlement_reward", sources["reward"],
                f"睡眠评分奖励：{int(selected.get('score_total') or 0)}/100",
            ),
            f"sleep-cycle-penalty:{user_id}:{sleep_date}:{version}": (
                float(selected.get("cycle_penalty") or 0), "sleep_cycle_penalty", sources["cycle_penalty"],
                "睡眠周期不足（<4.0）" if float(selected.get("cycle_penalty") or 0) else "睡眠周期结果：无处罚",
            ),
            f"sleep-completion-reward:{user_id}:{sleep_date}:{version}": (
                float(selected.get("completion_reward_amount") or 0), "sleep_completion_reward", sources["completion"],
                (
                    "睡眠指标全完成奖励：八项均满分"
                    if version == V4_RULE_VERSION
                    else "睡眠指标全完成奖励：十项均满分"
                ) if bool(selected.get("is_all_complete")) else "睡眠指标全完成奖励：未获得",
            ),
        }
        if version == V4_RULE_VERSION:
            expected[f"sleep-deep-penalty:{user_id}:{sleep_date}:{version}"] = (
                deep_sleep_penalty, "sleep_deep_penalty", sources["deep_sleep_penalty"],
                "深睡时长不足（<60分钟）" if deep_sleep_penalty else "深睡时长结果：无处罚",
            )
        if no_sleep_penalty:
            expected[f"sleep-no-sleep-penalty:{user_id}:{sleep_date}:{version}"] = (
                no_sleep_penalty, "sleep_no_sleep_penalty", sources["no_sleep_penalty"], "无睡眠，严重警告！",
            )
        existing = conn.execute(
            """SELECT * FROM server_reward_ledger WHERE user_id=? AND target_date=?
               AND source_type IN ('sleep_settlement_reward','sleep_cycle_penalty','sleep_deep_penalty','sleep_no_sleep_penalty','sleep_completion_reward')""",
            (user_id, sleep_date),
        ).fetchall()
        changed = False
        for row in existing:
            if row["id"] not in expected:
                conn.execute("DELETE FROM server_reward_ledger WHERE user_id=? AND id=?", (user_id, row["id"]))
                self._record_change(conn, user_id, "server_reward_ledger", row["id"], "delete", {"id": row["id"]})
                changed = True
        for ledger_id, (amount, source_type, source_id, description) in expected.items():
            row = next((item for item in existing if item["id"] == ledger_id), None)
            if not row:
                self._wallet.append_ledger_in_txn(conn, user_id, amount, source_type, source_id, description, sleep_date, ledger_id, now)
                changed = True
            elif (float(row["amount"]) != amount or row["source_type"] != source_type or row["source_id"] != source_id
                  or row["description"] != description or row["target_date"] != sleep_date):
                conn.execute(
                    """UPDATE server_reward_ledger SET amount=?,source_type=?,source_id=?,description=?,target_date=?,
                       occurred_at=?,updated_at=? WHERE user_id=? AND id=?""",
                    (amount, source_type, source_id, description, sleep_date,
                     selected.get("occurred_at") or now, now, user_id, ledger_id),
                )
                self._record_change(conn, user_id, "server_reward_ledger", ledger_id, "upsert", {"id": ledger_id})
                changed = True
        if changed:
            wallet = self._wallet.rebuild_wallet_snapshot_in_txn(conn, user_id, self._now)
            self._record_change(conn, user_id, "server_user_wallets", user_id, "upsert", {
                "user_id": user_id, "balance": wallet["balance"], "updated_at": now,
            })
        return changed

    def _result_from_existing(self, row) -> dict:
        """将 SQLite 快照还原为与首次结算相同的只读返回模型。"""
        result = {
            "id": row["id"],
            "sleep_date": row["sleep_date"],
            "status": row["settlement_status"],
            "missing_fields": json.loads(row["missing_fields"] or "[]"),
            "dimensions": json.loads(row["score_breakdown"] or "{}"),
            "score_total": row["score_total"],
            "reward_amount": row["reward_amount"],
            "cycle_penalty": row["cycle_penalty"],
            "deep_sleep_penalty": _deep_sleep_penalty_from_snapshot(row["rule_version"], json.loads(row["score_breakdown"] or "{}")),
            "no_sleep_penalty": _no_sleep_penalty_from_snapshot(row["rule_version"], row["metrics_snapshot"]),
            "net_amount": row["net_amount"],
            "report_completed_at": row["report_completed_at"],
            "completion_reward_amount": row["completion_reward_amount"],
            "is_all_complete": bool(row["is_all_complete"]),
            "completion_reason": row["completion_reason"],
            "diary_completion_status": row["diary_completion_status"],
            "diary_completion_reward_amount": row["diary_completion_reward_amount"],
            "diary_completion_reason": row["diary_completion_reason"],
            "diary_completion_rule_version": row["diary_completion_rule_version"],
            "morning_diary_reward_status": row["morning_diary_reward_status"],
            "morning_diary_reward_amount": row["morning_diary_reward_amount"],
            "morning_diary_reward_reason": row["morning_diary_reward_reason"],
            "morning_diary_reward_rule_version": row["morning_diary_reward_rule_version"],
            "evening_diary_reward_status": row["evening_diary_reward_status"],
            "evening_diary_reward_amount": row["evening_diary_reward_amount"],
            "evening_diary_reward_reason": row["evening_diary_reward_reason"],
            "evening_diary_reward_rule_version": row["evening_diary_reward_rule_version"],
            "bedtime_coin_status": row["bedtime_coin_status"],
            "bedtime_coin_amount": row["bedtime_coin_amount"],
            "bedtime_coin_reason": row["bedtime_coin_reason"],
            "bedtime_coin_rule_version": row["bedtime_coin_rule_version"],
            "rule_version": row["rule_version"],
            "ledger_sources": self._ledger_sources(row["sleep_date"], row["rule_version"]),
        }
        return result
