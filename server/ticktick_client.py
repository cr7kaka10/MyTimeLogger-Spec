# -*- coding: utf-8 -*-
"""
服务端 TickTick HTTP 客户端 (ticktick_client.py)
轻量级异步 HTTP 客户端，仅封装 TickTick OpenAPI 调用。
用于服务端 SyncHub 轮询滴答清单和推送变更。
"""

import asyncio
import logging
import os
import time
import httpx
from typing import Optional

try:
    from .logging_config import traced
except (ImportError, ValueError):
    from logging_config import traced

logger = logging.getLogger(__name__)


def task_operation_log_fields(*, request_id: str | None, operation: str, status: str, task_id: str | None = None, project_id: str | None = None, http_status: int | None = None, error_code: str | None = None) -> dict:
    """Return the only diagnostic fields permitted for a task operation."""
    return {"request_id": request_id, "operation": operation, "status": status, "task_id": task_id, "project_id": project_id, "http_status": http_status, "error_code": error_code}


class TickTickClient:
    """TickTick OpenAPI v1 异步客户端"""

    TASK_UPDATE_FIELDS = frozenset({
        "id", "projectId", "title", "content", "desc", "isAllDay", "startDate",
        "dueDate", "timeZone", "reminders", "tags", "repeatFlag", "priority",
        "sortOrder", "items",
    })

    def __init__(
        self,
        access_token: str,
        host: str = "dida365.com",
        verify_tls: bool | None = None,
        timeout_seconds: float | None = None,
        request_id: str | None = None,
    ):
        self.base_url = f"https://api.{host}/open/v1"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        if verify_tls is None:
            raw = os.getenv("TICKTICK_VERIFY_TLS", "false").strip().lower()
            verify_tls = raw not in ("0", "false", "no", "off")
        self.verify_tls = verify_tls
        self.request_id = request_id
        self.last_get_attempts = 0
        self.get_request_attempts = 0
        self._get_attempt_limit = 2
        if not self.verify_tls:
            logger.info("TickTick TLS certificate verification is disabled by configuration")
        self.timeout_seconds = timeout_seconds or float(os.getenv("TICKTICK_TIMEOUT_SECONDS", "15"))

    async def __aenter__(self):
        # 调用链路：SyncHub -> TickTickClient -> httpx.AsyncClient -> TickTick/Dida365 OpenAPI。
        # TLS/timeout 边界：生产默认校验证书；配置由 ticktick_config.py 集中读取后注入。
        self._client = httpx.AsyncClient(
            headers=self.headers, timeout=self.timeout_seconds, verify=self.verify_tls
        )
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    def set_get_attempt_limit(self, attempt_limit: int) -> None:
        """Limit the next idempotent GET so callers can share a request budget."""
        self._get_attempt_limit = max(1, min(2, int(attempt_limit)))

    async def _get(
        self, path: str, params: dict = None, endpoint_template: str | None = None,
    ) -> dict | list:
        url = f"{self.base_url}{path}"
        endpoint = endpoint_template or path
        started = time.perf_counter()
        attempt_limit = self._get_attempt_limit
        self._get_attempt_limit = 2
        self.last_get_attempts = 0
        for attempt in range(1, attempt_limit + 1):
            self.last_get_attempts = attempt
            self.get_request_attempts += 1
            logger.info(
                "[TickTickClient] request start request_id=%s method=GET path=%s attempt=%s timeout_seconds=%s params_keys=%s",
                self.request_id, endpoint, attempt, self.timeout_seconds, sorted((params or {}).keys()),
            )
            try:
                resp = await self._client.get(url, params=params)
                resp.raise_for_status()
                logger.info(
                    "[TickTickClient] request ok request_id=%s method=GET path=%s attempt=%s status=%s elapsed_ms=%s",
                    self.request_id, endpoint, attempt, resp.status_code, round((time.perf_counter() - started) * 1000, 2),
                )
                return resp.json()
            except (httpx.ReadTimeout, httpx.NetworkError) as exc:
                logger.warning(
                    "[TickTickClient] request error request_id=%s method=GET path=%s attempt=%s timeout_seconds=%s error_type=%s elapsed_ms=%s",
                    self.request_id, endpoint, attempt, self.timeout_seconds, type(exc).__name__, round((time.perf_counter() - started) * 1000, 2),
                )
                if attempt < attempt_limit:
                    await asyncio.sleep(0.1)
                    continue
                raise
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "[TickTickClient] request failed request_id=%s method=GET path=%s attempt=%s status=%s error_type=HTTPStatusError elapsed_ms=%s",
                    self.request_id, endpoint, attempt, exc.response.status_code if exc.response else None, round((time.perf_counter() - started) * 1000, 2),
                )
                raise
            except Exception as exc:
                logger.warning(
                    "[TickTickClient] request error request_id=%s method=GET path=%s attempt=%s timeout_seconds=%s error_type=%s elapsed_ms=%s",
                    self.request_id, endpoint, attempt, self.timeout_seconds, type(exc).__name__, round((time.perf_counter() - started) * 1000, 2),
                )
                raise

    @traced("ticktick.post")
    async def _post(self, path: str, body: dict = None) -> dict:
        url = f"{self.base_url}{path}"
        started = time.perf_counter()
        logger.info(
            "[TickTickClient] request start request_id=%s method=POST path=%s body_keys=%s",
            self.request_id,
            path,
            sorted((body or {}).keys()),
        )
        try:
            resp = await self._client.post(url, json=body)
            resp.raise_for_status()
            logger.info(
                "[TickTickClient] request ok request_id=%s method=POST path=%s status=%s elapsed_ms=%s",
                self.request_id,
                path,
                resp.status_code,
                round((time.perf_counter() - started) * 1000, 2),
            )
            return resp.json() if resp.text else {}
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "[TickTickClient] request failed request_id=%s method=POST path=%s status=%s elapsed_ms=%s",
                self.request_id,
                path,
                exc.response.status_code if exc.response else None,
                round((time.perf_counter() - started) * 1000, 2),
            )
            raise
        except Exception as exc:
            logger.warning(
                "[TickTickClient] request error request_id=%s method=POST path=%s error_type=%s elapsed_ms=%s",
                self.request_id,
                path,
                type(exc).__name__,
                round((time.perf_counter() - started) * 1000, 2),
            )
            raise

    @traced("ticktick.delete")
    async def _delete(self, path: str) -> dict:
        url = f"{self.base_url}{path}"
        started = time.perf_counter()
        logger.info(
            "[TickTickClient] request start request_id=%s method=DELETE path=%s",
            self.request_id,
            path,
        )
        try:
            resp = await self._client.delete(url)
            resp.raise_for_status()
            logger.info(
                "[TickTickClient] request ok request_id=%s method=DELETE path=%s status=%s elapsed_ms=%s",
                self.request_id,
                path,
                resp.status_code,
                round((time.perf_counter() - started) * 1000, 2),
            )
            return resp.json() if resp.text else {}
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "[TickTickClient] request failed request_id=%s method=DELETE path=%s status=%s elapsed_ms=%s",
                self.request_id,
                path,
                exc.response.status_code if exc.response else None,
                round((time.perf_counter() - started) * 1000, 2),
            )
            raise
        except Exception as exc:
            logger.warning(
                "[TickTickClient] request error request_id=%s method=DELETE path=%s error_type=%s elapsed_ms=%s",
                self.request_id,
                path,
                type(exc).__name__,
                round((time.perf_counter() - started) * 1000, 2),
            )
            raise

    # ========== 项目 & 任务 ==========

    async def get_projects(self) -> list[dict]:
        return await self._get("/project")

    async def get_project_data(self, project_id: str) -> dict:
        return await self._get(f"/project/{project_id}/data", endpoint_template="/project/{project_id}/data")

    async def get_task(self, project_id: str, task_id: str) -> Optional[dict]:
        try:
            return await self._get(
                f"/project/{project_id}/task/{task_id}",
                endpoint_template="/project/{project_id}/task/{task_id}",
            )
        except Exception:
            return None

    @staticmethod
    def _task_title(title: str) -> str:
        normalized = str(title or "").strip()
        if not normalized:
            raise ValueError("validation_error:title_required")
        return normalized

    async def create_task(self, title: str, due_date: str | None = None, tags: list[str] | None = None) -> dict:
        payload = {"title": self._task_title(title)}
        if due_date:
            payload.update({"dueDate": due_date, "timeZone": "Asia/Shanghai", "isAllDay": True})
        if tags:
            payload["tags"] = tags
        task = await self._post("/task", payload)
        if not task.get("id") or not task.get("projectId"):
            raise ValueError("provider_response_missing_identifiers")
        return task

    async def complete_task(self, project_id: str, task_id: str) -> dict:
        return await self._post(f"/project/{project_id}/task/{task_id}/complete")

    async def update_task(self, project_id: str, task_id: str, task: dict | str) -> dict:
        source = {"title": task} if isinstance(task, str) else dict(task or {})
        payload = {key: value for key, value in source.items() if key in self.TASK_UPDATE_FIELDS}
        payload["id"] = str(task_id)
        payload["projectId"] = str(project_id)
        payload["title"] = self._task_title(payload.get("title"))
        return await self._post(f"/task/{task_id}", payload)

    async def delete_task(self, project_id: str, task_id: str) -> dict:
        return await self._delete(f"/project/{project_id}/task/{task_id}")

    async def is_task_active(self, project_id: str, task_id: str) -> bool:
        project = await self.get_project_data(project_id)
        return any(str(task.get("id")) == str(task_id) for task in project.get("tasks", []))

    @staticmethod
    def normalize_completed_tasks_page(payload: dict | list) -> dict:
        """Normalize legacy lists and provider-declared pagination without guessing cursors."""
        if isinstance(payload, list):
            return {"records": payload, "next_page": None}
        if not isinstance(payload, dict):
            raise ValueError("completed_page_invalid_payload")

        records = next(
            (payload[key] for key in ("records", "tasks", "items", "data") if isinstance(payload.get(key), list)),
            None,
        )
        if records is None:
            raise ValueError("completed_page_missing_records")

        has_more = next((payload[key] for key in ("hasMore", "hasNext", "more") if key in payload), None)
        next_page = None
        if has_more is not False:
            raw_next = payload.get("next")
            if isinstance(raw_next, dict) and raw_next:
                next_page = dict(raw_next)
            elif raw_next not in (None, ""):
                next_page = {"cursor": raw_next}
            else:
                for response_key, request_key in (
                    ("nextCursor", "cursor"), ("nextPageToken", "pageToken"), ("nextPage", "page")
                ):
                    value = payload.get(response_key)
                    if value not in (None, ""):
                        next_page = {request_key: value}
                        break
        if has_more is True and next_page is None:
            raise ValueError("completed_page_missing_continuation")
        return {"records": records, "next_page": next_page}

    async def get_completed_tasks(self, start_time: str, continuation: dict | None = None) -> dict:
        body = {"start": start_time}
        if continuation:
            if not isinstance(continuation, dict):
                raise ValueError("completed_page_invalid_continuation")
            body.update(continuation)
        payload = await self._post("/task/completed", body)
        return self.normalize_completed_tasks_page(payload)

    # ========== 习惯 ==========

    async def get_habits(self) -> list[dict]:
        return await self._get("/habit")

    async def get_habit_checkins(
        self, habit_ids: list[str], from_stamp: str, to_stamp: str
    ) -> list[dict]:
        params = {
            "habitIds": ",".join(habit_ids),
            "from": from_stamp,
            "to": to_stamp,
        }
        return await self._get("/habit/checkins", params)

    async def checkin_habit(
        self, habit_id: str, stamp: str, status: int = 0, value: float = 1.0
    ) -> dict:
        payload = {"stamp": int(stamp), "status": status, "value": value}
        return await self._post(f"/habit/{habit_id}/checkin", payload)

    async def get_habit_sections(self) -> list[dict]:
        """获取习惯分组列表"""
        return await self._get("/habit/sections")
