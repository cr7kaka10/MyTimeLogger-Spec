from __future__ import annotations

import asyncio
from .diet_habit_migration_service import DietHabitMigrationService
from .exercise_v4_service import is_exercise_rest_day

class HabitUnavailable(ValueError):
    pass


class HabitCheckinCommandService:
    """MyTimeLogger 本地习惯的幂等目标状态命令。"""

    def __init__(self, transact, habit_domain_service, command_store):
        self._transact = transact
        self._habits = habit_domain_service
        self._commands = command_store
        self._locks: dict[tuple[int, str, str], asyncio.Lock] = {}

    async def execute(self, user_id: int, idempotency_key: str, habit_id: str, checkin_date: str, desired_status: int, client=None) -> dict:
        command, _ = self._commands.create_or_get(user_id, idempotency_key, habit_id, checkin_date, desired_status)
        if not self._matches(command, habit_id, checkin_date, desired_status):
            return {**command, "status": "failed", "error_code": "idempotency_key_conflict"}
        if command["status"] in {"confirmed", "failed"}:
            return command
        async with self._lock(user_id, habit_id, checkin_date):
            command = self._commands.get(user_id, idempotency_key) or command
            if command["status"] in {"confirmed", "failed"}:
                return command
            if command["status"] == "provider_confirmed":
                return self._finalize(user_id, idempotency_key, habit_id, checkin_date, desired_status)
            try:
                applicable = self._can_apply(user_id, habit_id, checkin_date, desired_status)
            except HabitUnavailable as exc:
                return self._commands.mark(user_id, idempotency_key, "failed", error_code=str(exc))
            except ValueError as exc:
                code = str(exc) if str(exc).startswith("timed_habit_") else "cancel_not_allowed"
                return self._commands.mark(user_id, idempotency_key,
                    "failed" if code.startswith("timed_habit_") else "retryable_failed", error_code=code)
            if not applicable:
                return self._commands.mark(user_id, idempotency_key, "retryable_failed", error_code="cancel_not_allowed")
            self._commands.begin_attempt(user_id, idempotency_key)
            self._commands.mark(user_id, idempotency_key, "provider_confirmed")
            return self._finalize(user_id, idempotency_key, habit_id, checkin_date, desired_status)

    def _finalize(self, user_id: int, idempotency_key: str, habit_id: str, checkin_date: str, desired_status: int) -> dict:
        finalize_error = None
        try:
            with self._transact() as conn:
                conn.execute("BEGIN IMMEDIATE")
                self._require_active(conn, user_id, habit_id)
                self._require_system_day(conn, user_id, habit_id, checkin_date, desired_status)
                already_completed = False
                if int(desired_status) == 2:
                    existing = conn.execute(
                        "SELECT id,status FROM server_habit_checkins WHERE user_id=? AND habit_id=? AND COALESCE(checkin_date,date)=?",
                        (user_id, habit_id, checkin_date),
                    ).fetchone()
                    already_completed = bool(existing and int(existing["status"] or 0) == 2)
                    if (not existing or int(existing["status"] or 0) != 2) and not self._habits.checkin_habit_in_txn(
                            conn, user_id, habit_id, checkin_date, replace_failed=True):
                        self._commands.mark_in_txn(conn, user_id, idempotency_key, "retryable_failed", error_code="habit_not_found")
                        finalize_error = "habit_not_found"
                elif int(desired_status) == 1:
                    if not self._habits.mark_failed_habit_in_txn(conn, user_id, habit_id, checkin_date):
                        self._commands.mark_in_txn(conn, user_id, idempotency_key, "retryable_failed", error_code="habit_not_found")
                        finalize_error = "habit_not_found"
                else:
                    self._habits.cancel_checkin_habit_in_txn(conn, user_id, habit_id, checkin_date)
                if not finalize_error:
                    self._commands.mark_in_txn(conn, user_id, idempotency_key, "confirmed",
                                               error_code="already_completed" if already_completed else None)
        except HabitUnavailable as exc:
            return self._commands.mark(user_id, idempotency_key, "failed", error_code=str(exc))
        except ValueError as exc:
            code = str(exc) if str(exc).startswith("timed_habit_") else "cancel_not_allowed"
            return self._commands.mark(user_id, idempotency_key,
                "failed" if code.startswith("timed_habit_") else "retryable_failed", error_code=code)
        return self._commands.get(user_id, idempotency_key)

    def _can_apply(self, user_id: int, habit_id: str, checkin_date: str, desired_status: int) -> bool:
        with self._transact() as conn:
            self._require_active(conn, user_id, habit_id)
            self._require_system_day(conn, user_id, habit_id, checkin_date, desired_status)
            self._habits.timed_checkin_guard(conn, user_id, habit_id, checkin_date, desired_status)
            if int(desired_status) == 2:
                return True
            if int(desired_status) == 1:
                return self._habits.can_mark_failed_in_txn(conn, user_id, habit_id, checkin_date)
            return self._habits.can_cancel_checkin_in_txn(conn, user_id, habit_id, checkin_date)

    def _lock(self, user_id: int, habit_id: str, checkin_date: str) -> asyncio.Lock:
        return self._locks.setdefault((int(user_id), str(habit_id), str(checkin_date)), asyncio.Lock())

    @staticmethod
    def _require_active(conn, user_id, habit_id):
        habit = conn.execute("SELECT is_active,source FROM server_habits WHERE user_id=? AND id=?", (user_id, habit_id)).fetchone()
        if not habit:
            raise HabitUnavailable("habit_not_found")
        if habit["source"] not in {"local", "system"}:
            raise HabitUnavailable("provider_habit_sync_disabled")
        if habit["is_active"] != 0:
            raise HabitUnavailable("habit_archived")

    @staticmethod
    def _require_system_day(conn, user_id, habit_id, date, desired_status):
        row = conn.execute("SELECT source FROM server_habits WHERE user_id=? AND id=?", (user_id, habit_id)).fetchone()
        if row["source"] != "system":
            return
        if not str(habit_id).startswith("diet-v5:") or not DietHabitMigrationService.active(conn, user_id, date) or is_exercise_rest_day(conn, user_id, "v5", date):
            raise HabitUnavailable("diet_habit_unavailable")
        if int(desired_status) != 2:
            raise HabitUnavailable("diet_habit_auto_failure_only")

    @staticmethod
    def _matches(command: dict, habit_id: str, checkin_date: str, desired_status: int) -> bool:
        return (
            str(command.get("habit_id")) == str(habit_id)
            and str(command.get("checkin_date")) == str(checkin_date)
            and int(command.get("desired_status") or 0) == int(desired_status)
        )
