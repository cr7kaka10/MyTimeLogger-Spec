"""Auditable, idempotent correction of wrongly attributed server sessions."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Callable

from .session_business_date import session_business_date


BEIJING_TZ = timezone(timedelta(hours=8))


def audit_cross_day_session_dates(conn, user_id: int | None = None) -> list[dict]:
    query = "SELECT id,user_id,start_time,end_time,date FROM server_study_sessions WHERE end_time IS NOT NULL"
    params: tuple[object, ...] = ()
    if user_id is not None:
        query += " AND user_id=?"
        params = (int(user_id),)
    rows = conn.execute(query + " ORDER BY user_id,id", params).fetchall()
    findings = []
    for row in rows:
        current_date = str(row["date"] or "")
        target_date = session_business_date(row["start_time"], row["end_time"], current_date)
        if target_date != current_date:
            findings.append({
                "id": str(row["id"]), "user_id": int(row["user_id"]),
                "old_date": current_date, "date": target_date,
            })
    return findings


def repair_cross_day_session_dates(connect: Callable, user_id: int | None = None,
        apply: bool = False, now: Callable[[], datetime] | None = None) -> list[dict]:
    """Audit by default; explicit apply updates only date/day/updated_at and adds sync changes."""
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        findings = audit_cross_day_session_dates(conn, user_id)
        if apply:
            now_value = (now or (lambda: datetime.now(BEIJING_TZ)))()
            now_value = now_value.replace(tzinfo=BEIJING_TZ) if now_value.tzinfo is None else now_value.astimezone(BEIJING_TZ)
            now_text = now_value.replace(microsecond=0).isoformat(sep=" ")
            for finding in findings:
                _apply_finding(conn, finding, now_text)
        conn.commit()
        return findings
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _apply_finding(conn, finding: dict, now_text: str) -> None:
    date_text = finding["date"]
    day_name = "星期" + "一二三四五六日"[datetime.fromisoformat(date_text).weekday()]
    conn.execute(
        "UPDATE server_study_sessions SET date=?,day_of_week=?,updated_at=? WHERE user_id=? AND id=? AND date=?",
        (date_text, day_name, now_text, finding["user_id"], finding["id"], finding["old_date"]),
    )
    if conn.total_changes == 0:
        return
    user_id = finding["user_id"]
    conn.execute(
        "INSERT INTO server_version_counters(user_id,current_version,updated_at) VALUES (?,0,?) "
        "ON CONFLICT(user_id) DO NOTHING", (user_id, now_text),
    )
    conn.execute("UPDATE server_version_counters SET current_version=current_version+1,updated_at=? WHERE user_id=?", (now_text, user_id))
    version = conn.execute("SELECT current_version FROM server_version_counters WHERE user_id=?", (user_id,)).fetchone()["current_version"]
    session_id = finding["id"]
    conn.execute(
        "INSERT INTO server_change_log "
        "(user_id,server_version,change_id,device_id,table_name,record_id,entity_type,entity_id,operation,"
        "changed_fields_json,status,error,changed_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            user_id, version, f"session-business-date-repair:{session_id}:{date_text}", "maintenance",
            "server_study_sessions", session_id, "study_session", session_id, "upsert",
            json.dumps({"date": date_text, "day_of_week": day_name}, ensure_ascii=False, separators=(",", ":")),
            "applied", None, now_text, now_text,
        ),
    )
