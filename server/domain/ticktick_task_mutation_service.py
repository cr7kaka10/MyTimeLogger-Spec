from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime

import httpx

from server.ticktick_client import task_operation_log_fields
from server.domain.ticktick_task_dates import TaskTimezoneUnavailableError, normalize_task_date, validate_task_date_range

logger = logging.getLogger(__name__)


class TickTickTaskMutationService:
    """External-first task commands; a request id is the idempotency boundary."""

    def __init__(self, ledger):
        self.ledger = ledger
        self._locks: dict[tuple[int, str], asyncio.Lock] = {}

    async def create(self, user_id: int, request_id: str, title: str, client, due_date: object = None, tags: object = None) -> dict:
        title = str(title or "").strip()
        if not title:
            return {"request_id": request_id, "status": "failed", "error_code": "validation_error"}
        try:
            due_date = self._create_due_date(due_date)
            tags = self._create_tags(tags)
        except TaskTimezoneUnavailableError:
            return {"request_id": request_id, "status": "failed", "error_code": "task_timezone_unavailable"}
        except ValueError as exc:
            return {"request_id": request_id, "status": "failed", "error_code": str(exc).split(":", 1)[0]}
        operation, inserted = self.ledger.create_or_get(user_id, request_id, "create", title_fingerprint=self._create_fingerprint(title, due_date, tags))
        if not inserted:
            return operation
        async with self._lock(user_id, "default-inbox"):
            self.ledger.begin_attempt(user_id, request_id)
            try:
                created = await client.create_task(title, due_date, tags) if tags else await client.create_task(title, due_date) if due_date else await client.create_task(title)
                task_id, project_id = created["id"], created["projectId"]
                actual = await client.get_task(project_id, task_id)
                expected = {"title": title, **({"dueDate": due_date} if due_date else {}), **({"tags": tags} if tags else {})}
                if actual and str(actual.get("id")) == str(task_id) and all(self._task_field(actual, key) == value for key, value in expected.items()):
                    return self._mark(user_id, request_id, "confirmed", result_task_id=task_id, project_id=project_id, http_status=200)
                return self._mark(user_id, request_id, "unknown", result_task_id=task_id, project_id=project_id, error_code="provider_readback_unconfirmed")
            except httpx.TimeoutException:
                return self._mark(user_id, request_id, "unknown", error_code="provider_timeout")
            except httpx.RequestError:
                return self._mark(user_id, request_id, "unknown", error_code="provider_request_unknown")
            except httpx.HTTPStatusError:
                return self._mark(user_id, request_id, "failed", error_code="provider_request_failed")
            except ValueError as exc:
                return self._mark(user_id, request_id, "failed", error_code=str(exc).split(":", 1)[0])
            except Exception:
                return self._mark(user_id, request_id, "failed", error_code="provider_request_failed")

    async def update_title(self, user_id: int, request_id: str, project_id: str, task_id: str, title: str, client, expected_title: str | None = None) -> dict:
        expected = {"title": expected_title} if expected_title is not None else {}
        return await self.update(user_id, request_id, project_id, task_id, {"title": title}, expected, client)

    async def update(self, user_id: int, request_id: str, project_id: str, task_id: str, patch: dict, expected: dict, client) -> dict:
        patch = {key: value for key, value in dict(patch or {}).items() if key in {"title", "startDate", "dueDate"}}
        if not patch or ("title" in patch and not str(patch["title"] or "").strip()):
            return {"request_id": request_id, "status": "failed", "error_code": "validation_error"}
        expected = {key: value for key, value in dict(expected or {}).items() if key in {"title", "startDate", "dueDate", "isAllDay", "timeZone", "repeatFlag"}}
        operation, inserted = self.ledger.create_or_get(user_id, request_id, "update", task_id=task_id, project_id=project_id, expected_fingerprint=self._fingerprint(expected), patch_fingerprint=self._fingerprint(patch))
        if not inserted:
            return operation
        async with self._lock(user_id, project_id):
            self.ledger.begin_attempt(user_id, request_id)
            before = await client.get_task(project_id, task_id)
            if not before:
                return self._mark(user_id, request_id, "failed", error_code="provider_task_not_found")
            if str(before.get("id")) != str(task_id) or str(before.get("projectId")) != str(project_id):
                return self._mark(user_id, request_id, "failed", error_code="provider_task_not_found")
            if int(before.get("status") or 0) != 0:
                return self._mark(user_id, request_id, "failed", error_code="provider_task_completed")
            if before.get("repeatFlag"):
                return self._mark(user_id, request_id, "failed", error_code="provider_task_repeating")
            try:
                if any(self._task_field(before, key) != self._task_field(expected, key) for key in expected):
                    return self._mark(user_id, request_id, "conflict", error_code="provider_task_conflict")
                desired = dict(before)
                desired.update(patch)
                desired["startDate"], desired["dueDate"] = validate_task_date_range(desired.get("startDate"), desired.get("dueDate"), desired.get("timeZone"))
            except TaskTimezoneUnavailableError:
                return self._mark(user_id, request_id, "failed", error_code="task_timezone_unavailable")
            except ValueError as exc:
                return self._mark(user_id, request_id, "failed", error_code=str(exc).split(":", 1)[0])
            try:
                await client.update_task(project_id, task_id, desired)
                actual = await client.get_task(project_id, task_id)
                status = "confirmed" if actual and all(self._task_field(actual, key) == self._task_field(desired, key) for key in patch) else "failed"
                return self._mark(user_id, request_id, status, result_task_id=task_id, http_status=200 if status == "confirmed" else None, error_code=None if status == "confirmed" else "provider_readback_unconfirmed")
            except TaskTimezoneUnavailableError:
                return self._mark(user_id, request_id, "failed", error_code="task_timezone_unavailable")
            except httpx.TimeoutException:
                actual = await client.get_task(project_id, task_id)
                status = "confirmed" if actual and all(self._task_field(actual, key) == self._task_field(desired, key) for key in patch) else "unknown"
                return self._mark(user_id, request_id, status, result_task_id=task_id if status == "confirmed" else None, http_status=200 if status == "confirmed" else None, error_code=None if status == "confirmed" else "provider_timeout")
            except Exception:
                return self._mark(user_id, request_id, "failed", error_code="provider_request_failed")

    async def reconcile_create(self, user_id: int, request_id: str, client) -> dict:
        operation = self.ledger.get(user_id, request_id)
        if not operation or operation.get("operation") != "create" or operation.get("status") != "unknown":
            return operation or {"request_id": request_id, "status": "failed", "error_code": "operation_not_reconcilable"}
        project_id = operation.get("project_id")
        if not project_id or not operation.get("title_fingerprint"):
            return operation
        async with self._lock(user_id, project_id):
            project = await client.get_project_data(project_id)
            matches = [task for task in project.get("tasks", []) if self._create_fingerprint(task.get("title", ""), self._task_field(task, "dueDate"), self._task_field(task, "tags")) == operation["title_fingerprint"]]
            if len(matches) != 1:
                return operation
            candidate = matches[0]
            actual = await client.get_task(project_id, candidate.get("id"))
            if actual and self._create_fingerprint(actual.get("title", ""), self._task_field(actual, "dueDate"), self._task_field(actual, "tags")) == operation["title_fingerprint"]:
                return self._mark(user_id, request_id, "confirmed", result_task_id=str(candidate["id"]), project_id=project_id, http_status=200)
            return operation

    async def delete(self, user_id: int, request_id: str, project_id: str, task_id: str, client) -> dict:
        operation, inserted = self.ledger.create_or_get(user_id, request_id, "delete", task_id=task_id, project_id=project_id)
        if not inserted:
            return operation
        async with self._lock(user_id, project_id):
            self.ledger.begin_attempt(user_id, request_id)
            try:
                await client.delete_task(project_id, task_id)
                active = await client.is_task_active(project_id, task_id)
                return self._mark(user_id, request_id, "failed" if active else "confirmed", result_task_id=task_id, http_status=200 if not active else None, error_code="provider_readback_unconfirmed" if active else None)
            except Exception:
                try:
                    if not await client.is_task_active(project_id, task_id):
                        return self._mark(user_id, request_id, "confirmed", result_task_id=task_id, http_status=404)
                except Exception:
                    pass
                return self._mark(user_id, request_id, "failed", error_code="provider_request_failed")

    def _lock(self, user_id: int, project_id: str) -> asyncio.Lock:
        return self._locks.setdefault((int(user_id), str(project_id)), asyncio.Lock())

    def _mark(self, user_id: int, request_id: str, status: str, **kwargs) -> dict:
        result = self.ledger.mark(user_id, request_id, status, **kwargs)
        logger.info("TickTick task operation %s", task_operation_log_fields(request_id=request_id, operation=result["operation"], status=status, task_id=result.get("task_id"), project_id=result.get("project_id"), http_status=result.get("http_status"), error_code=result.get("error_code")))
        return result

    @staticmethod
    def _fingerprint(value: object) -> str:
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()

    @staticmethod
    def _create_due_date(value: object) -> str | None:
        if value is None or str(value).strip() == "":
            return None
        raw = str(value).strip()
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("validation_error:invalid_task_date") from exc
        if parsed.strftime("%Y-%m-%d") != raw:
            raise ValueError("validation_error:invalid_task_date")
        return normalize_task_date(f"{raw}T00:00:00", "Asia/Shanghai")

    @staticmethod
    def _create_tags(value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("validation_error:invalid_task_tags")
        return list(dict.fromkeys(str(tag).strip() for tag in value if str(tag).strip()))

    @classmethod
    def _create_fingerprint(cls, title: object, due_date: object, tags: object = None) -> str:
        normalized_tags = cls._create_tags(tags)
        if not normalized_tags:
            return cls._fingerprint(title) if not due_date else f"dated:{cls._fingerprint({'title': str(title or '').strip(), 'dueDate': due_date})}"
        payload = {"title": str(title or "").strip(), **({"dueDate": due_date} if due_date else {}), **({"tags": normalized_tags} if normalized_tags else {})}
        return f"tagged:{cls._fingerprint(payload)}"

    @staticmethod
    def _task_field(task: dict, key: str):
        value = task.get(key)
        if key in {"startDate", "dueDate"}:
            return normalize_task_date(value, task.get("timeZone"))
        if key == "title":
            return str(value or "").strip()
        if key == "tags":
            return TickTickTaskMutationService._create_tags(value)
        return value or ""
