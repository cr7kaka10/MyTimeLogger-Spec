# -*- coding: utf-8 -*-
"""金币流水预览、恢复快照、隔离候选生成与原子发布。"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import tempfile
import time
import uuid

try:
    from ..statistics_start_date import parse_statistics_start_date
    from .reward_candidate_builder import RewardCandidateBuilder
    from .reward_rebuild_diagnostics import failure_report, log_event, normalize_trace_id, safe_json
except ImportError:
    from statistics_start_date import parse_statistics_start_date
    from domain.reward_candidate_builder import RewardCandidateBuilder
    from domain.reward_rebuild_diagnostics import failure_report, log_event, normalize_trace_id, safe_json


logger = logging.getLogger("server.reward_rebuild")


class RewardRebuildError(ValueError):
    pass


class RewardRebuildService:
    FRAGMENT_EVENT_TYPES = frozenset({
        "fragment_acquired", "fragment_expired", "fragment_revoked", "fragment_composed",
    })
    SINGLE_FRAGMENT_EVENT_TYPES = frozenset({
        "fragment_acquired", "fragment_expired", "fragment_revoked",
    })
    SNAPSHOT_TABLES = (
        "server_reward_ledger", "server_external_rewards", "server_user_wallets",
        "server_backpack_events", "server_reward_fragments", "server_tasks",
        "server_habits", "server_habit_checkins",
    )
    PROJECTION_TABLES = RewardCandidateBuilder.PROJECTION_TABLES
    REVISION_TABLES = (
        "server_tasks", "server_habits", "server_habit_checkins", "server_study_sessions",
        "server_goals", "server_learning_objectives",
        "server_learning_checklist_links", "server_reward_config", "server_rewards",
        "server_reward_action_events", "server_reward_source_bindings", "server_exercise_checkins",
        "server_exercise_daily_logs", "server_exercise_settlements", "server_sleep_score_settlements",
        "server_learning_tasks", "server_learning_krs", "server_external_rewards",
    )

    @staticmethod
    def _diagnostic_json(value, fallback=None):
        try:
            return safe_json(value, fallback)
        except Exception:
            source = value if isinstance(value, dict) else {}
            minimum = fallback or {
                key: source.get(key) for key in (
                    "version", "code", "message_zh", "failed_stage", "trace_id", "job_id", "recovery",
                ) if source.get(key) is not None
            } or {"code": "diagnostic_unavailable"}
            return json.dumps(minimum, ensure_ascii=False, default=lambda _value: "[unavailable]")

    @staticmethod
    def _failure_report(error, **context):
        try:
            return failure_report(error, **context)
        except Exception:
            return {
                "version": 1, "code": str(error)[:200], "message_zh": "重建失败，诊断信息生成异常",
                "failed_stage": context.get("failed_stage") or "unknown", "retryable": False,
                "trace_id": normalize_trace_id(context.get("trace_id")), "job_id": context.get("job_id"),
                "causes": [], "recovery": context.get("recovery") or {"status": "unknown", "verified": False},
                "suggestions": ["请携带诊断编号联系维护者"],
            }

    def __init__(self, store):
        self.store = store
        self.recover_interrupted_jobs()

    @staticmethod
    def _candidate_error(check, record_id, reference_id=None):
        error = RewardRebuildError("candidate_reference_invalid")
        error.reward_rebuild_details = {
            "check": check,
            "record_id_suffix": str(record_id or "")[-6:],
        }
        if reference_id:
            error.reward_rebuild_details["reference_id_suffix"] = str(reference_id)[-6:]
        return error

    def _publish_restored_state_in_txn(self, conn, user_id, snapshot, replaced_ids):
        for table in ("server_tasks", "server_habits", "server_habit_checkins"):
            restored = {str(row["id"]): row for row in snapshot["tables"].get(table, [])}
            for record_id in sorted(set(replaced_ids.get(table, ())) | set(restored)):
                operation = "upsert" if record_id in restored else "delete"
                payload = restored.get(record_id, {"id": record_id})
                self.store._record_server_change(conn, user_id, table, record_id, operation, payload)
        published_version = self.store._record_server_change(
            conn, user_id, "reward_rebuild_recovery", str(user_id), "upsert", {"epoch_restored": True},
        )
        epoch = int(snapshot.get("epoch") or 0)
        now = self.store.reward_wallet_service._now()
        conn.execute(
            """INSERT INTO server_reward_rebuild_epochs(user_id,active_epoch,published_version,updated_at)
               VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET active_epoch=excluded.active_epoch,
               published_version=excluded.published_version,updated_at=excluded.updated_at""",
            (user_id, epoch, published_version, now),
        )

    def recover_interrupted_jobs(self):
        """Server restart cannot leave clients pinned to an unfinished old snapshot."""
        now = self.store.reward_wallet_service._now()
        with self.store._transact() as conn:
            jobs = conn.execute(
                "SELECT id,user_id,trace_id FROM server_reward_rebuild_jobs WHERE status IN ('queued','running')",
            ).fetchall()
            for job in jobs:
                trace_id = normalize_trace_id(job["trace_id"] or job["id"])
                recovery = {"status": "not_required", "verified": True}
                snapshot = conn.execute(
                    "SELECT snapshot_json FROM server_reward_rebuild_snapshots WHERE job_id=? AND user_id=?",
                    (job["id"], job["user_id"]),
                ).fetchone()
                if snapshot:
                    state = json.loads(snapshot["snapshot_json"])
                    replaced_ids = {
                        table: [str(row["id"]) for row in conn.execute(
                            f"SELECT id FROM {table} WHERE user_id=?", (job["user_id"],),
                        ).fetchall()]
                        for table in ("server_tasks", "server_habits", "server_habit_checkins")
                    }
                    self._restore_snapshot_in_txn(conn, job["user_id"], state)
                    self._publish_restored_state_in_txn(conn, job["user_id"], state, replaced_ids)
                    recovery = self._verify_restored_in_txn(conn, job["user_id"], state)
                report = self._failure_report("server_restarted", trace_id=trace_id, job_id=job["id"],
                                              failed_stage="restore", recovery=recovery)
                conn.execute(
                    "UPDATE server_reward_rebuild_jobs SET status='failed',error='server_restarted',trace_id=?,failure_report_json=?,updated_at=? WHERE id=?",
                    (trace_id, self._diagnostic_json(report), now, job["id"]),
                )
                conn.execute("DELETE FROM server_reward_rebuild_snapshots WHERE job_id=?", (job["id"],))
                log_event(logger, trace_id=trace_id, job_id=job["id"], user_id=job["user_id"],
                          stage="restore", event="server_restart_recovery", outcome="success" if recovery["verified"] else "failure",
                          details=recovery, level=logging.WARNING)

    @staticmethod
    def _rows(conn, table, user_id):
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table} WHERE user_id=?", (user_id,)).fetchall()]

    def _revision(self, conn, user_id):
        facts = self._revision_facts(conn, user_id)
        return hashlib.sha256(json.dumps(facts, ensure_ascii=False).encode("utf-8")).hexdigest()

    def _revision_facts(self, conn, user_id):
        facts = []
        for table in self.REVISION_TABLES:
            columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            time_col = "updated_at" if "updated_at" in columns else "completed_at" if "completed_at" in columns else "created_at"
            row = conn.execute(
                f"SELECT COUNT(*) count,MAX(COALESCE({time_col},'')) stamp FROM {table} WHERE user_id=?", (user_id,),
            ).fetchone()
            facts.append((table, int(row["count"]), str(row["stamp"] or "")))
        return facts

    def _backfill_actions(self, conn, user_id):
        rows = conn.execute(
            """SELECT * FROM server_reward_ledger WHERE user_id=? AND (
                 source_type IN ('store_custom_spend','backpack_use','backpack_discard','manual_adjustment')
                 OR (source_type='reward_buy' AND source_id NOT LIKE 'unlock:%' AND source_id NOT LIKE '%:goal:%'))""",
            (user_id,),
        ).fetchall()
        mapping = {"store_custom_spend": "custom_spend", "reward_buy": "reward_purchase",
                   "backpack_use": "backpack_use", "backpack_discard": "backpack_discard",
                   "manual_adjustment": "manual_adjustment"}
        for row in rows:
            payload = {"ledger_id": row["id"], "source_id": row["source_id"],
                       "source_type": row["source_type"], "description": row["description"] or ""}
            conn.execute(
                """INSERT OR IGNORE INTO server_reward_action_events
                   (id,user_id,event_type,amount,occurred_at,subject_id,payload_json,created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (f"action:{row['id']}", user_id, mapping[row["source_type"]], float(row["amount"]),
                 row["occurred_at"] or row["created_at"], row["source_id"],
                 json.dumps(payload, ensure_ascii=False, sort_keys=True), row["created_at"]),
            )

    def _preview_in_txn(self, conn, user_id, start_date):
        revision = self._revision(conn, user_id)
        ledger = conn.execute(
            "SELECT COUNT(*) count,COALESCE(SUM(amount),0) balance FROM server_reward_ledger WHERE user_id=?", (user_id,),
        ).fetchone()
        behavior_count = sum(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=?", (user_id,)).fetchone()[0]
                             for table in ("server_tasks", "server_habit_checkins", "server_study_sessions", "server_exercise_daily_logs", "server_reward_action_events"))
        digest = hashlib.sha256(f"{user_id}:{start_date}:{revision}".encode("utf-8")).hexdigest()
        backpack_items = conn.execute(
            """SELECT COUNT(*) FROM server_reward_ledger acquired
               WHERE acquired.user_id=? AND acquired.source_type='reward_buy'
                 AND NOT EXISTS (SELECT 1 FROM server_reward_ledger terminal
                   WHERE terminal.user_id=acquired.user_id AND terminal.source_id=acquired.id
                     AND terminal.source_type IN ('backpack_use','backpack_discard'))""", (user_id,),
        ).fetchone()[0]
        fragments = conn.execute(
            "SELECT COUNT(*) FROM server_reward_fragments WHERE user_id=?", (user_id,),
        ).fetchone()[0]
        return {"statistics_start_date": start_date, "preview_hash": digest, "frozen_revision": revision,
                "old_ledger_rows": int(ledger["count"]), "old_balance": float(ledger["balance"]),
                "old_backpack_items": int(backpack_items), "old_fragment_rows": int(fragments),
                "behavior_rows": int(behavior_count), "new_ledger_rows_estimate": int(behavior_count)}

    def preview(self, user_id, start_date, trace_id=None):
        trace_id = normalize_trace_id(trace_id)
        started = time.perf_counter()
        log_event(logger, trace_id=trace_id, job_id=None, user_id=user_id,
                  stage="preview", event="start", outcome="running")
        parsed = parse_statistics_start_date(start_date, reject_future=True).isoformat()
        with self.store._transact() as conn:
            self._backfill_actions(conn, user_id)
            preview = self._preview_in_txn(conn, user_id, parsed)
        path = self._clone_to_temp()
        try:
            estimate = RewardCandidateBuilder(type(self.store)(db_path=path)).build(user_id, parsed)
            preview.update({"new_ledger_rows_estimate": estimate["ledger_rows"],
                            "new_balance_estimate": estimate["balance"],
                            "new_backpack_items_estimate": estimate["backpack_items"],
                            "new_fragment_rows_estimate": estimate["fragment_rows"],
                            "source_counts_estimate": estimate["source_counts"],
                            "skipped_estimate": len(estimate["skipped"]),
                            "skipped_preview": estimate["skipped"][:20],
                            "warnings": ["重算后余额为负，已保留真实消费行为"] if float(estimate["balance"]) < 0 else []})
            preview["trace_id"] = trace_id
            log_event(logger, trace_id=trace_id, job_id=None, user_id=user_id,
                      stage="preview", event="finish", outcome="success",
                      elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
                      details={"old_ledger_rows": preview["old_ledger_rows"], "new_ledger_rows": preview["new_ledger_rows_estimate"]})
            return preview
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def _snapshot(self, conn, user_id):
        epoch = conn.execute(
            "SELECT active_epoch FROM server_reward_rebuild_epochs WHERE user_id=?", (user_id,),
        ).fetchone()
        configs = [dict(row) for row in conn.execute(
            """SELECT * FROM server_system_config WHERE user_id=? AND key IN
               ('statistics_start_date','checklist_sync_start_date','checklist_ticktick_reset_marker')""", (user_id,),
        ).fetchall()]
        sync_state = [dict(row) for row in conn.execute(
            "SELECT * FROM server_sync_state WHERE user_id=? AND system='ticktick'", (user_id,),
        ).fetchall()]
        return {"tables": {table: self._rows(conn, table, user_id) for table in self.SNAPSHOT_TABLES},
                "configs": configs, "sync_state": sync_state,
                "epoch": int(epoch["active_epoch"]) if epoch else 0}

    def start(self, user_id, start_date, preview_hash, trace_id=None):
        trace_id = normalize_trace_id(trace_id)
        parsed = parse_statistics_start_date(start_date, reject_future=True).isoformat()
        now = self.store.reward_wallet_service._now()
        log_event(logger, trace_id=trace_id, job_id=None, user_id=user_id,
                  stage="job_create", event="start", outcome="running", details={"statistics_start_date": parsed})
        try:
            with self.store._transact() as conn:
                self._backfill_actions(conn, user_id)
                running = conn.execute(
                    "SELECT * FROM server_reward_rebuild_jobs WHERE user_id=? AND status IN ('queued','running') ORDER BY created_at DESC LIMIT 1", (user_id,),
                ).fetchone()
                if running:
                    return self.get_job(user_id, running["id"]), False
                preview = self._preview_in_txn(conn, user_id, parsed)
                if preview_hash != preview["preview_hash"]:
                    raise RewardRebuildError("preview_stale")
                job_id = uuid.uuid4().hex
                log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id,
                          stage="snapshot", event="start", outcome="running")
                snapshot = self._snapshot(conn, user_id)
                conn.execute(
                    """INSERT INTO server_reward_rebuild_jobs
                       (id,user_id,status,statistics_start_date,preview_hash,frozen_revision,trace_id,created_at,updated_at)
                       VALUES (?,?, 'queued',?,?,?,?,?,?)""",
                    (job_id, user_id, parsed, preview_hash, preview["frozen_revision"], trace_id, now, now),
                )
                conn.execute(
                    "INSERT INTO server_reward_rebuild_snapshots(job_id,user_id,epoch,snapshot_json,created_at) VALUES (?,?,?,?,?)",
                    (job_id, user_id, snapshot["epoch"], json.dumps(snapshot, ensure_ascii=False), now),
                )
                conn.execute(
                    """INSERT INTO server_system_config(user_id,key,value,updated_at)
                       VALUES (?, 'statistics_start_date', ?, ?) ON CONFLICT(user_id,key)
                       DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""", (user_id, parsed, now),
                )
                log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id,
                          stage="snapshot", event="finish", outcome="success",
                          details={"epoch": snapshot["epoch"], "tables": len(snapshot["tables"])})
        except sqlite3.IntegrityError:
            conn = self.store._connect()
            try:
                running = conn.execute(
                    "SELECT * FROM server_reward_rebuild_jobs WHERE user_id=? AND status IN ('queued','running') ORDER BY created_at DESC LIMIT 1",
                    (user_id,),
                ).fetchone()
                if running:
                    return self.get_job(user_id, running["id"]), False
            finally:
                conn.close()
            raise
        log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id,
                  stage="job_create", event="finish", outcome="success")
        return self.get_job(user_id, job_id), True

    def get_job(self, user_id, job_id):
        conn = self.store._connect()
        try:
            row = conn.execute("SELECT * FROM server_reward_rebuild_jobs WHERE user_id=? AND id=?", (user_id, job_id)).fetchone()
            if not row:
                raise RewardRebuildError("job_not_found")
            result = dict(row)
            for key in ("pull_diagnostics_json", "result_json", "failure_report_json"):
                result[key.removesuffix("_json")] = json.loads(result.pop(key) or "null")
            result["trace_id"] = normalize_trace_id(result.get("trace_id") or job_id)
            return result
        finally:
            conn.close()

    @staticmethod
    def _replace_rows(conn, table, user_id, rows):
        conn.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
        for row in rows:
            columns = list(row)
            conn.execute(
                f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                [row[column] for column in columns],
            )

    def _restore_snapshot_in_txn(self, conn, user_id, snapshot):
        tables = list(snapshot["tables"])
        for table in reversed(tables):
            try:
                conn.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
            except Exception as error:
                error.reward_restore_projection = table
                raise
        for table in tables:
            try:
                for row in snapshot["tables"][table]:
                    columns = list(row)
                    conn.execute(
                        f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                        [row[column] for column in columns],
                    )
            except Exception as error:
                error.reward_restore_projection = table
                raise
        conn.execute("DELETE FROM server_sync_state WHERE user_id=? AND system='ticktick'", (user_id,))
        for row in snapshot["sync_state"]:
            columns = list(row)
            conn.execute(f"INSERT INTO server_sync_state ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", [row[c] for c in columns])
        for key in ("statistics_start_date", "checklist_sync_start_date", "checklist_ticktick_reset_marker"):
            conn.execute("DELETE FROM server_system_config WHERE user_id=? AND key=?", (user_id, key))
        for row in snapshot["configs"]:
            columns = list(row)
            conn.execute(f"INSERT INTO server_system_config ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", [row[c] for c in columns])

    @staticmethod
    def _verify_restored_in_txn(conn, user_id, snapshot):
        ledger = float(conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM server_reward_ledger WHERE user_id=?", (user_id,),
        ).fetchone()[0] or 0)
        wallet_row = conn.execute("SELECT balance FROM server_user_wallets WHERE user_id=?", (user_id,)).fetchone()
        wallet = float(wallet_row[0] if wallet_row else 0)
        epoch_row = conn.execute("SELECT active_epoch FROM server_reward_rebuild_epochs WHERE user_id=?", (user_id,)).fetchone()
        epoch = int(epoch_row[0] if epoch_row else 0)
        expected_epoch = int(snapshot.get("epoch") or 0)
        verified = abs(ledger - wallet) <= 0.000001 and epoch == expected_epoch
        return {"status": "restored", "verified": verified, "ledger_balance": ledger,
                "wallet_balance": wallet, "epoch": epoch, "expected_epoch": expected_epoch}

    def fail_and_restore(self, user_id, job_id, error, pull_diagnostics=None, failed_stage=None):
        now = self.store.reward_wallet_service._now()
        job = self.get_job(user_id, job_id)
        trace_id = job["trace_id"]
        failed_stage = failed_stage or getattr(error, "reward_rebuild_stage", None)
        recovery = {"status": "not_required", "verified": True}
        log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id,
                  stage="restore", event="start", outcome="running", level=logging.WARNING)
        try:
            with self.store._transact() as conn:
                row = conn.execute("SELECT snapshot_json FROM server_reward_rebuild_snapshots WHERE user_id=? AND job_id=?", (user_id, job_id)).fetchone()
                if row:
                    snapshot = json.loads(row["snapshot_json"])
                    replaced_ids = {table: [str(item["id"]) for item in conn.execute(
                        f"SELECT id FROM {table} WHERE user_id=?", (user_id,),
                    ).fetchall()] for table in ("server_tasks", "server_habits", "server_habit_checkins")}
                    self._restore_snapshot_in_txn(conn, user_id, snapshot)
                    try:
                        self._publish_restored_state_in_txn(conn, user_id, snapshot, replaced_ids)
                    except Exception as error:
                        error.reward_restore_projection = "restored_sync_projection"
                        raise
                    recovery = self._verify_restored_in_txn(conn, user_id, snapshot)
                report = self._failure_report(error, trace_id=trace_id, job_id=job_id,
                                              failed_stage=failed_stage, pull=pull_diagnostics, recovery=recovery)
                conn.execute(
                    "UPDATE server_reward_rebuild_jobs SET status='failed',error=?,pull_diagnostics_json=?,failure_report_json=?,updated_at=? WHERE user_id=? AND id=?",
                    (str(error), self._diagnostic_json(pull_diagnostics), self._diagnostic_json(report), now, user_id, job_id),
                )
                conn.execute("DELETE FROM server_reward_rebuild_snapshots WHERE user_id=? AND job_id=?", (user_id, job_id))
        except Exception as restore_error:
            recovery = {
                "status": "failed", "verified": False,
                "error_type": type(restore_error).__name__,
                "sqlite_error": getattr(restore_error, "sqlite_errorname", None),
                "projection": getattr(restore_error, "reward_restore_projection", "unknown"),
            }
            report = self._failure_report(error, trace_id=trace_id, job_id=job_id,
                                          failed_stage=failed_stage, pull=pull_diagnostics, recovery=recovery)
            with self.store._transact() as conn:
                conn.execute(
                    "UPDATE server_reward_rebuild_jobs SET status='failed',error=?,pull_diagnostics_json=?,failure_report_json=?,updated_at=? WHERE user_id=? AND id=?",
                    (str(error), self._diagnostic_json(pull_diagnostics), self._diagnostic_json(report), now, user_id, job_id),
                )
        log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id, stage="restore",
                  event="finish", outcome="success" if recovery["verified"] else "failure",
                  details=recovery, level=logging.WARNING)
        return report

    def _clone_to_temp(self):
        handle = tempfile.NamedTemporaryFile(prefix="mtl-reward-candidate-", suffix=".db", delete=False)
        path = handle.name
        handle.close()
        source = self.store._connect()
        target = sqlite3.connect(path)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        return path

    def build_and_publish(self, user_id, job_id, pull_diagnostics, retry_count=0):
        job = self.get_job(user_id, job_id)
        trace_id = job["trace_id"]
        if not pull_diagnostics.get("ok") or pull_diagnostics.get("skipped"):
            raise RewardRebuildError("ticktick_pull_incomplete")
        snapshot_conn = self.store._connect()
        try:
            snapshot_row = snapshot_conn.execute(
                "SELECT snapshot_json FROM server_reward_rebuild_snapshots WHERE user_id=? AND job_id=?", (user_id, job_id),
            ).fetchone()
            old_rows = json.loads(snapshot_row["snapshot_json"])["tables"]["server_reward_ledger"] if snapshot_row else []
        finally:
            snapshot_conn.close()
        now = self.store.reward_wallet_service._now()
        conn = self.store._connect()
        try:
            frozen_facts = self._revision_facts(conn, user_id)
            frozen = hashlib.sha256(json.dumps(frozen_facts, ensure_ascii=False).encode("utf-8")).hexdigest()
        finally:
            conn.close()
        with self.store._transact() as conn:
            conn.execute("UPDATE server_reward_rebuild_jobs SET status='running',frozen_revision=?,pull_diagnostics_json=?,updated_at=? WHERE user_id=? AND id=?",
                         (frozen, self._diagnostic_json(pull_diagnostics), now, user_id, job_id))
        path = self._clone_to_temp()
        current_stage = "candidate_build"
        try:
            started = time.perf_counter()
            log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id,
                      stage="candidate_build", event="start", outcome="running")
            candidate_store = type(self.store)(db_path=path)
            report = RewardCandidateBuilder(candidate_store).build(user_id, job["statistics_start_date"])
            log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id,
                      stage="candidate_build", event="finish", outcome="success",
                      details={"ledger_rows": report.get("ledger_rows"), "balance": report.get("balance")})
            candidate = {}
            candidate_conn = candidate_store._connect()
            try:
                current_stage = "candidate_validate"
                log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id,
                          stage="candidate_validate", event="start", outcome="running")
                candidate = {table: self._rows(candidate_conn, table, user_id) for table in self.PROJECTION_TABLES}
                ledger_sum = sum(float(row["amount"]) for row in candidate["server_reward_ledger"])
                wallet = candidate["server_user_wallets"]
                if not wallet or abs(float(wallet[0]["balance"]) - ledger_sum) > 0.000001:
                    raise RewardRebuildError("candidate_wallet_mismatch")
                duplicate = candidate_conn.execute(
                    "SELECT id FROM server_reward_ledger WHERE user_id=? GROUP BY id HAVING COUNT(*)>1 LIMIT 1", (user_id,),
                ).fetchone()
                orphan = candidate_conn.execute(
                    """SELECT used.id FROM server_reward_ledger used LEFT JOIN server_reward_ledger acquired
                       ON acquired.user_id=used.user_id AND acquired.id=used.source_id AND acquired.source_type='reward_buy'
                       WHERE used.user_id=? AND used.source_type IN ('backpack_use','backpack_discard')
                         AND acquired.id IS NULL LIMIT 1""", (user_id,),
                ).fetchone()
                orphan_fragment = candidate_conn.execute(
                    """SELECT fragment.id FROM server_reward_fragments fragment
                       LEFT JOIN server_rewards reward ON reward.user_id=fragment.user_id AND reward.id=fragment.reward_id
                       WHERE fragment.user_id=? AND reward.id IS NULL LIMIT 1""", (user_id,),
                ).fetchone()
                duplicate_terminal = candidate_conn.execute(
                    """SELECT source_id FROM server_reward_ledger WHERE user_id=?
                       AND source_type IN ('backpack_use','backpack_discard')
                       GROUP BY source_id HAVING COUNT(*)>1 LIMIT 1""", (user_id,),
                ).fetchone()
                single_fragment_types = tuple(sorted(self.SINGLE_FRAGMENT_EVENT_TYPES))
                single_fragment_placeholders = ",".join("?" for _ in single_fragment_types)
                fragment_types = tuple(sorted(self.FRAGMENT_EVENT_TYPES))
                fragment_placeholders = ",".join("?" for _ in fragment_types)
                orphan_backpack_event = candidate_conn.execute(
                    """SELECT event.id FROM server_backpack_events event
                       LEFT JOIN server_reward_ledger acquired ON acquired.user_id=event.user_id
                         AND acquired.id=event.ledger_id AND acquired.source_type='reward_buy'
                       WHERE event.user_id=? AND event.event_type<>'revoked'
                         AND event.event_type NOT GLOB 'fragment_*'
                         AND acquired.id IS NULL LIMIT 1""", (user_id,),
                ).fetchone()
                orphan_fragment_event = candidate_conn.execute(
                    f"""SELECT event.id FROM server_backpack_events event
                       LEFT JOIN server_reward_fragments fragment ON fragment.user_id=event.user_id
                         AND fragment.id=event.fragment_id AND fragment.reward_id=event.reward_id
                       LEFT JOIN server_rewards reward ON reward.user_id=event.user_id AND reward.id=event.reward_id
                       WHERE event.user_id=? AND event.event_type IN ({single_fragment_placeholders})
                         AND (fragment.id IS NULL OR reward.id IS NULL) LIMIT 1""",
                    (user_id, *single_fragment_types),
                ).fetchone()
                orphan_composed_event = candidate_conn.execute(
                    """SELECT event.id FROM server_backpack_events event
                       LEFT JOIN server_rewards reward ON reward.user_id=event.user_id AND reward.id=event.reward_id
                       LEFT JOIN server_reward_fragments fragment ON fragment.user_id=event.user_id
                         AND fragment.reward_id=event.reward_id AND fragment.compose_batch_id=event.fragment_id
                         AND fragment.status='consumed'
                       LEFT JOIN server_reward_ledger composed_reward ON composed_reward.user_id=event.user_id
                         AND composed_reward.source_type='reward_buy'
                         AND composed_reward.source_id='unlock:'||event.reward_id||':fragment:'||event.fragment_id
                       WHERE event.user_id=? AND event.event_type='fragment_composed'
                       GROUP BY event.id,event.quantity,reward.id
                       HAVING reward.id IS NULL OR MAX(composed_reward.id) IS NULL
                         OR event.quantity<=0 OR COUNT(fragment.id)<>event.quantity
                       LIMIT 1""", (user_id,),
                ).fetchone()
                unknown_fragment_event = candidate_conn.execute(
                    f"""SELECT id FROM server_backpack_events
                       WHERE user_id=? AND event_type GLOB 'fragment_*'
                         AND event_type NOT IN ({fragment_placeholders}) LIMIT 1""",
                    (user_id, *fragment_types),
                ).fetchone()
                if duplicate:
                    raise self._candidate_error("duplicate_ledger_id", duplicate["id"])
                if orphan:
                    raise self._candidate_error("orphan_terminal_ledger", orphan["id"])
                if orphan_fragment:
                    raise self._candidate_error("orphan_reward_fragment", orphan_fragment["id"])
                if duplicate_terminal:
                    raise self._candidate_error("duplicate_terminal_reference", duplicate_terminal["source_id"])
                if orphan_backpack_event:
                    raise self._candidate_error("orphan_backpack_event", orphan_backpack_event["id"])
                if orphan_fragment_event:
                    raise self._candidate_error("orphan_fragment_backpack_event", orphan_fragment_event["id"])
                if orphan_composed_event:
                    raise self._candidate_error("invalid_composed_fragment_event", orphan_composed_event["id"])
                if unknown_fragment_event:
                    raise self._candidate_error("unknown_fragment_backpack_event", unknown_fragment_event["id"])
                replayed_actions = 0
                skipped_action_ids = {
                    str(item["source_id"]) for item in report["skipped"]
                    if item["source"] in {"reward_purchase", "custom_spend", "manual_adjustment", "backpack_use", "backpack_discard"}
                }
                actions = candidate_conn.execute(
                    "SELECT id,payload_json FROM server_reward_action_events WHERE user_id=? AND substr(occurred_at,1,10)>=?",
                    (user_id, job["statistics_start_date"]),
                ).fetchall()
                for action in actions:
                    payload = json.loads(action["payload_json"] or "{}")
                    ledger_id = str(payload.get("ledger_id") or str(action["id"]).removeprefix("action:"))
                    exists = candidate_conn.execute(
                        "SELECT 1 FROM server_reward_ledger WHERE user_id=? AND id=?", (user_id, ledger_id),
                    ).fetchone()
                    if exists:
                        replayed_actions += 1
                    elif str(action["id"]) not in skipped_action_ids:
                        raise RewardRebuildError("candidate_action_coverage_incomplete")
                report["replayed_action_events"] = replayed_actions
                log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id,
                          stage="candidate_validate", event="finish", outcome="success",
                          details={"ledger_rows": len(candidate["server_reward_ledger"]), "balance": ledger_sum})
            finally:
                candidate_conn.close()
            log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id,
                      stage="publish", event="start", outcome="running")
            current_stage = "publish"
            with self.store._transact() as conn:
                current_facts = self._revision_facts(conn, user_id)
                current = hashlib.sha256(json.dumps(current_facts, ensure_ascii=False).encode("utf-8")).hexdigest()
                if current != frozen:
                    error = RewardRebuildError("behavior_revision_changed")
                    before = {row[0]: row[1:] for row in frozen_facts}
                    after = {row[0]: row[1:] for row in current_facts}
                    error.reward_rebuild_details = {
                        "chain": "publish", "check": "behavior_revision_changed",
                        "message_zh": "重建期间以下金币事实发生变化",
                        "changed_tables": [table for table in sorted(set(before) | set(after)) if before.get(table) != after.get(table)],
                    }
                    raise error
                for table, rows in candidate.items():
                    self._replace_rows(conn, table, user_id, rows)
                epoch_row = conn.execute("SELECT active_epoch FROM server_reward_rebuild_epochs WHERE user_id=?", (user_id,)).fetchone()
                epoch = (int(epoch_row["active_epoch"]) if epoch_row else 0) + 1
                published_version = self.store._record_server_change(
                    conn, user_id, "reward_rebuild_epoch", str(epoch), "upsert", {"epoch": epoch},
                )
                conn.execute("""INSERT INTO server_reward_rebuild_epochs(user_id,active_epoch,published_version,updated_at) VALUES (?,?,?,?)
                              ON CONFLICT(user_id) DO UPDATE SET active_epoch=excluded.active_epoch,
                              published_version=excluded.published_version,updated_at=excluded.updated_at""",
                             (user_id, epoch, published_version, now))
                report.update({
                    "epoch": epoch, "statistics_start_date": job["statistics_start_date"],
                    "old_ledger_rows": len(old_rows),
                    "old_balance": sum(float(row["amount"]) for row in old_rows),
                    "warnings": ["重算后余额为负，已保留真实消费行为"] if float(report["balance"]) < 0 else [],
                })
                conn.execute("UPDATE server_reward_rebuild_jobs SET status='succeeded',result_json=?,updated_at=? WHERE user_id=? AND id=?",
                             (json.dumps(report, ensure_ascii=False), now, user_id, job_id))
                conn.execute(
                    "DELETE FROM server_reward_rebuild_snapshots WHERE user_id=? AND job_id<>?", (user_id, job_id),
                )
            log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id,
                      stage="publish", event="finish", outcome="success",
                      elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
                      details={"epoch": report["epoch"], "ledger_rows": report["ledger_rows"], "balance": report["balance"]})
            return report
        except Exception as exc:
            if str(exc) == "behavior_revision_changed" and retry_count < 1:
                log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id,
                          stage="publish", event="retry", outcome="running",
                          details={"reason": "behavior_revision_changed", "retry": retry_count + 1,
                                   **getattr(exc, "reward_rebuild_details", {})}, level=logging.WARNING)
                return self.build_and_publish(user_id, job_id, pull_diagnostics, retry_count + 1)
            log_event(logger, trace_id=trace_id, job_id=job_id, user_id=user_id,
                      stage=current_stage, event="finish", outcome="failure",
                      details={"error_type": type(exc).__name__, "code": str(exc),
                               **getattr(exc, "reward_rebuild_details", {})}, level=logging.ERROR)
            try:
                exc.reward_rebuild_stage = current_stage
            except Exception:
                pass
            raise
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
