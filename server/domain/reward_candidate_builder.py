# -*- coding: utf-8 -*-
"""在隔离数据库中按当前规则生成完整金币候选账。"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone

try:
    from ..statistics_start_date import BEIJING_TIMEZONE, is_statistics_date_eligible
    from .sleep_reward_service import DIARY_REWARD_EFFECTIVE_DATE, DIARY_REWARD_VERSION, select_authoritative_sleep_diary_settlements, select_authoritative_sleep_settlements
except ImportError:
    from statistics_start_date import BEIJING_TIMEZONE, is_statistics_date_eligible
    from domain.sleep_reward_service import DIARY_REWARD_EFFECTIVE_DATE, DIARY_REWARD_VERSION, select_authoritative_sleep_diary_settlements, select_authoritative_sleep_settlements


class RewardCandidateBuilder:
    PROJECTION_TABLES = (
        "server_reward_ledger", "server_user_wallets",
        "server_backpack_events", "server_reward_fragments",
    )
    REPLAYED_LEDGER_TYPES = frozenset({
        "task_complete", "habit_checkin", "habit_fail", "learning_checkin", "learning_objective_complete",
        "goal_reward", "goal_penalty", "exercise_score", "exercise_completion_reward",
        "body_metric_deadline_penalty", "exercise_diet_penalty",
        "sleep_settlement_reward", "sleep_cycle_penalty", "sleep_completion_reward", "sleep_diary_completion_reward",
        "sleep_morning_diary_reward", "sleep_evening_diary_reward",
        "reward_buy", "store_custom_spend", "manual_adjustment", "backpack_use", "backpack_discard",
        "external_claim",
    })

    def __init__(self, store):
        self.store = store
        self.skipped: list[dict] = []

    @staticmethod
    def _provider_time(value) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("+0000", "+00:00").replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=BEIJING_TIMEZONE)
            return parsed.astimezone(BEIJING_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    def _skip(self, source, source_id, reason, business_date=None):
        self.skipped.append({
            "source": source, "source_id": str(source_id),
            "business_date": business_date, "reason": reason,
        })

    def _clear(self, conn, user_id, start_date):
        for table in self.PROJECTION_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
        conn.execute(
            """INSERT INTO server_system_config(user_id,key,value,updated_at)
               VALUES (?, 'statistics_start_date', ?, ?)
               ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
            (user_id, start_date, self.store.reward_wallet_service._now()),
        )

    def _assert_ledger_coverage(self, conn, user_id, start_date):
        rows = conn.execute(
            "SELECT DISTINCT source_type FROM server_reward_ledger WHERE user_id=? AND target_date>=?",
            (user_id, start_date),
        ).fetchall()
        unknown = sorted({str(row["source_type"]) for row in rows} - self.REPLAYED_LEDGER_TYPES)
        if unknown:
            raise ValueError(f"unsupported_ledger_sources:{','.join(unknown)}")
        return {
            str(row["source_type"]): int(row["count"])
            for row in conn.execute(
                "SELECT source_type,COUNT(*) count FROM server_reward_ledger WHERE user_id=? AND target_date>=? GROUP BY source_type",
                (user_id, start_date),
            ).fetchall()
        }

    def _replay_sleep(self, conn, user_id, start_date):
        rows = conn.execute(
            """SELECT * FROM server_sleep_score_settlements
               WHERE user_id=? AND sleep_date>=?""",
            (user_id, start_date),
        ).fetchall()
        selected = select_authoritative_sleep_settlements(rows)
        for sleep_date in sorted(selected):
            row = selected[sleep_date]
            version = str(row.get("rule_version") or "sleep-score-v2")
            source_prefix = f"sleep-score:{sleep_date}:{version}"
            occurred_at = row.get("occurred_at") or f"{sleep_date} 00:00:00"
            entries = (
                (row.get("reward_amount"), "sleep_settlement_reward", f"{source_prefix}:reward", f"sleep-reward:{user_id}:{sleep_date}:{version}", f"睡眠评分奖励：{int(row.get('score_total') or 0)}/100"),
                (row.get("cycle_penalty"), "sleep_cycle_penalty", f"{source_prefix}:cycle-penalty", f"sleep-cycle-penalty:{user_id}:{sleep_date}:{version}", "睡眠周期不足（<4.0）" if float(row.get("cycle_penalty") or 0) else "睡眠周期结果：无处罚"),
                (row.get("completion_reward_amount"), "sleep_completion_reward", f"{source_prefix}:completion", f"sleep-completion-reward:{user_id}:{sleep_date}:{version}", "睡眠指标全完成奖励：十项均满分" if bool(row.get("is_all_complete")) else "睡眠指标全完成奖励：未获得"),
            )
            for amount, source_type, source_id, ledger_id, description in entries:
                self.store.reward_wallet_service.append_ledger_in_txn(
                    conn, user_id, float(amount or 0), source_type, source_id, description,
                    sleep_date, ledger_id, occurred_at,
                )
        for sleep_date, row in sorted(select_authoritative_sleep_diary_settlements(rows).items()):
            if sleep_date >= DIARY_REWARD_EFFECTIVE_DATE:
                for diary_type, label in (("morning", "晨间"), ("evening", "晚间")):
                    if row.get(f"{diary_type}_diary_reward_status") != "completed":
                        continue
                    ledger_id = f"sleep-{diary_type}-diary-reward:{user_id}:{sleep_date}:{DIARY_REWARD_VERSION}"
                    self.store.reward_wallet_service.append_ledger_in_txn(
                        conn, user_id, float(row.get(f"{diary_type}_diary_reward_amount") or 0),
                        f"sleep_{diary_type}_diary_reward", ledger_id, f"{label}日记奖励", sleep_date,
                        ledger_id, row.get("occurred_at") or f"{sleep_date} 00:00:00",
                    )
                continue
            if row.get("diary_completion_status") != "completed":
                continue
            version = str(row.get("rule_version") or "sleep-score-v2")
            self.store.reward_wallet_service.append_ledger_in_txn(
                conn, user_id, float(row.get("diary_completion_reward_amount") or 0),
                "sleep_diary_completion_reward", f"sleep-score:{sleep_date}:{version}:diary-completion",
                row.get("diary_completion_reason") or "晨间与晚间日记均已完成", sleep_date,
                f"sleep-diary-completion-reward:{user_id}:{sleep_date}:{version}", row.get("occurred_at") or f"{sleep_date} 00:00:00",
            )

    def _assert_sleep_ledger_authority(self, conn, user_id, start_date):
        settlements = conn.execute(
            """SELECT * FROM server_sleep_score_settlements
               WHERE user_id=? AND sleep_date>=?""",
            (user_id, start_date),
        ).fetchall()
        expected = {}
        for sleep_date, row in select_authoritative_sleep_settlements(settlements).items():
            version = str(row.get("rule_version") or "sleep-score-v2")
            expected[sleep_date] = {
                f"sleep-reward:{user_id}:{sleep_date}:{version}": float(row.get("reward_amount") or 0),
                f"sleep-cycle-penalty:{user_id}:{sleep_date}:{version}": float(row.get("cycle_penalty") or 0),
                f"sleep-completion-reward:{user_id}:{sleep_date}:{version}": float(row.get("completion_reward_amount") or 0),
            }
        for sleep_date, row in select_authoritative_sleep_diary_settlements(settlements).items():
            if sleep_date >= DIARY_REWARD_EFFECTIVE_DATE:
                for diary_type in ("morning", "evening"):
                    if row.get(f"{diary_type}_diary_reward_status") == "completed":
                        expected.setdefault(sleep_date, {})[f"sleep-{diary_type}-diary-reward:{user_id}:{sleep_date}:{DIARY_REWARD_VERSION}"] = float(row.get(f"{diary_type}_diary_reward_amount") or 0)
                continue
            if row.get("diary_completion_status") == "completed":
                version = str(row.get("rule_version") or "sleep-score-v2")
                expected.setdefault(sleep_date, {})[f"sleep-diary-completion-reward:{user_id}:{sleep_date}:{version}"] = float(row.get("diary_completion_reward_amount") or 0)
        rows = conn.execute(
            """SELECT id,amount,target_date FROM server_reward_ledger WHERE user_id=? AND target_date>=?
               AND source_type IN ('sleep_settlement_reward','sleep_cycle_penalty','sleep_completion_reward','sleep_diary_completion_reward','sleep_morning_diary_reward','sleep_evening_diary_reward')""",
            (user_id, start_date),
        ).fetchall()
        actual = {}
        for row in rows:
            actual.setdefault(str(row["target_date"])[:10], {})[str(row["id"])] = float(row["amount"])
        for sleep_date in sorted(set(expected) | set(actual)):
            if expected.get(sleep_date, {}) != actual.get(sleep_date, {}):
                versions = sorted({ledger_id.rsplit(":", 1)[0].split(":")[-1] for ledger_id in actual.get(sleep_date, {})})
                raise ValueError(
                    f"sleep_ledger_authority_mismatch:user={user_id}:date={sleep_date}:versions={','.join(versions)}"
                )

    def _task_and_habit_events(self, conn, user_id, start_date):
        events = []
        task_titles = {
            str(row["id"]): str(row["title"] or "")
            for row in conn.execute(
                "SELECT id,title FROM server_tasks WHERE user_id=? AND deleted_at IS NULL", (user_id,),
            ).fetchall()
        }
        occurrence_sources = set()
        for row in conn.execute(
            """SELECT source_id,description,target_date FROM server_reward_ledger
               WHERE user_id=? AND source_type='task_complete' AND target_date>=? AND source_id LIKE '%#%'""",
            (user_id, start_date),
        ).fetchall():
            source_id = str(row["source_id"] or "")
            task_id, completed_time = source_id.rsplit("#", 1)
            occurred_at = self._provider_time(completed_time)
            if not occurred_at:
                self._skip("task", source_id, "missing_completed_time", row["target_date"])
                continue
            title = task_titles.get(task_id) or str(row["description"] or "").removeprefix("√ 任务 ") or "清单"
            source_id = f"{task_id}#{occurred_at}"
            if source_id in occurrence_sources:
                continue
            occurrence_sources.add(source_id)
            events.append((occurred_at, "task", {
                "id": task_id, "title": title, "source_id": source_id,
            }, {"completedTime": completed_time}))
        for row in conn.execute(
            "SELECT id,title,raw_json FROM server_tasks WHERE user_id=? AND status=2 AND deleted_at IS NULL",
            (user_id,),
        ).fetchall():
            try:
                raw = json.loads(row["raw_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                raw = {}
            occurred_at = self._provider_time(raw.get("completedTime"))
            if not occurred_at:
                self._skip("task", row["id"], "missing_completed_time")
                continue
            source_id = f"{row['id']}#{occurred_at}"
            if source_id not in occurrence_sources and is_statistics_date_eligible(occurred_at[:10], start_date):
                task = dict(row)
                task["source_id"] = source_id
                events.append((occurred_at, "task", task, raw))
        rows = conn.execute(
            """SELECT c.*,h.name,h.difficulty FROM server_habit_checkins c
               JOIN server_habits h ON h.user_id=c.user_id AND h.id=c.habit_id
               WHERE c.user_id=? AND c.status IN (1,2)""", (user_id,),
        ).fetchall()
        for row in rows:
            target_date = str(row["checkin_date"] or row["date"] or "")[:10]
            if not is_statistics_date_eligible(target_date, start_date):
                continue
            occurred_at = str(row["checkin_time"] or "")
            if occurred_at and len(occurred_at) <= 8:
                occurred_at = f"{target_date} {occurred_at}"
            if int(row["status"]) == 2 and not occurred_at:
                self._skip("habit", row["habit_id"], "missing_checkin_time", target_date)
                continue
            events.append((occurred_at or f"{target_date} 00:00:00", "habit", dict(row), {}))
        return sorted(events, key=lambda event: (event[0], event[1], str(event[2].get("id"))))

    def _replay_task_and_habit(self, conn, user_id, events):
        rules, settlement = self.store.reward_rule_service, self.store.reward_settlement_service
        for occurred_at, kind, row, raw in events:
            target_date = occurred_at[:10] if kind == "task" else str(row.get("checkin_date") or row.get("date"))[:10]
            try:
                if kind == "task":
                    reward = rules.calculate_task_success(user_id, row["id"], row["title"])
                    source_id = row["source_id"]
                    settlement.settle_task_success_in_txn(
                        conn, user_id, source_id, reward.title, reward.amount, target_date, occurred_at,
                    )
                    event_key = settlement.completion_event_key("checklist_task", row["id"], target_date, occurred_at)
                    settlement.grant_task_unlocks_in_txn(conn, user_id, "checklist_task", row["id"], event_key, row["title"], target_date)
                elif int(row["status"]) == 2:
                    reward = rules.calculate_habit_success(user_id, row["habit_id"], row["name"], row["difficulty"], target_date, occurred_at)
                    settlement.settle_habit_success_in_txn(conn, user_id, row["habit_id"], reward.title, reward.amount, target_date, occurred_at)
                    event_key = settlement.completion_event_key("habit", row["habit_id"], target_date)
                    settlement.grant_task_unlocks_in_txn(conn, user_id, "habit", row["habit_id"], event_key, row["name"], target_date)
                else:
                    reward = rules.calculate_habit_fail(user_id, row["habit_id"], row["name"], row["difficulty"])
                    settlement.settle_habit_fail_in_txn(conn, user_id, row["habit_id"], reward.title, reward.amount, target_date, occurred_at)
            except Exception as exc:
                self._skip(kind, row.get("id") or row.get("habit_id"), type(exc).__name__, target_date)

    def _replay_learning(self, conn, user_id, start_date):
        objectives = conn.execute(
            """SELECT o.id,o.title,MAX(link.completed_at) completed_at
               FROM server_learning_objectives o
               LEFT JOIN server_learning_krs kr ON kr.user_id=o.user_id AND kr.objective_id=o.id
               LEFT JOIN server_learning_tasks task ON task.user_id=kr.user_id AND task.kr_id=kr.id
               LEFT JOIN server_learning_checklist_links link ON link.user_id=task.user_id AND link.learning_task_id=task.id
               WHERE o.user_id=? AND o.status=2 GROUP BY o.id,o.title""", (user_id,),
        ).fetchall()
        for objective in objectives:
            if not self.store._objective_links_completed_in_txn(conn, user_id, objective["id"]):
                self._skip("learning", objective["id"], "linked_checklist_incomplete")
                continue
            occurred_at = self._provider_time(objective["completed_at"])
            if not occurred_at:
                self._skip("learning", objective["id"], "missing_completed_time")
                continue
            if not is_statistics_date_eligible(occurred_at[:10], start_date):
                continue
            reward = conn.execute(
                "SELECT coins FROM server_reward_config WHERE user_id=? AND item_type='learning_objective' AND item_id=?",
                (user_id, objective["id"]),
            ).fetchone()
            if reward is not None:
                source = f"learning_objective:{objective['id']}"
                self.store.reward_settlement_service.settle_in_txn(
                    conn, user_id, float(reward["coins"]), "learning", objective["title"],
                    "learning_objective_complete", source, occurred_at[:10], True, source, occurred_at,
                )
                self.store.reward_settlement_service.grant_task_unlocks_in_txn(
                    conn, user_id, "learning_objective", objective["id"], source,
                    objective["title"], occurred_at[:10],
                )

    def _replay_learning_tasks(self, conn, user_id, start_date):
        rows = conn.execute(
            "SELECT id,title,updated_at FROM server_learning_tasks WHERE user_id=? AND status=2",
            (user_id,),
        ).fetchall()
        for row in rows:
            occurred_at = self._provider_time(row["updated_at"])
            if not occurred_at:
                self._skip("learning_task", row["id"], "missing_completed_time")
                continue
            if not is_statistics_date_eligible(occurred_at[:10], start_date):
                continue
            reward = self.store.reward_rule_service.calculate_learning_success(user_id, row["id"], row["title"])
            self.store.reward_settlement_service.settle_learning_success_in_txn(
                conn, user_id, row["id"], reward.title, reward.amount, occurred_at[:10],
            )

    def _replay_external_rewards(self, conn, user_id, start_date):
        rows = conn.execute(
            """SELECT ext_id,item_type,item_name,coins,created_at FROM server_external_rewards
               WHERE user_id=? AND status=1 AND substr(created_at,1,10)>=?""",
            (user_id, start_date),
        ).fetchall()
        for row in rows:
            target_date = str(row["created_at"] or "")[:10]
            if not target_date:
                self._skip("external_reward", row["ext_id"], "missing_created_at")
                continue
            amount = float(row["coins"])
            item_type = str(row["item_type"] or "")
            source_type = {"task": "task_complete", "goal": "goal_reward" if amount >= 0 else "goal_penalty"}.get(
                item_type, "habit_checkin" if item_type == "habit" and amount >= 0 else "habit_fail" if item_type == "habit" else "external_claim",
            )
            description = re.sub(r"[^\w\s,.\-\[\]()]", "", str(row["item_name"] or "")).strip()
            self.store.reward_wallet_service.append_ledger_in_txn(
                conn, user_id, amount, source_type, row["ext_id"], description, target_date,
                occurred_at=row["created_at"],
            )

    def _replay_exercise(self, conn, user_id, start_date):
        settlement_rows = conn.execute(
            """SELECT * FROM server_exercise_settlements
               WHERE user_id=? AND business_date>=? AND business_date<?""",
            (user_id, start_date, datetime.now(BEIJING_TIMEZONE).date().isoformat()),
        ).fetchall()
        settled_dates = set()
        if settlement_rows:
            logs = {
                str(row["date"])[:10]: dict(row)
                for row in conn.execute(
                    "SELECT * FROM server_exercise_daily_logs WHERE user_id=? AND date>=? AND date<?",
                    (user_id, start_date, datetime.now(BEIJING_TIMEZONE).date().isoformat()),
                ).fetchall()
            }
            for raw in settlement_rows:
                settlement = dict(raw)
                target_date = str(settlement["business_date"])[:10]
                settled_dates.add(target_date)
                score = float(settlement.get("score_total") or 0)
                completed = int(settlement.get("completed_items") or 0)
                total = int(settlement.get("total_items") or 0)
                plan_version = str(settlement.get("plan_version") or "v0")
                day_name = logs.get(target_date, {}).get("day_name") or self._day_name(target_date)
                title = f"{plan_version} {day_name} {int(round(score))}分 · {completed}/{total}项"
                amount = float(settlement.get("coin_amount") or 0)
                self.store.reward_settlement_service.settle_in_txn(
                    conn, user_id, amount, "exercise", title, "exercise_score",
                    f"exercise-score:{plan_version}:{target_date}", target_date, amount >= 0,
                    f"exercise-score:{user_id}:{plan_version}:{target_date}", f"{target_date} 00:00:00",
                )
                completion = float(settlement.get("completion_reward_amount") or 0)
                self.store.reward_wallet_service.append_ledger_in_txn(
                    conn, user_id, completion, "exercise_completion_reward",
                    f"exercise-completion:{plan_version}:{target_date}",
                    f"运动指标全完成奖励：{plan_version}" if bool(settlement.get("is_all_complete")) else f"运动指标全完成奖励：未获得（{plan_version}）", target_date,
                    f"exercise-completion-reward:{user_id}:{plan_version}:{target_date}",
                    settlement.get("occurred_at") or f"{target_date} 00:00:00",
                )
        rows = conn.execute(
            """SELECT * FROM server_exercise_daily_logs
               WHERE user_id=? AND date>=? AND date<? AND score_snapshot IS NOT NULL""",
            (user_id, start_date, datetime.now(BEIJING_TIMEZONE).date().isoformat()),
        ).fetchall()
        grouped = {}
        for raw in rows:
            row = dict(raw)
            try:
                row["score_total"] = float(json.loads(row["score_snapshot"])["total"])
            except (TypeError, ValueError, KeyError, json.JSONDecodeError):
                self._skip("exercise", row["id"], "invalid_score_snapshot", row["date"])
                continue
            grouped.setdefault(str(row["date"])[:10], []).append(row)
        for target_date, candidates in grouped.items():
            if target_date in settled_dates:
                continue
            rank = lambda r: (int(r.get("completed_items") or 0) / max(1, int(r.get("total_items") or 0)), r["score_total"], str(r.get("updated_at") or ""), str(r.get("plan_version") or "v0"))
            row = max(candidates, key=rank)
            title = f"{row.get('plan_version') or 'v0'} {row.get('day_name') or '运动'}"
            reward = self.store.reward_rule_service.calculate_exercise_score_band(title, row["score_total"], row.get("day_name"), row.get("completed_items"), row.get("total_items"))
            reward = type(reward)(amount=reward.amount, title=f"{reward.title} · {int(round(row['score_total']))}分 · {int(row.get('completed_items') or 0)}/{int(row.get('total_items') or 0)}项", is_makeup=reward.is_makeup, days_late=reward.days_late)
            self.store.reward_settlement_service.settle_in_txn(
                conn, user_id, reward.amount, "exercise", reward.title, "exercise_score",
                f"exercise-score:{row.get('plan_version') or 'v0'}:{target_date}", target_date, reward.amount >= 0,
                f"exercise-score:{user_id}:{row.get('plan_version') or 'v0'}:{target_date}", f"{target_date} 00:00:00",
            )
            self.store.reward_wallet_service.append_ledger_in_txn(
                conn, user_id, 0, "exercise_completion_reward", f"exercise-completion:{row.get('plan_version') or 'v0'}:{target_date}",
                f"运动指标全完成奖励：未获得（{row.get('plan_version') or 'v0'}）", target_date,
                f"exercise-completion-reward:{user_id}:{row.get('plan_version') or 'v0'}:{target_date}", f"{target_date} 00:00:00",
            )

    def _replay_body_metric_deadline_penalties(self, conn, user_id, start_date):
        rows = conn.execute(
            """SELECT date,deadline_penalty_source_id,deadline_penalty_amount,locked_at
               FROM server_exercise_checkins
               WHERE user_id=? AND date>=? AND deadline_penalty_source_id IS NOT NULL
                 AND deadline_penalty_source_id<>''""",
            (user_id, start_date),
        ).fetchall()
        for row in rows:
            target_date = str(row["date"])[:10]
            amount = float(row["deadline_penalty_amount"] or 0)
            if amount:
                source_id = str(row["deadline_penalty_source_id"])
                self.store.reward_wallet_service.append_ledger_in_txn(
                    conn, user_id, amount, "body_metric_deadline_penalty", source_id,
                    "体重体脂逾期未填写（09:00）", target_date,
                    f"body-metric-deadline-penalty:{user_id}:{target_date}",
                    row["locked_at"] or f"{target_date} 09:00:00",
                )
        v4_rows = conn.execute(
            """SELECT date,penalty_source_id,penalty_amount,deadline_at,created_at
               FROM server_exercise_deadline_facts
               WHERE user_id=? AND date>=? AND plan_version='v4' AND fact_type='body_metrics'
                 AND status='failed' AND penalty_source_id IS NOT NULL AND penalty_amount<>0""",
            (user_id, start_date),
        ).fetchall()
        for row in v4_rows:
            target_date = str(row["date"])[:10]
            self.store.reward_wallet_service.append_ledger_in_txn(
                conn, user_id, float(row["penalty_amount"]), "body_metric_deadline_penalty",
                f"body-metric-deadline:{target_date}", "体重体脂逾期未填写（09:00）", target_date,
                str(row["penalty_source_id"]), row["deadline_at"] or row["created_at"] or f"{target_date} 09:00:00",
            )

    def _replay_exercise_diet_penalties(self, conn, user_id, start_date):
        rows = conn.execute(
            """SELECT date,rule_key,penalty_source_id,updated_at
               FROM server_exercise_diet_checkins
               WHERE user_id=? AND date>=? AND plan_version='v4' AND status='failed'
                 AND penalty_source_id IS NOT NULL AND penalty_source_id<>''""",
            (user_id, start_date),
        ).fetchall()
        for row in rows:
            target_date = str(row["date"])[:10]
            source = str(row["penalty_source_id"])
            self.store.reward_wallet_service.append_ledger_in_txn(
                conn, user_id, -20, "exercise_diet_penalty", source,
                "饮食必做项逾期未完成", target_date, source,
                row["updated_at"] or f"{target_date} 00:00:00",
            )

    def _materialize_historical_body_metric_penalties(self, conn, user_id, start_date):
        yesterday = (datetime.now(BEIJING_TIMEZONE).date() - timedelta(days=1)).isoformat()
        rows = conn.execute("SELECT id,date,plan_version FROM server_exercise_daily_logs WHERE user_id=? AND date>=? AND date<=?", (user_id, start_date, yesterday)).fetchall()
        expected = []
        for row in rows:
            target_date, version, log_id = str(row["date"])[:10], str(row["plan_version"] or ""), str(row["id"])
            complete = conn.execute("SELECT 1 FROM server_exercise_daily_logs WHERE user_id=? AND date=? AND weight IS NOT NULL AND body_fat_rate IS NOT NULL", (user_id, target_date)).fetchone()
            items = conn.execute("SELECT item FROM server_exercise_plan_schedule_items WHERE user_id=? AND plan_version=? AND schedule_type=? ORDER BY sort_order", (user_id, version, "rest" if self._day_name(target_date) in {"六", "日"} else "weekday")).fetchall()
            index = next((i for i, item in enumerate(items) if "体重" in str(item["item"] or "") and "体脂" in str(item["item"] or "")), None)
            if complete or index is None:
                if not complete and index is None: self._skip("body_metric_deadline", target_date, "historical_plan_unproven", target_date)
                continue
            source_id, ledger_id, now = f"body-metric-deadline:{target_date}", f"body-metric-deadline-penalty:{user_id}:{target_date}", f"{target_date} 09:00:00"
            existing = conn.execute("SELECT id FROM server_exercise_checkins WHERE user_id=? AND date=? AND plan_version=? AND item_key=?", (user_id, target_date, version, f"sc-{target_date}-{index}")).fetchone()
            checkin_id = existing["id"] if existing else f"body-metric-lock:{user_id}:{target_date}:{version}"
            conn.execute("""INSERT INTO server_exercise_checkins (id,user_id,log_id,plan_version,item_key,status,note,item_name,date,locked_at,lock_reason,deadline_penalty_source_id,deadline_penalty_amount,created_at,updated_at) VALUES (?,?,?,?,?,?,'09:00 超时锁定：体重或体脂率未填写',?,?,?,'body_metrics_missing_at_09:00',?,-50,?,?) ON CONFLICT(id) DO UPDATE SET status=-1,locked_at=excluded.locked_at,lock_reason=excluded.lock_reason,deadline_penalty_source_id=excluded.deadline_penalty_source_id,deadline_penalty_amount=-50,updated_at=excluded.updated_at""", (checkin_id, user_id, log_id, version, f"sc-{target_date}-{index}", -1, str(items[index]["item"]), target_date, now, source_id, now, now))
            expected.append((ledger_id, target_date))
        return expected

    @staticmethod
    def _day_name(target_date: str) -> str:
        return ("一", "二", "三", "四", "五", "六", "日")[date.fromisoformat(target_date).weekday()]

    def _replay_additional_unlocks(self, conn, user_id, start_date):
        settlement = self.store.reward_settlement_service
        learning_tasks = conn.execute(
            """SELECT task.id,task.title,MAX(link.completed_at) completed_at,
                      SUM(CASE WHEN link.completed_at IS NULL THEN 1 ELSE 0 END) incomplete
               FROM server_learning_tasks task
               JOIN server_reward_source_bindings binding
                 ON binding.user_id=task.user_id AND binding.source_type='learning_task' AND binding.source_id=task.id
               LEFT JOIN server_learning_checklist_links link
                 ON link.user_id=task.user_id AND link.learning_task_id=task.id
               WHERE task.user_id=? AND task.status=2 GROUP BY task.id,task.title""", (user_id,),
        ).fetchall()
        for row in learning_tasks:
            occurred_at = self._provider_time(row["completed_at"])
            if int(row["incomplete"] or 0) or not occurred_at:
                self._skip("learning_task", row["id"], "missing_completed_time")
                continue
            if not is_statistics_date_eligible(occurred_at[:10], start_date):
                continue
            event_key = settlement.completion_event_key(
                "learning_task", row["id"], occurred_at[:10], occurred_at,
            )
            settlement.grant_task_unlocks_in_txn(
                conn, user_id, "learning_task", row["id"], event_key, row["title"], occurred_at[:10],
            )
        exercise_rows = conn.execute(
            """SELECT checkin.plan_item_id,checkin.plan_version,checkin.item_key,checkin.item_name,checkin.date
               FROM server_exercise_checkins checkin
               JOIN server_reward_source_bindings binding ON binding.user_id=checkin.user_id
                 AND binding.source_type='exercise_checkin' AND binding.source_id=checkin.plan_item_id
               WHERE checkin.user_id=? AND checkin.status=1 AND checkin.date>=? AND checkin.date<?""",
            (user_id, start_date, datetime.now(BEIJING_TIMEZONE).date().isoformat()),
        ).fetchall()
        for row in exercise_rows:
            target_date = str(row["date"])[:10]
            event_key = settlement.completion_event_key(
                "exercise_checkin", row["plan_item_id"], target_date,
                plan_version=row["plan_version"], item_key=row["item_key"],
            )
            settlement.grant_task_unlocks_in_txn(
                conn, user_id, "exercise_checkin", row["plan_item_id"], event_key,
                row["item_name"] or "运动打卡", target_date,
            )

    def _replay_actions(self, conn, user_id, start_date):
        rows = conn.execute(
            """SELECT * FROM server_reward_action_events WHERE user_id=?
               ORDER BY occurred_at,
                 CASE event_type WHEN 'reward_purchase' THEN 0 WHEN 'custom_spend' THEN 1
                      WHEN 'manual_adjustment' THEN 2 WHEN 'backpack_use' THEN 3
                      WHEN 'backpack_discard' THEN 4 ELSE 5 END,
                 id""", (user_id,),
        ).fetchall()
        for row in rows:
            occurred_at = str(row["occurred_at"])
            if not is_statistics_date_eligible(occurred_at[:10], start_date):
                continue
            payload = json.loads(row["payload_json"] or "{}")
            ledger_id = str(payload.get("ledger_id") or str(row["id"]).removeprefix("action:"))
            event_type = str(row["event_type"])
            source_type = str(payload.get("source_type") or {"reward_purchase": "reward_buy", "custom_spend": "store_custom_spend", "manual_adjustment": "manual_adjustment", "backpack_use": "backpack_use", "backpack_discard": "backpack_discard"}.get(event_type, event_type))
            source_id = payload.get("source_id") or row["subject_id"]
            if event_type in {"backpack_use", "backpack_discard"} and not conn.execute(
                "SELECT 1 FROM server_reward_ledger WHERE user_id=? AND id=? AND source_type='reward_buy'", (user_id, str(source_id)),
            ).fetchone():
                self._skip(event_type, row["id"], "missing_acquisition", occurred_at[:10])
                continue
            self.store.reward_wallet_service.append_ledger_in_txn(
                conn, user_id, float(row["amount"]), source_type, source_id,
                str(payload.get("description") or event_type), occurred_at[:10], ledger_id, occurred_at,
            )
            if event_type in {"backpack_use", "backpack_discard"}:
                self.store.reward_wallet_service.record_backpack_event_in_txn(
                    conn, user_id, str(source_id), "used" if event_type == "backpack_use" else "discarded",
                    event_id=f"backpack:{event_type}:{ledger_id}", occurred_at=occurred_at,
                )

    def build(self, user_id: int, start_date: str) -> dict:
        with self.store._transact() as conn:
            task_and_habit_events = self._task_and_habit_events(conn, user_id, start_date)
            covered_sources = self._assert_ledger_coverage(conn, user_id, start_date)
            self._clear(conn, user_id, start_date)
            expected_facts = self._materialize_historical_body_metric_penalties(conn, user_id, start_date)
            self._replay_task_and_habit(conn, user_id, task_and_habit_events)
            self._replay_learning(conn, user_id, start_date)
            self._replay_learning_tasks(conn, user_id, start_date)
            self._replay_exercise(conn, user_id, start_date)
            self._replay_body_metric_deadline_penalties(conn, user_id, start_date)
            self._replay_exercise_diet_penalties(conn, user_id, start_date)
            for ledger_id, target_date in expected_facts:
                row = conn.execute("SELECT amount FROM server_reward_ledger WHERE user_id=? AND id=?", (user_id, ledger_id)).fetchone()
                if not row or float(row["amount"]) != -50: raise ValueError(f"missing_expected_reward_fact:{ledger_id}:{target_date}")
            self._replay_sleep(conn, user_id, start_date)
            self._assert_sleep_ledger_authority(conn, user_id, start_date)
            self._replay_external_rewards(conn, user_id, start_date)
            self._replay_additional_unlocks(conn, user_id, start_date)
        self.store.auto_settle_goals(user_id)
        with self.store._transact() as conn:
            self._replay_actions(conn, user_id, start_date)
            self.store.reward_settlement_service.expire_fragments_for_user_in_txn(conn, user_id)
            wallet = self.store.reward_wallet_service.rebuild_wallet_snapshot_in_txn(conn, user_id, self.store.reward_wallet_service._now)
            ledger_total = conn.execute(
                "SELECT COALESCE(SUM(amount),0) FROM server_reward_ledger WHERE user_id=?", (user_id,),
            ).fetchone()[0]
            if float(wallet["balance"]) != float(ledger_total):
                raise ValueError(f"wallet_ledger_mismatch:user={user_id}:wallet={wallet['balance']}:ledger={ledger_total}")
            ledger_count = conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=?", (user_id,)).fetchone()[0]
            source_counts = {
                str(row["source_type"]): int(row["count"])
                for row in conn.execute(
                    "SELECT source_type,COUNT(*) count FROM server_reward_ledger WHERE user_id=? GROUP BY source_type",
                    (user_id,),
                ).fetchall()
            }
            reduced_sources = [source_type for source_type in covered_sources
                               if source_type not in source_counts]
            if reduced_sources:
                raise ValueError("unreplayed_ledger_sources:" + ",".join(sorted(reduced_sources)))
            # Candidate must retain every registered historical ledger source.
            backpack_items = conn.execute(
                """SELECT COUNT(*) FROM server_reward_ledger acquired
                   WHERE acquired.user_id=? AND acquired.source_type='reward_buy'
                     AND NOT EXISTS (SELECT 1 FROM server_reward_ledger terminal
                       WHERE terminal.user_id=acquired.user_id AND terminal.source_id=acquired.id
                         AND terminal.source_type IN ('backpack_use','backpack_discard'))""", (user_id,),
            ).fetchone()[0]
            fragment_rows = conn.execute(
                "SELECT COUNT(*) FROM server_reward_fragments WHERE user_id=?", (user_id,),
            ).fetchone()[0]
            eligible_actions = conn.execute(
                "SELECT COUNT(*) FROM server_reward_action_events WHERE user_id=? AND substr(occurred_at,1,10)>=?",
                (user_id, start_date),
            ).fetchone()[0]
        return {
            "ledger_rows": int(ledger_count), "balance": wallet["balance"], "skipped": self.skipped,
            "source_counts": source_counts, "backpack_items": int(backpack_items),
            "fragment_rows": int(fragment_rows), "eligible_action_events": int(eligible_actions),
            "task_events": sum(1 for event in task_and_habit_events if event[1] == "task"),
            "habit_events": sum(1 for event in task_and_habit_events if event[1] == "habit"),
            "covered_sources": covered_sources,
        }
