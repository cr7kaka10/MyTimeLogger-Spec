"""Auditable, idempotent repair for invalid server session category references."""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from typing import Callable

BEIJING_TZ = timezone(timedelta(hours=8))

def repair_invalid_session_category_references(connect: Callable, user_id: int | None = None,
        apply: bool = False, now: Callable[[], datetime] | None = None) -> list[dict]:
    """Audit by default; apply only when the final segment name has one server-category match."""
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        query = "SELECT s.id,s.user_id,s.category_id FROM server_study_sessions s LEFT JOIN server_categories c ON c.id=s.category_id AND c.user_id=s.user_id WHERE c.id IS NULL"
        rows = conn.execute(query + (" AND s.user_id=?" if user_id is not None else "") + " ORDER BY s.user_id,s.id", (() if user_id is None else (int(user_id),))).fetchall()
        value = (now or (lambda: datetime.now(BEIJING_TZ)))()
        findings, now_text = [], (value.replace(tzinfo=BEIJING_TZ) if value.tzinfo is None else value.astimezone(BEIJING_TZ)).replace(microsecond=0).isoformat(sep=" ")
        for row in rows:
            segment = conn.execute("SELECT category_name FROM live_timer_segments WHERE user_id=? AND session_id=? ORDER BY started_at DESC,created_at DESC,segment_id DESC LIMIT 1", (row["user_id"], row["id"])).fetchone()
            name = str(segment["category_name"] or "") if segment else ""
            matches = conn.execute("SELECT id FROM server_categories WHERE user_id=? AND name=?", (row["user_id"], name)).fetchall() if name else []
            finding = {"id": str(row["id"]), "user_id": int(row["user_id"]), "old_category_id": row["category_id"], "category_name": name}
            if len(matches) != 1:
                findings.append({**finding, "reason": "missing_or_ambiguous_segment_category"}); continue
            target = int(matches[0]["id"]); finding["category_id"] = target; findings.append(finding)
            if not apply: continue
            changed = conn.execute("UPDATE server_study_sessions SET category_id=?,updated_at=? WHERE user_id=? AND id=? AND (category_id IS NULL OR NOT EXISTS (SELECT 1 FROM server_categories WHERE user_id=? AND id=server_study_sessions.category_id))", (target, now_text, row["user_id"], row["id"], row["user_id"])).rowcount
            if not changed: continue
            conn.execute("INSERT INTO server_version_counters(user_id,current_version,updated_at) VALUES (?,0,?) ON CONFLICT(user_id) DO NOTHING", (row["user_id"], now_text))
            conn.execute("UPDATE server_version_counters SET current_version=current_version+1,updated_at=? WHERE user_id=?", (now_text, row["user_id"]))
            version = conn.execute("SELECT current_version FROM server_version_counters WHERE user_id=?", (row["user_id"],)).fetchone()["current_version"]
            conn.execute("INSERT INTO server_change_log (user_id,server_version,change_id,device_id,table_name,record_id,entity_type,entity_id,operation,changed_fields_json,status,error,changed_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (row["user_id"], version, f"session-category-reference-repair:{row['id']}:{target}", "maintenance", "server_study_sessions", row["id"], "study_session", row["id"], "upsert", json.dumps({"category_id": target}), "applied", None, now_text, now_text))
        conn.commit(); return findings
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()
