"""Guarded local candidate storage for feedback-driven flash-skill tuning."""
from __future__ import annotations

import difflib
import json
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from typing import Callable

from .management_plan_service import now_text


class FlashSkillFeedbackService:
    """Keeps each account's feedback and candidate skill lifecycle isolated."""

    def __init__(self, connect: Callable[[], sqlite3.Connection]):
        self.connect = connect

    @staticmethod
    def _anonymize(text: str) -> str:
        text = re.sub(r"[\w.+-]+@[\w.-]+", "[邮箱]", text)
        return re.sub(r"(?<!\d)1\d{10}(?!\d)", "[手机号]", text).strip()

    def feedback_samples(self, user_id: int, limit: int = 24) -> list[dict]:
        with closing(self.connect()) as conn:
            classified = conn.execute(
                "SELECT f.label,c.original_text FROM server_flash_classification_feedback f "
                "JOIN server_flash_cards c ON c.id=f.flash_card_id AND c.user_id=f.user_id "
                "WHERE f.user_id=? AND c.deleted_at IS NULL ORDER BY f.updated_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
            corrected = conn.execute(
                "SELECT p.flash_card_id,p.original_text_snapshot,p.corrected_polished_text FROM server_flash_polish_corrections p "
                "JOIN server_flash_cards c ON c.id=p.flash_card_id AND c.user_id=p.user_id "
                "WHERE p.user_id=? AND c.deleted_at IS NULL ORDER BY p.created_at DESC,p.rowid DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        samples, seen = [], set()
        seen_cards = set()
        for row in corrected:
            if row["flash_card_id"] in seen_cards:
                continue
            seen_cards.add(row["flash_card_id"])
            input_text = self._anonymize(str(row["original_text_snapshot"] or ""))
            expected = self._anonymize(str(row["corrected_polished_text"] or ""))
            key = ("polish", input_text, expected)
            if input_text and expected and key not in seen:
                samples.append({"kind": "polish", "input": input_text, "expected_output": expected})
                seen.add(key)
        for row in classified:
            text = self._anonymize(str(row["original_text"] or ""))
            key = ("classification", str(row["label"]), text)
            if text and key not in seen:
                samples.append({"kind": "classification", "input": text, "expected_label": key[1]})
                seen.add(key)
        return samples[:limit]

    @staticmethod
    def _event_time() -> str:
        return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S.%f")

    @staticmethod
    def _rule_diff(before: str, after: str) -> dict:
        result = {"added": [], "modified": [], "removed": []}
        matcher = difflib.SequenceMatcher(None, before.splitlines(), after.splitlines())
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            old, new = before.splitlines()[i1:i2], after.splitlines()[j1:j2]
            if tag == "insert": result["added"].extend(new)
            elif tag == "delete": result["removed"].extend(old)
            elif tag == "replace":
                paired = min(len(old), len(new))
                result["modified"].extend({"from": old[index], "to": new[index]} for index in range(paired))
                result["removed"].extend(old[paired:])
                result["added"].extend(new[paired:])
        return {key: value[:20] for key, value in result.items()}

    @staticmethod
    def _sample_summary(samples: list[dict]) -> dict:
        return {kind: sum(1 for item in samples if item.get("kind") == kind) for kind in ("classification", "polish")}

    @staticmethod
    def _redact_rule_diff(rule_diff: dict, samples: list[dict]) -> dict:
        private_values = {str(item.get(key) or "") for item in samples for key in ("input", "expected_output") if len(str(item.get(key) or "")) >= 2}
        clean = lambda text: next(("[校准样本]" for value in private_values if value in str(text)), str(text))
        return {
            "added": [clean(value) for value in rule_diff.get("added", [])],
            "removed": [clean(value) for value in rule_diff.get("removed", [])],
            "modified": [{"from": clean(value.get("from", "")), "to": clean(value.get("to", ""))} for value in rule_diff.get("modified", [])],
        }

    def _append_event(self, conn, user_id: int, candidate: dict, event_type: str, rule_diff: dict, sample_summary: dict, summary: str = "") -> None:
        conn.execute(
            "INSERT INTO server_flash_skill_change_events(id,user_id,candidate_id,version,parent_version,event_type,rule_diff_json,sample_summary_json,evaluation_summary,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), user_id, candidate["id"], candidate["version"], candidate.get("parent_version"), event_type, json.dumps(rule_diff, ensure_ascii=False), json.dumps(sample_summary, ensure_ascii=False), str(summary)[:1000], self._event_time()),
        )

    def create_candidate(self, user_id: int, content: str, samples: list[dict] | None = None, fallback_parent_version: str | None = None, fallback_parent_content: str = "") -> dict:
        content = str(content or "").strip()
        if not content:
            raise ValueError("flash skill candidate is empty")
        now, candidate_id = now_text(), str(uuid.uuid4())
        version = f"flash-todo-diary-feedback-{candidate_id[:8]}"
        with closing(self.connect()) as conn:
            active = conn.execute("SELECT version,content FROM server_flash_skill_candidates WHERE user_id=? AND status='active' ORDER BY updated_at DESC LIMIT 1", (user_id,)).fetchone()
            conn.execute(
                "INSERT INTO server_flash_skill_candidates(id,user_id,version,content,status,created_at,updated_at) VALUES(?,?,?,?, 'pending',?,?)",
                (candidate_id, user_id, version, content, now, now),
            )
            parent_version = str(active["version"]) if active else fallback_parent_version
            parent_content = str(active["content"]) if active else fallback_parent_content
            candidate = {"id": candidate_id, "version": version, "content": content, "status": "pending", "parent_version": parent_version}
            rule_diff = self._redact_rule_diff(self._rule_diff(parent_content, content), samples or [])
            self._append_event(conn, user_id, candidate, "candidate_created", rule_diff, self._sample_summary(samples or []))
            conn.commit()
        return candidate

    def evaluate_and_activate(self, user_id: int, candidate_id: str, evaluator: Callable[[str], tuple[bool, str]]) -> dict:
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT * FROM server_flash_skill_candidates WHERE id=? AND user_id=?", (candidate_id, user_id)).fetchone()
        if not row:
            raise LookupError("flash skill candidate not found")
        passed, summary = evaluator(str(row["content"]))
        candidate = dict(row)
        with closing(self.connect()) as conn:
            created = conn.execute("SELECT parent_version,rule_diff_json,sample_summary_json FROM server_flash_skill_change_events WHERE candidate_id=? AND user_id=? AND event_type='candidate_created'", (candidate_id, user_id)).fetchone()
            candidate["parent_version"] = created["parent_version"] if created else None
            rule_diff = json.loads(created["rule_diff_json"] or "{}") if created else {}
            sample_summary = json.loads(created["sample_summary_json"] or "{}") if created else {}
            now, status = now_text(), "passed" if passed else "failed"
            conn.execute(
                "INSERT INTO server_flash_skill_evaluations(id,user_id,candidate_id,status,summary,created_at) VALUES(?,?,?,?,?,?)",
                (str(uuid.uuid4()), user_id, candidate_id, status, str(summary)[:1000], now),
            )
            conn.execute("UPDATE server_flash_skill_candidates SET status=?,updated_at=? WHERE id=? AND user_id=?", (status, now, candidate_id, user_id))
            self._append_event(conn, user_id, candidate, "evaluated", rule_diff, sample_summary, summary)
            if passed:
                conn.execute("UPDATE server_flash_skill_candidates SET status='passed',updated_at=? WHERE user_id=? AND status='active'", (now, user_id))
                conn.execute("UPDATE server_flash_skill_candidates SET status='active',updated_at=? WHERE id=? AND user_id=?", (now, candidate_id, user_id))
                status = "active"
                self._append_event(conn, user_id, candidate, "activated", rule_diff, sample_summary, summary)
            else:
                self._append_event(conn, user_id, candidate, "failed", rule_diff, sample_summary, summary)
            conn.commit()
        return {"id": candidate_id, "status": status, "summary": str(summary)}

    def active_content(self, user_id: int) -> str | None:
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT content FROM server_flash_skill_candidates WHERE user_id=? AND status='active' ORDER BY updated_at DESC LIMIT 1", (user_id,)).fetchone()
        return str(row["content"]) if row else None

    def active_version(self, user_id: int) -> str | None:
        with closing(self.connect()) as conn:
            row = conn.execute("SELECT version FROM server_flash_skill_candidates WHERE user_id=? AND status='active' ORDER BY updated_at DESC LIMIT 1", (user_id,)).fetchone()
        return str(row["version"]) if row else None

    def history(self, user_id: int, cursor: str | None = None, limit: int = 20) -> dict:
        limit = max(1, min(int(limit), 50))
        where, params = "e.user_id=?", [user_id]
        if cursor and "|" in cursor:
            created_at, event_id = cursor.split("|", 1)
            where += " AND (e.created_at<? OR (e.created_at=? AND e.id<?))"
            params.extend([created_at, created_at, event_id])
        with closing(self.connect()) as conn:
            rows = conn.execute(
                f"SELECT e.*,c.status AS candidate_status FROM server_flash_skill_change_events e LEFT JOIN server_flash_skill_candidates c ON c.id=e.candidate_id WHERE {where} ORDER BY e.created_at DESC,e.id DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
        events = [{**dict(row), "rule_diff": json.loads(row["rule_diff_json"] or "{}"), "sample_summary": json.loads(row["sample_summary_json"] or "{}")} for row in rows]
        for event in events:
            event.pop("rule_diff_json", None); event.pop("sample_summary_json", None)
        next_cursor = f"{rows[-1]['created_at']}|{rows[-1]['id']}" if len(rows) == limit else None
        return {"events": events, "next_cursor": next_cursor}
