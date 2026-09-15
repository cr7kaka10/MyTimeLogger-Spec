"""Account-isolated CRUD for TimeBook flash cards."""
from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timedelta
from typing import Callable
import json

from .management_plan_service import now_text
from .flash_proofreading import validate_minimal_polish
from .reward_config_service import RewardConfigService


class FlashCardError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class FlashCardService:
    def __init__(self, connect: Callable[[], sqlite3.Connection], record_change: Callable):
        self.connect = connect
        self.record_change = record_change

    def list(self, user_id: int, date: str | None = None) -> list[dict]:
        with closing(self.connect()) as conn:
            query = "SELECT id,occurred_at,original_text,polished_text,diary_mood,diary_content,task_recommendations_json,analysis_status,analysis_error_code,analysis_draft_id,created_at,updated_at FROM server_flash_cards WHERE user_id=? AND deleted_at IS NULL"
            params: tuple = (user_id,)
            if date:
                query += " AND substr(occurred_at,1,10)=?"
                params = (user_id, date)
            return [dict(row) for row in conn.execute(query + " ORDER BY occurred_at DESC,id", params)]

    @staticmethod
    def _recommendation_id(card_id: str, ordinal: int) -> str:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"mytimelogger:flash-recommendation:{card_id}:{ordinal}"))

    @staticmethod
    def _creation_mode(original_text: str, todos: list[dict]) -> str:
        if len(todos) != 1:
            return "confirm"
        text = f"{original_text}\n{todos[0].get('title', '')}"
        complex_markers = ("计划", "规划", "拆解", "步骤", "分别", "以及", "然后", "并且", "同时", "如果", "取决于", "、", "；", ";", "\n-")
        return "confirm" if any(marker in text for marker in complex_markers) else "direct"

    def _create_local_task(self, conn: sqlite3.Connection, user_id: int, card_id: str, recommendation_id: str, title: str, creation_key: str, now: str) -> str:
        task_id = "local_" + uuid.uuid5(uuid.NAMESPACE_URL, creation_key).hex
        created = conn.execute(
            "INSERT OR IGNORE INTO server_tasks(id,user_id,title,priority,status,due_date,tags,raw_json,source,updated_at) VALUES(?,?,?,0,0,?,?,?,'local',?)",
            (task_id, user_id, title, now[:10], "[]", json.dumps({"flash_card_id": card_id, "recommendation_id": recommendation_id}, ensure_ascii=False), now),
        ).rowcount
        RewardConfigService().ensure_item(conn, user_id, "task", task_id)
        if created:
            self.record_change(conn, user_id, "server_tasks", task_id, "upsert", {"id": task_id, "source": "local"})
        return task_id

    def _ensure_recommendations(self, conn: sqlite3.Connection, user_id: int, card_id: str, todos: list[dict], original_text: str = "") -> None:
        now = now_text()
        creation_mode = self._creation_mode(original_text, todos)
        for ordinal, todo in enumerate(todos):
            title = str((todo or {}).get("title") or "").strip()
            if not title:
                continue
            recommendation_id = self._recommendation_id(card_id, ordinal)
            creation_key = f"flash:{card_id}:{recommendation_id}"
            conn.execute(
                "INSERT OR IGNORE INTO server_flash_task_recommendations(id,user_id,flash_card_id,ordinal,title,reason,status,creation_mode,creation_idempotency_key,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (recommendation_id, user_id, card_id, ordinal, title, str((todo or {}).get("reason") or "").strip(), "pending", creation_mode, creation_key, now, now),
            )
            if creation_mode == "direct":
                task_id = self._create_local_task(conn, user_id, card_id, recommendation_id, title, creation_key, now)
                conn.execute("UPDATE server_flash_task_recommendations SET status='added',local_task_id=?,creation_mode='direct',creation_idempotency_key=?,updated_at=? WHERE id=? AND user_id=?", (task_id, creation_key, now, recommendation_id, user_id))

    def migrate_legacy_recommendations(self, user_id: int | None = None) -> int:
        with closing(self.connect()) as conn:
            query, params = "SELECT id,user_id,original_text,task_recommendations_json FROM server_flash_cards WHERE deleted_at IS NULL", ()
            if user_id is not None:
                query += " AND user_id=?"; params = (user_id,)
            migrated = 0
            for card in conn.execute(query, params):
                try: todos = json.loads(card["task_recommendations_json"] or "[]")
                except (TypeError, ValueError): todos = []
                before = conn.total_changes
                self._ensure_recommendations(conn, int(card["user_id"]), str(card["id"]), todos if isinstance(todos, list) else [], str(card["original_text"] or ""))
                if conn.total_changes > before:
                    created = conn.execute("SELECT id FROM server_flash_task_recommendations WHERE user_id=? AND flash_card_id=?", (card["user_id"], card["id"])).fetchall()
                    for recommendation in created:
                        self.record_change(conn, int(card["user_id"]), "server_flash_task_recommendations", str(recommendation["id"]), "upsert", {"id": recommendation["id"]})
                    migrated += conn.total_changes - before
            conn.commit()
            return migrated

    def list_recommendations(self, user_id: int, flash_card_ids: list[str] | None = None) -> list[dict]:
        self.migrate_legacy_recommendations(user_id)
        with closing(self.connect()) as conn:
            query, params = "SELECT * FROM server_flash_task_recommendations WHERE user_id=?", [user_id]
            if flash_card_ids:
                query += f" AND flash_card_id IN ({','.join('?' for _ in flash_card_ids)})"; params.extend(flash_card_ids)
            return [dict(row) for row in conn.execute(query + " ORDER BY flash_card_id,ordinal", params)]

    def get_recommendation(self, user_id: int, recommendation_id: str) -> dict:
        self.migrate_legacy_recommendations(user_id)
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT * FROM server_flash_task_recommendations WHERE id=? AND user_id=?", (recommendation_id, user_id)).fetchone()
            if not row: raise FlashCardError("flash_recommendation_not_found", "推荐任务不存在", 404)
            return dict(row)

    def ignore_recommendation(self, user_id: int, recommendation_id: str) -> dict:
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT * FROM server_flash_task_recommendations WHERE id=? AND user_id=?", (recommendation_id, user_id)).fetchone()
            if not row: raise FlashCardError("flash_recommendation_not_found", "推荐任务不存在", 404)
            now = now_text()
            if row["status"] == "pending":
                conn.execute("UPDATE server_flash_task_recommendations SET status='ignored',ignored_at=?,updated_at=? WHERE id=? AND user_id=?", (now, now, recommendation_id, user_id))
                self.record_change(conn, user_id, "server_flash_task_recommendations", recommendation_id, "upsert", {"id": recommendation_id, "status": "ignored"})
                conn.commit()
            return dict(conn.execute("SELECT * FROM server_flash_task_recommendations WHERE id=? AND user_id=?", (recommendation_id, user_id)).fetchone())

    def mark_recommendation_added(self, user_id: int, recommendation_id: str, provider_task_id: str) -> dict:
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT * FROM server_flash_task_recommendations WHERE id=? AND user_id=?", (recommendation_id, user_id)).fetchone()
            if not row: raise FlashCardError("flash_recommendation_not_found", "推荐任务不存在", 404)
            if row["status"] == "pending":
                now = now_text()
                conn.execute("UPDATE server_flash_task_recommendations SET status='added',provider_task_id=?,updated_at=? WHERE id=? AND user_id=?", (provider_task_id, now, recommendation_id, user_id))
                self.record_change(conn, user_id, "server_flash_task_recommendations", recommendation_id, "upsert", {"id": recommendation_id, "status": "added"})
                conn.commit()
            return dict(conn.execute("SELECT * FROM server_flash_task_recommendations WHERE id=? AND user_id=?", (recommendation_id, user_id)).fetchone())

    def confirm_recommendation(self, user_id: int, recommendation_id: str) -> dict:
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT * FROM server_flash_task_recommendations WHERE id=? AND user_id=?", (recommendation_id, user_id)).fetchone()
            if not row: raise FlashCardError("flash_recommendation_not_found", "推荐任务不存在", 404)
            if row["status"] == "pending":
                now = now_text()
                creation_key = row["creation_idempotency_key"] or f"flash:{row['flash_card_id']}:{recommendation_id}"
                task_id = self._create_local_task(conn, user_id, row["flash_card_id"], recommendation_id, row["title"], creation_key, now)
                conn.execute("UPDATE server_flash_task_recommendations SET status='added',local_task_id=?,creation_idempotency_key=?,updated_at=? WHERE id=? AND user_id=?", (task_id, creation_key, now, recommendation_id, user_id))
                self.record_change(conn, user_id, "server_flash_task_recommendations", recommendation_id, "upsert", {"id": recommendation_id, "status": "added"})
                conn.commit()
            return dict(conn.execute("SELECT * FROM server_flash_task_recommendations WHERE id=? AND user_id=?", (recommendation_id, user_id)).fetchone())

    def record_classification_feedback(self, user_id: int, card_id: str, label: str, skill_version: str = "") -> dict:
        if label not in {"todo", "mood"}:
            raise FlashCardError("flash_feedback_label_invalid", "反馈分类无效")
        with closing(self.connect()) as conn:
            if not conn.execute("SELECT 1 FROM server_flash_cards WHERE id=? AND user_id=? AND deleted_at IS NULL", (card_id, user_id)).fetchone():
                raise FlashCardError("flash_card_not_found", "闪念卡片不存在", 404)
            now, run_id = now_text(), str(uuid.uuid4())
            conn.execute(
                "INSERT INTO server_flash_classification_feedback(user_id,flash_card_id,label,created_at,updated_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(user_id,flash_card_id) DO UPDATE SET label=excluded.label,updated_at=excluded.updated_at",
                (user_id, card_id, label, now, now),
            )
            conn.execute(
                "INSERT INTO server_flash_feedback_reanalysis_runs(id,user_id,flash_card_id,label,skill_version,status,created_at) VALUES(?,?,?,?,?,'pending',?)",
                (run_id, user_id, card_id, label, skill_version, now),
            )
            conn.execute("UPDATE server_flash_cards SET analysis_status='processing',analysis_error_code=NULL,updated_at=? WHERE id=? AND user_id=?", (now, card_id, user_id))
            self.record_change(conn, user_id, "server_flash_cards", card_id, "upsert", {"id": card_id, "analysis_status": "processing"})
            conn.commit()
        return {"label": label, "run_id": run_id, "status": "pending", "updated_at": now}

    def mark_feedback_reanalysis_failed(self, user_id: int, card_id: str, run_id: str, error_code: str) -> None:
        with closing(self.connect()) as conn:
            now = now_text()
            conn.execute("UPDATE server_flash_feedback_reanalysis_runs SET status='failed',error_code=?,completed_at=? WHERE id=? AND user_id=? AND flash_card_id=?", (error_code, now, run_id, user_id, card_id))
            conn.execute("UPDATE server_flash_cards SET analysis_status='failed',analysis_error_code=?,updated_at=? WHERE id=? AND user_id=?", (error_code, now, card_id, user_id))
            self.record_change(conn, user_id, "server_flash_cards", card_id, "upsert", {"id": card_id, "analysis_status": "failed"})
            conn.commit()

    def save_feedback_reanalysis(self, user_id: int, card_id: str, run_id: str, polished_text: str, diary: dict | None, todos: list[dict]) -> dict:
        original = self._get(user_id, card_id)
        polished = str(polished_text or "").strip()
        mood, content = (str((diary or {}).get(key) or "").strip() or None for key in ("mood", "content"))
        if not polished or len(polished) > len(str(original["original_text"])) + 40:
            raise FlashCardError("flash_card_polish_invalid", "AI 润色结果不符合忠实整理要求", 422)
        if bool(mood) != bool(content) or (mood and (len(mood) > 20 or len(content) > 1000)):
            raise FlashCardError("flash_diary_invalid", "AI 心情日记结果格式无效", 422)
        with closing(self.connect()) as conn:
            run = conn.execute("SELECT id FROM server_flash_feedback_reanalysis_runs WHERE id=? AND user_id=? AND flash_card_id=? AND status IN ('pending','processing')", (run_id, user_id, card_id)).fetchone()
            if not run:
                raise FlashCardError("flash_feedback_run_not_found", "重识别任务不存在", 404)
            human = conn.execute("SELECT corrected_polished_text FROM server_flash_polish_corrections WHERE user_id=? AND flash_card_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1", (user_id, card_id)).fetchone()
            stored_polished = str(human["corrected_polished_text"]) if human else polished
            now = now_text()
            pending = conn.execute("SELECT * FROM server_flash_task_recommendations WHERE user_id=? AND flash_card_id=? AND status='pending' ORDER BY ordinal", (user_id, card_id)).fetchall()
            for index, todo in enumerate(todos):
                title, reason = str(todo.get("title") or "").strip(), str(todo.get("reason") or "").strip()
                if not title:
                    continue
                if index < len(pending):
                    conn.execute("UPDATE server_flash_task_recommendations SET title=?,reason=?,updated_at=? WHERE id=?", (title, reason, now, pending[index]["id"]))
                    self.record_change(conn, user_id, "server_flash_task_recommendations", str(pending[index]["id"]), "upsert", {"id": pending[index]["id"]})
                else:
                    ordinal = int(conn.execute("SELECT COALESCE(MAX(ordinal),-1)+1 FROM server_flash_task_recommendations WHERE user_id=? AND flash_card_id=?", (user_id, card_id)).fetchone()[0])
                    recommendation_id = self._recommendation_id(card_id, ordinal)
                    conn.execute("INSERT INTO server_flash_task_recommendations(id,user_id,flash_card_id,ordinal,title,reason,status,created_at,updated_at) VALUES(?,?,?,?,?,?, 'pending',?,?)", (recommendation_id, user_id, card_id, ordinal, title, reason, now, now))
                    self.record_change(conn, user_id, "server_flash_task_recommendations", recommendation_id, "upsert", {"id": recommendation_id})
            for row in pending[len(todos):]:
                conn.execute("UPDATE server_flash_task_recommendations SET status='ignored',superseded_at=?,updated_at=? WHERE id=?", (now, now, row["id"]))
                self.record_change(conn, user_id, "server_flash_task_recommendations", str(row["id"]), "upsert", {"id": row["id"], "status": "ignored"})
            conn.execute("UPDATE server_flash_cards SET polished_text=?,diary_mood=?,diary_content=?,task_recommendations_json=?,analysis_status='done',analysis_error_code=NULL,updated_at=? WHERE id=? AND user_id=?", (stored_polished, mood, content, json.dumps(todos, ensure_ascii=False), now, card_id, user_id))
            conn.execute("UPDATE server_flash_feedback_reanalysis_runs SET status='done',completed_at=? WHERE id=?", (now, run_id))
            self.record_change(conn, user_id, "server_flash_cards", card_id, "upsert", {"id": card_id, "feedback_reanalysis": True})
            conn.commit()
        return self._get(user_id, card_id)

    @staticmethod
    def claim_analysis(conn: sqlite3.Connection, user_id: int, card_id: str) -> bool:
        now = now_text()
        stale_before = (datetime.strptime(now, "%Y-%m-%d %H:%M:%S") - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE server_flash_cards SET analysis_status='pending',updated_at=? "
            "WHERE user_id=? AND id=? AND analysis_status='processing' AND updated_at<?",
            (now, user_id, card_id, stale_before),
        )
        claimed = conn.execute(
            "UPDATE server_flash_cards SET analysis_status='processing',updated_at=? "
            "WHERE user_id=? AND id=? AND deleted_at IS NULL AND analysis_status IN ('pending','failed','idle')",
            (now, user_id, card_id),
        )
        return claimed.rowcount == 1

    def create(self, user_id: int, payload: dict) -> dict:
        text = str(payload.get("original_text") or "").strip()
        occurred_at = str(payload.get("occurred_at") or now_text()).strip()
        if not text:
            raise FlashCardError("flash_card_text_required", "闪念内容不能为空")
        if len(text) > 4000:
            raise FlashCardError("flash_card_text_too_long", "闪念内容不能超过 4000 个字符")
        card_id, now = str(uuid.uuid4()), now_text()
        with closing(self.connect()) as conn:
            try:
                conn.execute("INSERT INTO server_flash_cards(id,user_id,occurred_at,original_text,analysis_status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (card_id, user_id, occurred_at, text, "pending", now, now))
                self.record_change(conn, user_id, "server_flash_cards", card_id, "upsert", {"id": card_id})
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return self._get(user_id, card_id)

    def update(self, user_id: int, card_id: str, payload: dict) -> dict:
        allowed = {key: payload[key] for key in ("original_text", "occurred_at") if key in payload}
        if not allowed:
            return self._get(user_id, card_id)
        if "original_text" in allowed:
            allowed["original_text"] = str(allowed["original_text"] or "").strip()
            if not allowed["original_text"]:
                raise FlashCardError("flash_card_text_required", "闪念内容不能为空")
        with closing(self.connect()) as conn:
            if not conn.execute("SELECT 1 FROM server_flash_cards WHERE id=? AND user_id=? AND deleted_at IS NULL", (card_id, user_id)).fetchone():
                raise FlashCardError("flash_card_not_found", "闪念卡片不存在", 404)
            assignments = ",".join(f"{key}=?" for key in allowed)
            conn.execute(f"UPDATE server_flash_cards SET {assignments},updated_at=? WHERE id=? AND user_id=?", (*allowed.values(), now_text(), card_id, user_id))
            self.record_change(conn, user_id, "server_flash_cards", card_id, "upsert", {"id": card_id, **allowed})
            conn.commit()
        return self._get(user_id, card_id)

    def polish(self, user_id: int, card_id: str, runner: Callable[[str], str]) -> dict:
        """Persist only a faithful, model-produced rewrite of one owned card."""
        card = self._get(user_id, card_id)
        try:
            polished, _code, _edits = validate_minimal_polish(str(card["original_text"]) or "", runner(str(card["original_text"]) or ""))
        except FlashCardError:
            raise
        except Exception as exc:
            raise FlashCardError("flash_card_polish_failed", "AI 润色失败，请稍后重试", 502) from exc
        if not polished or len(polished) > len(str(card["original_text"])) + 40:
            raise FlashCardError("flash_card_polish_invalid", "AI 润色结果不符合忠实整理要求", 422)
        with closing(self.connect()) as conn:
            now = now_text()
            conn.execute(
                "UPDATE server_flash_cards SET polished_text=?,updated_at=? WHERE id=? AND user_id=? AND deleted_at IS NULL",
                (polished, now, card_id, user_id),
            )
            self.record_change(conn, user_id, "server_flash_cards", card_id, "upsert", {"id": card_id, "polished": True})
            conn.commit()
        return self._get(user_id, card_id)

    def correct_polish(self, user_id: int, card_id: str, payload: dict, skill_version: str = "") -> dict:
        request_id = str(payload.get("request_id") or "").strip()
        corrected = str(payload.get("corrected_text") or "").strip()
        occurred_at = str(payload.get("occurred_at") or "").strip() or None
        if not request_id or len(request_id) > 128:
            raise FlashCardError("flash_polish_request_invalid", "保存请求标识无效")
        if not corrected:
            raise FlashCardError("flash_card_text_required", "润色内容不能为空")
        if len(corrected) > 4000:
            raise FlashCardError("flash_card_text_too_long", "润色内容不能超过 4000 个字符")
        with closing(self.connect()) as conn:
            existing = conn.execute(
                "SELECT flash_card_id,corrected_polished_text FROM server_flash_polish_corrections WHERE user_id=? AND request_id=?",
                (user_id, request_id),
            ).fetchone()
            if existing:
                if existing["flash_card_id"] != card_id or existing["corrected_polished_text"] != corrected:
                    raise FlashCardError("flash_polish_request_conflict", "保存请求标识已用于其他内容", 409)
                return self._get(user_id, card_id)
            card = conn.execute(
                "SELECT original_text,polished_text FROM server_flash_cards WHERE id=? AND user_id=? AND deleted_at IS NULL",
                (card_id, user_id),
            ).fetchone()
            if not card:
                raise FlashCardError("flash_card_not_found", "闪念卡片不存在", 404)
            now = now_text()
            try:
                conn.execute(
                    "INSERT INTO server_flash_polish_corrections(id,request_id,user_id,flash_card_id,original_text_snapshot,previous_polished_text,corrected_polished_text,skill_version,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (str(uuid.uuid4()), request_id, user_id, card_id, card["original_text"], card["polished_text"], corrected, skill_version, now),
                )
                if occurred_at:
                    conn.execute("UPDATE server_flash_cards SET polished_text=?,occurred_at=?,updated_at=? WHERE id=? AND user_id=?", (corrected, occurred_at, now, card_id, user_id))
                else:
                    conn.execute("UPDATE server_flash_cards SET polished_text=?,updated_at=? WHERE id=? AND user_id=?", (corrected, now, card_id, user_id))
                self.record_change(conn, user_id, "server_flash_cards", card_id, "upsert", {"id": card_id, "human_polished": True})
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return self._get(user_id, card_id)

    def save_insights(self, user_id: int, card_id: str, polished_text: str, diary: dict | None, todos: list[dict] | None = None) -> dict:
        original = self._get(user_id, card_id)
        polished = str(polished_text or "").strip()
        mood = str((diary or {}).get("mood") or "").strip() or None
        content = str((diary or {}).get("content") or "").strip() or None
        if not polished or len(polished) > len(str(original["original_text"])) + 40:
            raise FlashCardError("flash_card_polish_invalid", "AI 润色结果不符合忠实整理要求", 422)
        if bool(mood) != bool(content) or (mood and (len(mood) > 20 or len(content) > 1000)):
            raise FlashCardError("flash_diary_invalid", "AI 心情日记结果格式无效", 422)
        with closing(self.connect()) as conn:
            now = now_text()
            human = conn.execute("SELECT corrected_polished_text FROM server_flash_polish_corrections WHERE user_id=? AND flash_card_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1", (user_id, card_id)).fetchone()
            stored_polished = str(human["corrected_polished_text"]) if human else polished
            conn.execute(
                "UPDATE server_flash_cards SET polished_text=?,diary_mood=?,diary_content=?,task_recommendations_json=?,analysis_status='done',analysis_error_code=NULL,updated_at=? WHERE id=? AND user_id=? AND deleted_at IS NULL",
                (stored_polished, mood, content, json.dumps(todos or [], ensure_ascii=False), now, card_id, user_id),
            )
            self._ensure_recommendations(conn, user_id, card_id, todos or [], str(original["original_text"] or ""))
            self.record_change(conn, user_id, "server_flash_cards", card_id, "upsert", {"id": card_id, "polished": True, "has_diary": bool(content)})
            for recommendation in conn.execute("SELECT id FROM server_flash_task_recommendations WHERE user_id=? AND flash_card_id=?", (user_id, card_id)):
                self.record_change(conn, user_id, "server_flash_task_recommendations", str(recommendation["id"]), "upsert", {"id": recommendation["id"]})
            conn.commit()
        return self._get(user_id, card_id)

    def mark_analysis_failed(self, user_id: int, card_id: str, error_code: str) -> dict:
        with closing(self.connect()) as conn:
            conn.execute("UPDATE server_flash_cards SET analysis_status='failed',analysis_error_code=?,updated_at=? WHERE id=? AND user_id=? AND deleted_at IS NULL",
                         (error_code, now_text(), card_id, user_id))
            self.record_change(conn, user_id, "server_flash_cards", card_id, "upsert", {"id": card_id, "analysis_status": "failed"})
            conn.commit()
        return self._get(user_id, card_id)

    def create_and_polish(self, user_id: int, payload: dict, runner_factory: Callable[[], Callable[[str], str]]) -> dict:
        """Keep the original flash card even when its automatic polish cannot run."""
        card = self.create(user_id, payload)
        try:
            return {"card": self.polish(user_id, card["id"], runner_factory()), "polish_status": "done"}
        except FlashCardError as exc:
            return {"card": card, "polish_status": "failed", "message": exc.message}
        except Exception:
            return {"card": card, "polish_status": "failed", "message": "AI 润色失败，请稍后重试"}

    def mark_analysis_draft(self, user_id: int, card_id: str, draft_id: str) -> dict:
        with closing(self.connect()) as conn:
            if not conn.execute("SELECT 1 FROM server_flash_cards WHERE id=? AND user_id=? AND deleted_at IS NULL", (card_id, user_id)).fetchone():
                raise FlashCardError("flash_card_not_found", "闪念卡片不存在", 404)
            now = now_text()
            conn.execute(
                "UPDATE server_flash_cards SET analysis_status='draft_ready',analysis_draft_id=?,updated_at=? WHERE id=? AND user_id=?",
                (draft_id, now, card_id, user_id),
            )
            self.record_change(conn, user_id, "server_flash_cards", card_id, "upsert", {"id": card_id, "analysis_status": "draft_ready", "analysis_draft_id": draft_id})
            conn.commit()
        return self._get(user_id, card_id)

    def delete(self, user_id: int, card_id: str) -> None:
        with closing(self.connect()) as conn:
            if not conn.execute("SELECT 1 FROM server_flash_cards WHERE id=? AND user_id=? AND deleted_at IS NULL", (card_id, user_id)).fetchone():
                raise FlashCardError("flash_card_not_found", "闪念卡片不存在", 404)
            now = now_text()
            conn.execute("DELETE FROM server_flash_classification_feedback WHERE user_id=? AND flash_card_id=?", (user_id, card_id))
            conn.execute("DELETE FROM server_flash_feedback_reanalysis_runs WHERE user_id=? AND flash_card_id=?", (user_id, card_id))
            conn.execute("DELETE FROM server_flash_polish_corrections WHERE user_id=? AND flash_card_id=?", (user_id, card_id))
            conn.execute("UPDATE server_flash_cards SET deleted_at=?,updated_at=? WHERE id=? AND user_id=?", (now, now, card_id, user_id))
            self.record_change(conn, user_id, "server_flash_cards", card_id, "delete", {"id": card_id})
            conn.commit()

    def _get(self, user_id: int, card_id: str) -> dict:
        cards = self.list(user_id)
        for card in cards:
            if card["id"] == card_id:
                return card
        raise FlashCardError("flash_card_not_found", "闪念卡片不存在", 404)

    def get(self, user_id: int, card_id: str) -> dict:
        return self._get(user_id, card_id)
