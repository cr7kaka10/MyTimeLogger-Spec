from __future__ import annotations

import asyncio

import httpx


class HabitCheckinCommandService:
    """TickTick 外部优先的习惯目标状态命令。"""

    def __init__(self, transact, habit_domain_service, command_store):
        self._transact = transact
        self._habits = habit_domain_service
        self._commands = command_store
        self._locks: dict[tuple[int, str, str], asyncio.Lock] = {}

    async def execute(self, user_id: int, idempotency_key: str, habit_id: str, checkin_date: str, desired_status: int, client=None) -> dict:
        command, _ = self._commands.create_or_get(user_id, idempotency_key, habit_id, checkin_date, desired_status)
        if not self._matches(command, habit_id, checkin_date, desired_status):
            return {**command, "status": "failed", "error_code": "idempotency_key_conflict"}
        if command["status"] == "confirmed":
            return command
        async with self._lock(user_id, habit_id, checkin_date):
            command = self._commands.get(user_id, idempotency_key) or command
            if command["status"] == "confirmed":
                return command
            if command["status"] == "provider_confirmed":
                return self._finalize(user_id, idempotency_key, habit_id, checkin_date, desired_status)
            try:
                applicable = self._can_apply(user_id, habit_id, checkin_date, desired_status)
            except ValueError:
                return self._commands.mark(user_id, idempotency_key, "retryable_failed", error_code="cancel_not_allowed")
            if not applicable:
                return self._commands.mark(user_id, idempotency_key, "retryable_failed", error_code="cancel_not_allowed")
            self._commands.begin_attempt(user_id, idempotency_key)
            if self._requires_provider(habit_id):
                if client is None:
                    return self._commands.mark(user_id, idempotency_key, "retryable_failed", error_code="provider_not_configured")
                try:
                    await client.checkin_habit(
                        self._provider_habit_id(user_id, habit_id),
                        str(checkin_date).replace("-", ""),
                        int(desired_status),
                        1.0 if int(desired_status) == 2 else 0.0,
                    )
                except httpx.TimeoutException:
                    return self._commands.mark(user_id, idempotency_key, "retryable_failed", error_code="provider_timeout")
                except Exception:
                    return self._commands.mark(user_id, idempotency_key, "retryable_failed", error_code="provider_request_failed")
            self._commands.mark(user_id, idempotency_key, "provider_confirmed")
            return self._finalize(user_id, idempotency_key, habit_id, checkin_date, desired_status)

    def _finalize(self, user_id: int, idempotency_key: str, habit_id: str, checkin_date: str, desired_status: int) -> dict:
        finalize_error = None
        try:
            with self._transact() as conn:
                if int(desired_status) == 2:
                    existing = conn.execute(
                        "SELECT id FROM server_habit_checkins WHERE user_id=? AND habit_id=? AND COALESCE(checkin_date,date)=?",
                        (user_id, habit_id, checkin_date),
                    ).fetchone()
                    if not existing and not self._habits.checkin_habit_in_txn(conn, user_id, habit_id, checkin_date):
                        self._commands.mark_in_txn(conn, user_id, idempotency_key, "retryable_failed", error_code="habit_not_found")
                        finalize_error = "habit_not_found"
                elif int(desired_status) == 1:
                    if not self._habits.mark_failed_habit_in_txn(conn, user_id, habit_id, checkin_date):
                        self._commands.mark_in_txn(conn, user_id, idempotency_key, "retryable_failed", error_code="habit_not_found")
                        finalize_error = "habit_not_found"
                else:
                    self._habits.cancel_checkin_habit_in_txn(conn, user_id, habit_id, checkin_date)
                if not finalize_error:
                    self._commands.mark_in_txn(conn, user_id, idempotency_key, "confirmed")
        except ValueError:
            return self._commands.mark(user_id, idempotency_key, "retryable_failed", error_code="cancel_not_allowed")
        return self._commands.get(user_id, idempotency_key)

    def _can_apply(self, user_id: int, habit_id: str, checkin_date: str, desired_status: int) -> bool:
        with self._transact() as conn:
            habit = conn.execute("SELECT id FROM server_habits WHERE user_id=? AND id=?", (user_id, habit_id)).fetchone()
            if not habit:
                return False
            if int(desired_status) == 2:
                return True
            if int(desired_status) == 1:
                return self._habits.can_mark_failed_in_txn(conn, user_id, habit_id, checkin_date)
            return self._habits.can_cancel_checkin_in_txn(conn, user_id, habit_id, checkin_date)

    def _lock(self, user_id: int, habit_id: str, checkin_date: str) -> asyncio.Lock:
        return self._locks.setdefault((int(user_id), str(habit_id), str(checkin_date)), asyncio.Lock())

    @staticmethod
    def _matches(command: dict, habit_id: str, checkin_date: str, desired_status: int) -> bool:
        return (
            str(command.get("habit_id")) == str(habit_id)
            and str(command.get("checkin_date")) == str(checkin_date)
            and int(command.get("desired_status") or 0) == int(desired_status)
        )

    @staticmethod
    def _requires_provider(habit_id: str) -> bool:
        return not str(habit_id).startswith("local_")

    @staticmethod
    def _provider_habit_id(user_id: int, habit_id: str) -> str:
        prefix = f"ticktick:{user_id}:"
        value = str(habit_id)
        return value[len(prefix):] if value.startswith(prefix) else value
