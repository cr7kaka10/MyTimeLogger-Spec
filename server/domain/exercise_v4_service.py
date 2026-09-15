from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json


TZ = timezone(timedelta(hours=8))
PLAN_VERSION = "v4"
RULE_VERSION = "exercise-score-v4"
DIET_RULES = ("no_snacks", "no_sugary_drinks", "no_refined_staples")
SCOPES = {"training", "diet", "body"}


def _dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    return parsed.replace(tzinfo=TZ) if parsed.tzinfo is None else parsed.astimezone(TZ)


def _deadline(date: str, hour: int = 0) -> datetime:
    base = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=TZ)
    return base.replace(hour=hour) if hour else base + timedelta(days=1)


def _now_text(now: datetime) -> str:
    return now.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S")


class ExerciseV4Service:
    def __init__(self, wallet, record_change):
        self.wallet = wallet
        self.record_change = record_change

    def _change(self, conn, user_id, table, record_id, operation="upsert"):
        self.record_change(conn, user_id, table, record_id, operation)

    def _discard_invalid_diet_facts(self, conn, user_id: int, date: str) -> None:
        placeholders = ",".join("?" for _ in DIET_RULES)
        rows = conn.execute(f"""SELECT id FROM server_exercise_diet_checkins
            WHERE user_id=? AND date=? AND plan_version=? AND rule_key NOT IN ({placeholders})""",
            (user_id, date, PLAN_VERSION, *DIET_RULES)).fetchall()
        for row in rows:
            conn.execute("DELETE FROM server_exercise_diet_checkins WHERE id=? AND user_id=?", (row["id"], user_id))
            self._change(conn, user_id, "server_exercise_diet_checkins", row["id"], "delete")

    def ensure_diet_rows(self, conn, user_id: int, date: str, now: datetime) -> None:
        self._discard_invalid_diet_facts(conn, user_id, date)
        stamp, cutoff = _now_text(now), _deadline(date).strftime("%Y-%m-%d %H:%M:%S")
        for rule_key in DIET_RULES:
            row_id = f"diet:{user_id}:{date}:{PLAN_VERSION}:{rule_key}"
            inserted = conn.execute("""INSERT OR IGNORE INTO server_exercise_diet_checkins
                (id,user_id,date,plan_version,rule_key,status,deadline_at,created_at,updated_at)
                VALUES (?,?,?,?,?,'pending',?,?,?)""",
                (row_id, user_id, date, PLAN_VERSION, rule_key, cutoff, stamp, stamp))
            if inserted.rowcount:
                self._change(conn, user_id, "server_exercise_diet_checkins", row_id)

    def set_diet(self, conn, user_id: int, date: str, rule_key: str, status: str | bool,
                 occurred_at: str | None, now: datetime) -> dict:
        if rule_key not in DIET_RULES:
            raise ValueError("unknown_diet_rule")
        if isinstance(status, bool):
            status = "completed" if status else "pending"
        if status not in {"pending", "completed", "failed"}:
            raise ValueError("invalid_diet_status")
        self.ensure_diet_rows(conn, user_id, date, now)
        event_time = _dt(occurred_at) if occurred_at else now.astimezone(TZ)
        if event_time >= _deadline(date):
            raise ValueError("diet_deadline_passed")
        row = conn.execute("""SELECT * FROM server_exercise_diet_checkins
            WHERE user_id=? AND date=? AND plan_version=? AND rule_key=?""",
            (user_id, date, PLAN_VERSION, rule_key)).fetchone()
        if status == "pending" and now.astimezone(TZ) >= _deadline(date):
            raise ValueError("diet_deadline_passed")
        stamp = _now_text(now)
        occurred_text = event_time.strftime("%Y-%m-%d %H:%M:%S") if status != "pending" else None
        failure_reason = "user_marked_failed" if status == "failed" else None
        changed = (row["status"], row["occurred_at"], row["failure_reason"], row["penalty_source_id"]) != (
            status, occurred_text, failure_reason, None,
        )
        if changed:
            conn.execute("""UPDATE server_exercise_diet_checkins SET status=?,occurred_at=?,
                failure_reason=?,penalty_source_id=NULL,updated_at=? WHERE id=? AND user_id=?""",
                (status, occurred_text, failure_reason, stamp, row["id"], user_id))
        if status in {"completed", "failed"}:
            self._remove_diet_penalty(conn, user_id, date, rule_key)
        if changed:
            self._change(conn, user_id, "server_exercise_diet_checkins", row["id"])
        return self.settle(conn, user_id, date, now)

    def close_diet(self, conn, user_id: int, date: str, now: datetime) -> int:
        if now.astimezone(TZ) < _deadline(date):
            return 0
        self.ensure_diet_rows(conn, user_id, date, now)
        changed, stamp = 0, _now_text(now)
        rows = conn.execute("""SELECT * FROM server_exercise_diet_checkins
            WHERE user_id=? AND date=? AND plan_version=?""", (user_id, date, PLAN_VERSION)).fetchall()
        for row in rows:
            if row["status"] != "pending":
                continue
            source = f"exercise-diet-penalty:{user_id}:{date}:{PLAN_VERSION}:{row['rule_key']}"
            row_changed = (row["status"], row["failure_reason"], row["penalty_source_id"]) != (
                "failed", "not_completed_before_midnight", source,
            )
            if row_changed:
                conn.execute("""UPDATE server_exercise_diet_checkins SET status='failed',failure_reason='not_completed_before_midnight',
                    penalty_source_id=?,updated_at=? WHERE id=? AND user_id=?""", (source, stamp, row["id"], user_id))
            ledger_missing = not conn.execute("SELECT 1 FROM server_reward_ledger WHERE user_id=? AND id=?", (user_id, source)).fetchone()
            if ledger_missing:
                self.wallet.append_ledger_in_txn(conn, user_id, -20, "exercise_diet_penalty", source,
                    "饮食必做项逾期未完成", date, source, stamp)
                self._change(conn, user_id, "server_reward_ledger", source)
            if row_changed:
                self._change(conn, user_id, "server_exercise_diet_checkins", row["id"])
            changed += int(row_changed or ledger_missing)
        if changed:
            self.wallet.rebuild_wallet_snapshot_in_txn(conn, user_id, lambda: stamp)
            self._change(conn, user_id, "server_user_wallets", str(user_id))
            self.settle(conn, user_id, date, now)
        return changed

    def settle_body_deadline(self, conn, user_id: int, date: str, now: datetime) -> dict | None:
        if now.astimezone(TZ) < _deadline(date, 9):
            return None
        existing_metric = conn.execute("""SELECT status FROM server_exercise_deadline_facts
            WHERE user_id=? AND date=? AND plan_version=? AND fact_type='body_metrics'""",
            (user_id, date, PLAN_VERSION)).fetchone()
        log = conn.execute("""SELECT weight,body_fat_rate FROM server_exercise_daily_logs
            WHERE user_id=? AND date=? AND plan_version=? AND exercise_type='daily'""",
            (user_id, date, PLAN_VERSION)).fetchone()
        field_statuses = {
            "body_weight": "complete" if log and log["weight"] is not None else "failed",
            "body_fat_rate": "complete" if log and log["body_fat_rate"] is not None else "failed",
        }
        if existing_metric:
            field_statuses = {key: "complete" if existing_metric["status"] == "complete" else "failed" for key in field_statuses}
        complete = all(status == "complete" for status in field_statuses.values())
        fact_id = f"body-deadline:{user_id}:{date}:{PLAN_VERSION}"
        source = f"body-metric-deadline-penalty:{user_id}:{date}"
        stamp = _now_text(now)
        field_inserted = 0
        for fact_type, status in field_statuses.items():
            inserted_field = conn.execute("""INSERT INTO server_exercise_deadline_facts
                (id,user_id,date,plan_version,fact_type,status,deadline_at,reason,penalty_source_id,penalty_amount,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,date,plan_version,fact_type) DO NOTHING""",
                (f"body-deadline:{user_id}:{date}:{PLAN_VERSION}:{fact_type}", user_id, date, PLAN_VERSION, fact_type, status,
                 _deadline(date, 9).strftime("%Y-%m-%d %H:%M:%S"), f"{fact_type}_{status}_before_09:00", None, 0, stamp, stamp))
            if inserted_field.rowcount:
                field_inserted += 1
                self._change(conn, user_id, "server_exercise_deadline_facts", f"body-deadline:{user_id}:{date}:{PLAN_VERSION}:{fact_type}")
        inserted = conn.execute("""INSERT INTO server_exercise_deadline_facts
            (id,user_id,date,plan_version,fact_type,status,deadline_at,reason,penalty_source_id,penalty_amount,created_at,updated_at)
            VALUES (?,?,?,?, 'body_metrics',?,?,?,?,?,?,?)
            ON CONFLICT(user_id,date,plan_version,fact_type) DO NOTHING""",
            (fact_id, user_id, date, PLAN_VERSION, "complete" if complete else "failed",
             _deadline(date, 9).strftime("%Y-%m-%d %H:%M:%S"), "complete_before_09:00" if complete else "body_metrics_missing_at_09:00",
             None if complete else source, 0 if complete else -50, stamp, stamp))
        fact = conn.execute("SELECT * FROM server_exercise_deadline_facts WHERE user_id=? AND date=? AND plan_version=? AND fact_type='body_metrics'",
            (user_id, date, PLAN_VERSION)).fetchone()
        ledger_missing = fact["status"] == "failed" and not conn.execute("SELECT 1 FROM server_reward_ledger WHERE user_id=? AND id=?", (user_id, source)).fetchone()
        if ledger_missing:
            self.wallet.append_ledger_in_txn(conn, user_id, -50, "body_metric_deadline_penalty",
                f"body-metric-deadline:{date}", "体重体脂逾期未填写（09:00）", date, source, stamp)
            self._change(conn, user_id, "server_reward_ledger", source)
            self.wallet.rebuild_wallet_snapshot_in_txn(conn, user_id, lambda: stamp)
            self._change(conn, user_id, "server_user_wallets", str(user_id))
        if inserted.rowcount:
            self._change(conn, user_id, "server_exercise_deadline_facts", fact["id"])
        return {**dict(fact), "_changed": bool(field_inserted or inserted.rowcount or ledger_missing)}

    def settle(self, conn, user_id: int, date: str, now: datetime) -> dict:
        self.ensure_diet_rows(conn, user_id, date, now)
        day = ("周一", "周二", "周三", "周四", "周五", "六", "日")[datetime.strptime(date, "%Y-%m-%d").weekday()]
        checkins = {str(row["item_key"]): int(row["status"] or 0) for row in conn.execute(
            "SELECT item_key,status FROM server_exercise_checkins WHERE user_id=? AND date=? AND plan_version=?", (user_id, date, PLAN_VERSION))}
        facts = []
        for item in conn.execute("""SELECT * FROM server_exercise_plan_items WHERE user_id=? AND plan_version=?
            AND day_key=? AND variant='gym' AND is_active=1 ORDER BY sort_order""", (user_id, PLAN_VERSION, day)):
            tags = json.loads(item["tags_json"] or "{}")
            maximum = float(tags.get("scorePoints") or 0)
            key = f"ex-{date}-g-{item['sort_order']}"
            facts.append((key, "training", maximum if checkins.get(key) == 1 else 0, maximum, item["name"]))
        placeholders = ",".join("?" for _ in DIET_RULES)
        for row in conn.execute(f"""SELECT rule_key,status FROM server_exercise_diet_checkins
            WHERE user_id=? AND date=? AND plan_version=? AND rule_key IN ({placeholders})""",
                                (user_id, date, PLAN_VERSION, *DIET_RULES)):
            facts.append((f"diet:{row['rule_key']}", "diet", 5 if row["status"] == "completed" else 0, 5, row["status"]))
        log = conn.execute("""SELECT * FROM server_exercise_daily_logs WHERE user_id=? AND date=?
            AND plan_version=? AND exercise_type='daily'""", (user_id, date, PLAN_VERSION)).fetchone()
        after_body_deadline = now.astimezone(TZ) >= _deadline(date, 9)
        eligibility = {row["fact_type"]: row["status"] for row in conn.execute("""SELECT fact_type,status
            FROM server_exercise_deadline_facts WHERE user_id=? AND date=? AND plan_version=?
            AND fact_type IN ('body_weight','body_fat_rate')""", (user_id, date, PLAN_VERSION))}
        def body_points(field: str, value) -> tuple[int, str]:
            eligible = eligibility.get(field)
            if after_body_deadline:
                return (5 if eligible == "complete" else 0, "截止前确认" if eligible == "complete" else "截止时缺失")
            return (5 if value is not None else 0, "有效身体记录")
        weight_points, weight_reason = body_points("body_weight", log["weight"] if log else None)
        fat_points, fat_reason = body_points("body_fat_rate", log["body_fat_rate"] if log else None)
        facts.extend((("body:weight", "body", weight_points, 5, weight_reason),
                      ("body:body_fat_rate", "body", fat_points, 5, fat_reason)))
        stamp, categories = _now_text(now), {scope: {"s": 0.0, "m": 0.0} for scope in SCOPES}
        for key, scope, earned, maximum, reason in facts:
            if scope not in SCOPES:
                continue
            score_id = f"exercise-item-score:{user_id}:{date}:{PLAN_VERSION}:{key}"
            existing = conn.execute("""SELECT earned_points,max_points,score_rule_version,score_reason,score_scope,status
                FROM server_exercise_item_scores WHERE user_id=? AND date=? AND plan_version=? AND item_key=?""",
                (user_id, date, PLAN_VERSION, key)).fetchone()
            desired = (float(earned), float(maximum), RULE_VERSION, str(reason), scope, "active")
            current = None if not existing else (float(existing["earned_points"]), float(existing["max_points"]),
                existing["score_rule_version"], existing["score_reason"], existing["score_scope"], existing["status"])
            if current != desired:
                conn.execute("""INSERT INTO server_exercise_item_scores
                (id,user_id,date,plan_version,item_key,earned_points,max_points,score_rule_version,score_reason,score_scope,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,'active',?,?) ON CONFLICT(user_id,date,plan_version,item_key) DO UPDATE SET
                earned_points=excluded.earned_points,max_points=excluded.max_points,score_rule_version=excluded.score_rule_version,
                score_reason=excluded.score_reason,score_scope=excluded.score_scope,status='active',updated_at=excluded.updated_at""",
                    (score_id, user_id, date, PLAN_VERSION, key, earned, maximum, RULE_VERSION, reason, scope, stamp, stamp))
                self._change(conn, user_id, "server_exercise_item_scores", score_id)
            categories[scope]["s"] += earned; categories[scope]["m"] += maximum
        ignored = conn.execute("""SELECT id FROM server_exercise_item_scores WHERE user_id=? AND date=? AND plan_version=?
            AND item_key LIKE 'sc-%' AND (earned_points!=0 OR max_points!=0 OR status!='ignored' OR score_scope!='schedule')""",
            (user_id, date, PLAN_VERSION)).fetchall()
        if ignored:
            conn.execute("""UPDATE server_exercise_item_scores SET earned_points=0,max_points=0,status='ignored',score_scope='schedule',updated_at=?
                WHERE user_id=? AND date=? AND plan_version=? AND item_key LIKE 'sc-%'""", (stamp, user_id, date, PLAN_VERSION))
            for row in ignored:
                self._change(conn, user_id, "server_exercise_item_scores", row["id"])
        total = round(sum(value["s"] for value in categories.values()), 2)
        complete = all(categories[s]["m"] > 0 and categories[s]["s"] == categories[s]["m"] for s in SCOPES)
        snapshot = {"total": total, "cats": {"运动训练": categories["training"], "饮食约束": categories["diet"], "身体记录": categories["body"]}, "plan_version": PLAN_VERSION}
        settlement_id = f"exercise-settlement:{user_id}:{PLAN_VERSION}:{date}"
        settlement_values = (json.dumps(snapshot, ensure_ascii=False, sort_keys=True), total,
            json.dumps(snapshot["cats"], ensure_ascii=False, sort_keys=True), sum(1 for _,_,e,m,_ in facts if m > 0 and e == m),
            sum(1 for _,_,_,m,_ in facts if m > 0), RULE_VERSION, int(complete), 100 if complete else 0,
            "三个V4评分域均满分" if complete else "训练、饮食或身体记录尚未满分")
        previous = conn.execute("""SELECT score_snapshot,score_total,category_scores,completed_items,total_items,rule_version,
            is_all_complete,completion_reward_amount,completion_reason FROM server_exercise_settlements
            WHERE user_id=? AND business_date=? AND plan_version=?""", (user_id, date, PLAN_VERSION)).fetchone()
        previous_values = None if not previous else (previous["score_snapshot"], float(previous["score_total"]), previous["category_scores"],
            int(previous["completed_items"]), int(previous["total_items"]), previous["rule_version"], int(previous["is_all_complete"]),
            int(previous["completion_reward_amount"]), previous["completion_reason"])
        if previous_values != settlement_values:
            conn.execute("""INSERT INTO server_exercise_settlements
            (id,user_id,business_date,plan_version,score_snapshot,score_total,category_scores,completed_items,total_items,
             settlement_status,reason_code,rule_version,coin_amount,is_all_complete,completion_reward_amount,completion_reason,occurred_at,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,'active','v4_live',?,0,?,?,?, ?,?,?)
            ON CONFLICT(user_id,business_date,plan_version) DO UPDATE SET score_snapshot=excluded.score_snapshot,
             score_total=excluded.score_total,category_scores=excluded.category_scores,completed_items=excluded.completed_items,
             total_items=excluded.total_items,is_all_complete=excluded.is_all_complete,completion_reward_amount=excluded.completion_reward_amount,
             completion_reason=excluded.completion_reason,updated_at=excluded.updated_at""",
                (settlement_id, user_id, date, PLAN_VERSION, *settlement_values[:5], settlement_values[5], settlement_values[6],
                 settlement_values[7], settlement_values[8], stamp, stamp, stamp))
            self._change(conn, user_id, "server_exercise_settlements", settlement_id)
        self._reconcile_completion_reward(conn, user_id, date, complete, stamp)
        return snapshot

    def _reconcile_completion_reward(self, conn, user_id: int, date: str, complete: bool, stamp: str) -> None:
        ledger_id = f"exercise-completion-reward:{user_id}:{PLAN_VERSION}:{date}"
        existing = conn.execute("SELECT 1 FROM server_reward_ledger WHERE user_id=? AND id=?", (user_id, ledger_id)).fetchone()
        if complete and not existing:
            self.wallet.append_ledger_in_txn(conn, user_id, 100, "exercise_completion_reward",
                f"exercise-completion:{PLAN_VERSION}:{date}", "V4运动指标全完成奖励", date, ledger_id, stamp)
            self._change(conn, user_id, "server_reward_ledger", ledger_id)
            self.wallet.rebuild_wallet_snapshot_in_txn(conn, user_id, lambda: stamp)
            self._change(conn, user_id, "server_user_wallets", str(user_id))
        elif not complete and existing:
            conn.execute("DELETE FROM server_reward_ledger WHERE user_id=? AND id=?", (user_id, ledger_id))
            self._change(conn, user_id, "server_reward_ledger", ledger_id, "delete")
            self.wallet.rebuild_wallet_snapshot_in_txn(conn, user_id, lambda: stamp)
            self._change(conn, user_id, "server_user_wallets", str(user_id))

    def _remove_diet_penalty(self, conn, user_id: int, date: str, rule_key: str) -> None:
        source = f"exercise-diet-penalty:{user_id}:{date}:{PLAN_VERSION}:{rule_key}"
        if conn.execute("SELECT 1 FROM server_reward_ledger WHERE user_id=? AND id=?", (user_id, source)).fetchone():
            conn.execute("DELETE FROM server_reward_ledger WHERE user_id=? AND id=?", (user_id, source))
            self._change(conn, user_id, "server_reward_ledger", source, "delete")
            stamp = self.wallet._now()
            self.wallet.rebuild_wallet_snapshot_in_txn(conn, user_id, lambda: stamp)
            self._change(conn, user_id, "server_user_wallets", str(user_id))
