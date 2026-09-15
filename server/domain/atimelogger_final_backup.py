from __future__ import annotations

from datetime import datetime, timedelta, timezone
import asyncio
import json
from typing import Any

import requests


BASE_URL = "https://app.atimelogger.pro"
BEIJING_TZ = timezone(timedelta(hours=8))


class ATimeLoggerRemoteError(RuntimeError):
    def __init__(self, code: str, step: str = "remote.request"):
        super().__init__(code)
        self.code = code
        self.step = step


def _parsed(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BEIJING_TZ)
    return parsed


def _utc(value: str) -> str:
    return (
        _parsed(value).astimezone(timezone.utc)
        .isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


def _second(value: str) -> int:
    return int(_parsed(value).timestamp())


def _epoch(value: Any) -> int | None:
    if isinstance(value, (int, float)):
        return int(value)
    if value:
        try:
            return _second(str(value))
        except (TypeError, ValueError):
            return None
    return None


def _items(value: Any, *keys: str) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in keys:
            if isinstance(value.get(key), list):
                return [item for item in value[key] if isinstance(item, dict)]
    return []


class ATimeLoggerFinalClient:
    def __init__(self, token: str, requester=None):
        self.token = token
        self._session = requests.Session() if requester is None else None
        self.requester = requester or self._session.request

    def _request_once(self, method: str, path: str, body=None, *, step: str):
        try:
            response = self.requester(
                method, f"{BASE_URL}{path}", json=body,
                headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
                timeout=30, verify=False,
            )
            if response.status_code in (401, 403):
                raise ATimeLoggerRemoteError("auth_required", step)
            if response.status_code >= 400:
                raise ATimeLoggerRemoteError(f"remote_http_{response.status_code}", step)
            response.raise_for_status()
            return response.json() if response.content else {}
        except ATimeLoggerRemoteError:
            raise
        except requests.Timeout as exc:
            raise ATimeLoggerRemoteError("remote_timeout", step) from exc
        except (requests.RequestException, ValueError) as exc:
            raise ATimeLoggerRemoteError("remote_request_failed", step) from exc

    def _request(self, method: str, path: str, body=None, *, step: str):
        retry_safe = step in {
            "type.list", "interval.query", "activity.running.list",
            "activity.full.get", "activity.full.update",
        }
        attempts = 3 if retry_safe else 1
        for attempt in range(attempts):
            try:
                return self._request_once(method, path, body, step=step)
            except ATimeLoggerRemoteError as error:
                transient = error.code in {"remote_timeout", "remote_request_failed"}
                if not retry_safe or not transient or attempt + 1 >= attempts:
                    raise
        raise ATimeLoggerRemoteError("remote_request_failed", step)

    def list_types(self) -> list[dict]:
        return _items(
            self._request("GET", "/api/types", step="type.list"),
            "types", "content", "data",
        )

    def find_interval(self, date: str, type_id: str, start: str, end: str) -> dict | None:
        result = self._request(
            "POST", "/api/intervals?page=0&size=100",
            {"from": date, "to": date, "timezone": "Asia/Shanghai"},
            step="interval.query",
        )
        for day in _items(result, "content", "data"):
            for interval in _items(day.get("intervals", [])):
                remote_start = interval.get("from")
                remote_end = interval.get("to")
                if remote_start is None:
                    remote_start = _second(interval.get("start"))
                if remote_end is None:
                    remote_end = _second(interval.get("finish"))
                if (str(interval.get("typeId")) == str(type_id)
                        and abs(int(remote_start) - _second(start)) <= 2
                        and abs(int(remote_end) - _second(end)) <= 2):
                    return interval
        return None

    def find_interval_for_activity(self, activity_id: str, type_id: str, start: str, end: str) -> dict | None:
        payload = self.get_activity(activity_id)
        for interval in _items(payload.get("intervals", [])):
            remote_start = interval.get("from", _epoch(interval.get("start")))
            remote_end = interval.get("to", _epoch(interval.get("finish")))
            if (str(interval.get("typeId") or payload.get("typeId")) == str(type_id)
                    and remote_start is not None and remote_end is not None
                    and abs(int(remote_start) - _second(start)) <= 2
                    and abs(int(remote_end) - _second(end)) <= 2):
                return interval
        return None

    def list_running(self) -> list[dict]:
        values = _items(
            self._request("GET", "/api/activities", step="activity.running.list"),
            "activities", "content", "data",
        )
        return [item for item in values if str(item.get("status") or "").upper() != "STOPPED"]

    def start_final(self, type_id: str, start: str) -> dict:
        return _activity(self._request(
            "POST", f"/api/activities/start/{type_id}?time={_second(start)}",
            step="activity.final.start",
        ))

    def stop_final(self, activity_id: str, end: str) -> dict:
        return _activity(self._request(
            "POST", f"/api/activities/stop/{activity_id}?time={_second(end)}",
            step="activity.final.stop",
        ))

    def get_activity(self, activity_id: str) -> dict:
        return _activity(self._request(
            "GET", f"/api/activities/{activity_id}", step="activity.full.get",
        ))

    def update_full(self, activity_id: str, interval_id: str | None, type_id: str,
                    start: str, end: str, comment: str) -> dict:
        payload = self.get_activity(activity_id)
        if not payload or str(payload.get("id") or "") != str(activity_id):
            raise ATimeLoggerRemoteError("remote_activity_not_found", "activity.full.update")
        intervals = _items(payload.get("intervals", []))
        interval = next(
            (item for item in intervals if str(item.get("id") or "") == str(interval_id or "")),
            intervals[0] if intervals else None,
        )
        if not interval or not interval.get("id"):
            raise ATimeLoggerRemoteError("remote_interval_not_ready", "activity.full.update")
        start_second, end_second = _second(start), _second(end)
        interval.update({
            "typeId": type_id, "activityId": activity_id,
            "start": _utc(start), "finish": _utc(end),
            "from": start_second, "to": end_second,
            "duration": max(0, end_second - start_second),
            "comment": comment.strip(),
        })
        payload.update({
            "typeId": type_id, "duration": max(0, end_second - start_second),
            "comment": comment.strip(), "intervals": intervals,
        })
        return self._request(
            "PUT", f"/api/activities/{activity_id}", payload,
            step="activity.full.update",
        )

    def delete_mapped(self, activity_id: str, interval_id: str | None):
        path = (f"/api/activities/{activity_id}/intervals/{interval_id}"
                if interval_id else f"/api/activities/{activity_id}")
        self._request("DELETE", path, step="activity.delete")


def build_comment(summary: str | None, pause_reasons: str | None) -> str:
    parts = [str(summary or "").strip()]
    raw = str(pause_reasons or "").strip()
    reasons: list[str] = []
    if raw and raw not in ("[]", "无"):
        try:
            parsed = json.loads(raw)
            reasons = [str(item).strip() for item in parsed if str(item).strip()] if isinstance(parsed, list) else [raw]
        except (TypeError, ValueError):
            reasons = [raw]
    if reasons:
        parts.append(f"暂停备注: {'；'.join(reasons)}")
    return "\n\n".join(part for part in parts if part)


def _activity(value: dict) -> dict:
    if value.get("id"):
        return value
    items = _items(value, "activities", "content", "data")
    return items[0] if items else {}


class ATimeLoggerFinalBackupWorker:
    def __init__(self, store, connect, binding_loader, auth_invalidater,
                 client_factory=ATimeLoggerFinalClient):
        self.store = store
        self.connect = connect
        self.binding_loader = binding_loader
        self.auth_invalidater = auth_invalidater
        self.client_factory = client_factory
        self.stopped = False

    def _session(self, user_id: int, session_id: str) -> dict | None:
        conn = self.connect()
        try:
            row = conn.execute(
                "SELECT s.*,c.name category_name FROM server_study_sessions s "
                "LEFT JOIN server_categories c ON c.user_id=s.user_id AND c.id=s.category_id "
                "WHERE s.user_id=? AND s.id=?", (user_id, session_id),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    @staticmethod
    def _type_id(types: list[dict], category_name: str) -> str | None:
        target = str(category_name or "").strip()
        for item in types:
            deleted = item.get("deleted") or item.get("isDeleted") or item.get("deletedAt")
            if not deleted and str(item.get("name") or "").strip() == target and item.get("id"):
                return str(item["id"])
        return None

    @staticmethod
    def _running_ids(activities: list[dict]) -> list[str]:
        return [str(item["id"]) for item in activities if item.get("id")]

    @staticmethod
    def _recover_started(activities: list[dict], baseline: set[str],
                         type_id: str, start: str) -> str | None:
        expected = _second(start)
        candidates = []
        for item in activities:
            activity_id = str(item.get("id") or "")
            remote_start = _epoch(item.get("start") or item.get("from"))
            if (activity_id and activity_id not in baseline
                    and str(item.get("typeId") or "") == str(type_id)
                    and remote_start is not None and abs(remote_start - expected) <= 2):
                candidates.append(activity_id)
        return candidates[0] if len(candidates) == 1 else None

    def _retry(self, job: dict, error: ATimeLoggerRemoteError):
        if error.code == "auth_required":
            self.auth_invalidater(int(job["user_id"]))
            self.store.mark(
                job["id"], "auth_required",
                error_code=error.code, error_step=error.step,
            )
            return
        delay = min(300, 2 ** min(int(job["attempts"]), 8))
        next_at = datetime.now(BEIJING_TZ).timestamp() + delay
        retry_at = datetime.fromtimestamp(next_at, BEIJING_TZ).replace(microsecond=0).isoformat(sep=" ")
        state = (
            "uncertain_start" if error.step == "activity.final.start"
            else "finalize_pending" if error.step == "activity.final.stop"
            else "failed"
        )
        self.store.mark(
            job["id"], state, error_code=error.code,
            error_step=error.step, next_retry_at=retry_at,
        )

    def process_once(self) -> bool:
        job = self.store.claim_due()
        if not job:
            return False
        session = self._session(int(job["user_id"]), str(job["stable_session_id"]))
        if not session:
            self.store.remove(job["id"])
            return True
        binding = self.binding_loader(int(job["user_id"])) or {}
        token = str(binding.get("token") or "")
        if not binding.get("enabled", True) or not token or binding.get("auth_required"):
            self.store.mark(job["id"], "auth_required", error_code="auth_required")
            return True
        client = self.client_factory(token)
        try:
            type_id = self._type_id(client.list_types(), session.get("category_name"))
            if not type_id:
                self.store.mark(
                    job["id"], "unmapped",
                    error_code="category_unmapped", error_step="type.list",
                )
                return True
            comment = build_comment(session.get("session_summary"), session.get("pause_reasons"))
            activity_id = job.get("remote_activity_id")
            interval_id = job.get("remote_interval_id")
            created_activity = False
            matched = client.find_interval(
                session["date"], type_id, session["start_time"], session["end_time"]
            )
            if not matched and activity_id:
                matched = getattr(client, "find_interval_for_activity", lambda *_args: None)(
                    activity_id, type_id, session["start_time"], session["end_time"]
                )
            if matched:
                activity_id = activity_id or matched.get("activityId")
                interval_id = interval_id or matched.get("id")

            if not activity_id:
                baseline = set(json.loads(job.get("running_baseline_json") or "[]"))
                recovering_start = job.get("claimed_from_state") in {
                    "start_pending", "uncertain_start",
                }
                if recovering_start:
                    activity_id = self._recover_started(
                        client.list_running(), baseline, type_id, session["start_time"],
                    )
                    if not activity_id:
                        raise ATimeLoggerRemoteError(
                            "remote_start_ownership_unknown", "activity.final.start",
                        )
                    self.store.record_started(job["id"], activity_id)
                    created_activity = True
                else:
                    running = client.list_running()
                    if running:
                        retry_at = (
                            datetime.now(BEIJING_TZ) + timedelta(seconds=30)
                        ).replace(microsecond=0).isoformat(sep=" ")
                        self.store.mark(
                            job["id"], "pending",
                            error_code="remote_running_active",
                            error_step="activity.running.list",
                            next_retry_at=retry_at,
                        )
                        return True
                    baseline = set(self._running_ids(running))
                    self.store.prepare_start(job["id"], list(baseline))
                    remote = client.start_final(type_id, session["start_time"])
                    activity_id = str(remote.get("id") or "")
                    if not activity_id:
                        raise ATimeLoggerRemoteError(
                            "remote_activity_id_missing", "activity.final.start",
                        )
                    self.store.record_started(job["id"], activity_id)
                    created_activity = True
                job["remote_activity_id"] = activity_id

            if not interval_id:
                if created_activity or job.get("last_error_step") == "activity.final.stop":
                    client.stop_final(activity_id, session["end_time"])
                matched = client.find_interval(
                    session["date"], type_id, session["start_time"], session["end_time"]
                )
                if not matched:
                    matched = getattr(client, "find_interval_for_activity", lambda *_args: None)(
                        activity_id, type_id, session["start_time"], session["end_time"]
                    )
                interval_id = (matched or {}).get("id")
            if not interval_id:
                raise ATimeLoggerRemoteError("remote_interval_not_ready", "interval.query")

            client.update_full(
                activity_id, interval_id, type_id,
                session["start_time"], session["end_time"], comment,
            )
            verified = client.find_interval(
                session["date"], type_id, session["start_time"], session["end_time"]
            )
            if not verified:
                verified = getattr(client, "find_interval_for_activity", lambda *_args: None)(
                    activity_id, type_id, session["start_time"], session["end_time"]
                )
            if not verified:
                raise ATimeLoggerRemoteError("remote_interval_not_ready", "interval.query")
            self.store.mark(
                job["id"], "confirmed", activity_id=activity_id,
                interval_id=verified.get("id") or interval_id,
            )
            return True
        except ATimeLoggerRemoteError as error:
            self._retry(job, error)
            return True

    async def run(self, interval_seconds: int = 5):
        self.stopped = False
        while not self.stopped:
            worked = await asyncio.to_thread(self.process_once)
            await asyncio.sleep(0 if worked else interval_seconds)

    def stop(self):
        self.stopped = True
