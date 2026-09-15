# -*- coding: utf-8 -*-
"""Transactional aTimeLogger date-snapshot persistence."""


def _activity_values(activity):
    start = activity.get("start_time") or activity.get("start") or ""
    end = activity.get("end_time") or activity.get("finish_time") or activity.get("finish") or ""
    if hasattr(start, "isoformat"):
        start = start.isoformat()
    if hasattr(end, "isoformat"):
        end = end.isoformat()
    duration = activity.get("duration_minutes") or (activity.get("duration", 0) // 60) or 0
    return (
        activity.get("activity_type") or activity.get("type") or "",
        start,
        end,
        duration,
        activity.get("comment") or "",
    )


def save_versioned_atm_data(conn, write_change, user_id, date_str, activities, updated_at):
    old_ids = [row[0] for row in conn.execute(
        "SELECT id FROM server_atm_activities WHERE user_id=? AND date=? ORDER BY id",
        (user_id, date_str),
    ).fetchall()]
    conn.execute(
        """INSERT INTO server_atm_summary (user_id,date,updated_at)
           VALUES (?,?,?) ON CONFLICT(user_id,date)
           DO UPDATE SET updated_at=excluded.updated_at""",
        (user_id, date_str, updated_at),
    )
    summary_id = conn.execute(
        "SELECT id FROM server_atm_summary WHERE user_id=? AND date=?", (user_id, date_str)
    ).fetchone()[0]
    write_change(user_id, "atm_summary", str(summary_id), "upsert", {"date": date_str},
                 table_name="server_atm_summary", conn=conn)
    for old_id in old_ids:
        conn.execute("DELETE FROM server_atm_activities WHERE user_id=? AND id=?", (user_id, old_id))
        write_change(user_id, "atm_activity", str(old_id), "delete", {"date": date_str},
                     table_name="server_atm_activities", conn=conn)
    new_ids = []
    for activity in activities:
        values = _activity_values(activity)
        cursor = conn.execute(
            """INSERT INTO server_atm_activities
               (user_id,date,activity_type,start_time,end_time,duration_minutes,comment,updated_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (user_id, date_str, *values, updated_at),
        )
        activity_id = cursor.lastrowid
        new_ids.append(activity_id)
        write_change(user_id, "atm_activity", str(activity_id), "upsert", {"date": date_str},
                     table_name="server_atm_activities", conn=conn)
    return summary_id, new_ids
