from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3

from server.domain.live_timer_lease_service import (
    LiveTimerStateService,
    decide_current_state,
)
from server.models.server_schema import ensure_server_schema


BEIJING = timezone(timedelta(hours=8))


def _service(tmp_path, now=None):
    path = str(tmp_path / "timer-state.db")
    conn = sqlite3.connect(path)
    ensure_server_schema(conn)
    ensure_server_schema(conn)
    conn.execute("INSERT INTO users(username,password_hash,created_at) VALUES ('u','x','now')")
    conn.executemany(
        "INSERT INTO server_categories(user_id,name,group_name,updated_at) VALUES (1,?,'默认','now')",
        [(name,) for name in ('输入', '输出', '吃饭', '工作', '睡觉', '运动', '家庭')],
    )
    conn.commit()
    conn.close()

    def connect():
        db = sqlite3.connect(path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        return db

    return LiveTimerStateService(connect, now=now), path


def _command(operation, revision, key, device="pc", category="输入", intent=None, **extra):
    return {
        "session_id": extra.pop("session_id", "timer-session"),
        "device_id": device,
        "observed_revision": revision,
        "idempotency_key": key,
        "user_intent_id": intent or key,
        "category_id": None,
        "category_name": category,
        "current_note": extra.pop("current_note", ""),
        "timer_mode": "countup",
        "duration_ms": 0,
        **extra,
    }


def test_current_state_decision_uses_revision_not_device_owner():
    current = {"revision": 7, "state": "running", "owner_device_id": "pc"}
    assert decide_current_state(current, "switch", 7) == "accepted"
    assert decide_current_state(current, "stop", 7) == "accepted"
    assert decide_current_state(current, "switch", 6) == "stale_timer_revision"
    assert decide_current_state(None, "start", 0) == "accepted"


def test_timer_category_uses_server_id_and_rejects_unknown_name(tmp_path):
    service, path = _service(tmp_path)
    started = service.command(1, "start", _command("start", 0, "work", category="工作", category_id=16))
    assert started["state"]["category_id"] != 16
    conn = sqlite3.connect(path)
    server_id = conn.execute("SELECT id FROM server_categories WHERE user_id=1 AND name='工作'").fetchone()[0]
    segment_id = conn.execute("SELECT category_id FROM live_timer_segments").fetchone()[0]
    conn.close()
    assert started["state"]["category_id"] == segment_id == server_id

    rejected = service.command(1, "switch", _command("switch", 1, "missing", category="不存在"))
    assert rejected["status"] == "conflict"
    assert rejected["error_code"] == "invalid_timer_category"
    assert rejected["state"]["category_name"] == "工作"


def test_cross_device_switch_pause_resume_and_time_baseline(tmp_path):
    clock = [datetime(2026, 7, 24, 20, 0, tzinfo=BEIJING)]
    service, _ = _service(tmp_path, now=lambda: clock[0])
    started = service.command(1, "start", _command("start", 0, "start", session_id="s", current_note="学习任务"))
    assert started["state"]["revision"] == 1
    assert started["state"]["segment_started_at"] == "2026-07-24 20:00:00+08:00"
    assert started["state"]["current_note"] == "学习任务"

    clock[0] += timedelta(seconds=5)
    switched = service.command(1, "switch", _command("switch", 1, "switch", device="android", category="吃饭", current_note="午餐"))
    assert switched["state"]["category_name"] == "吃饭"
    assert switched["completed_session_id"] == "s"
    assert switched["state"]["session_id"] != "s"
    assert switched["state"]["active_elapsed_ms"] == 0
    assert switched["state"]["updated_by_device_id"] == "android"
    assert switched["state"]["current_note"] == "午餐"

    clock[0] += timedelta(seconds=3)
    paused = service.command(1, "pause", _command("pause", 2, "pause", device="pc"))
    assert paused["state"]["state"] == "paused"
    assert paused["state"]["active_elapsed_ms"] == 3000
    resumed = service.command(1, "resume", _command("resume", 3, "resume", device="android"))
    assert resumed["state"]["state"] == "running"
    assert resumed["state"]["revision"] == 4
    assert resumed["state"]["current_note"] == "午餐"


def test_switch_and_stop_enqueue_distinct_stable_backup_jobs(tmp_path):
    clock = [datetime(2026, 7, 24, 20, 0, tzinfo=BEIJING)]
    service, path = _service(tmp_path, now=lambda: clock[0])
    service.command(1, "start", _command("start", 0, "start", session_id="first"))
    clock[0] += timedelta(seconds=5)
    switched = service.command(
        1, "switch", _command("switch", 1, "switch", session_id="second", category="输出"),
    )
    clock[0] += timedelta(seconds=4)
    stopped = service.command(1, "stop", _command("stop", 2, "stop"))
    conn = sqlite3.connect(path)
    jobs = conn.execute(
        "SELECT stable_session_id FROM server_atimelogger_backups ORDER BY id"
    ).fetchall()
    conn.close()
    assert switched["completed_session_id"] == "first"
    assert stopped["completed_session_id"] == "second"
    assert jobs == [("first",), ("second",)]


def test_completed_cross_day_session_uses_longer_beijing_day_and_version_log(tmp_path):
    clock = [datetime(2026, 8, 30, 22, 30, tzinfo=BEIJING)]
    service, path = _service(tmp_path, now=lambda: clock[0])
    service.command(1, "start", _command("start", 0, "start", session_id="sleep"))
    clock[0] = datetime(2026, 8, 31, 8, 30, tzinfo=BEIJING)
    service.command(1, "stop", _command("stop", 1, "stop"))

    conn = sqlite3.connect(path)
    session = conn.execute("SELECT id,date,day_of_week FROM server_study_sessions").fetchone()
    change = conn.execute("SELECT server_version,record_id FROM server_change_log WHERE table_name='server_study_sessions'").fetchone()
    conn.close()
    assert session == ("sleep", "2026-08-31", "星期一")
    assert change == (1, "sleep")


def test_automatic_sleep_switch_publishes_previous_and_sleep_once(tmp_path):
    clock = [datetime(2026, 8, 30, 21, 0, tzinfo=BEIJING)]
    service, path = _service(tmp_path, now=lambda: clock[0])
    service.command(1, "start", _command("start", 0, "before-start", session_id="before-sleep", category="工作"))

    clock[0] = datetime(2026, 8, 30, 22, 30, tzinfo=BEIJING)
    sleep_switch = _command(
        "switch", 1, "sleep-command:1:2026-08-30:timer-switch:1",
        session_id="automatic-sleep", category="睡觉", intent="sleep-command:1:2026-08-30:timer-switch",
    )
    switched = service.command(1, "switch", sleep_switch)
    replayed = service.command(1, "switch", sleep_switch)

    clock[0] = datetime(2026, 8, 31, 8, 30, tzinfo=BEIJING)
    stopped = service.command(1, "stop", _command("stop", 2, "sleep-stop", session_id="automatic-sleep", category="睡觉"))

    conn = sqlite3.connect(path)
    sessions = conn.execute(
        "SELECT id,date,net_duration_seconds FROM server_study_sessions ORDER BY start_time"
    ).fetchall()
    changes = conn.execute(
        "SELECT record_id FROM server_change_log WHERE table_name='server_study_sessions' ORDER BY server_version"
    ).fetchall()
    backups = conn.execute(
        "SELECT stable_session_id FROM server_atimelogger_backups ORDER BY id"
    ).fetchall()
    conn.close()

    assert switched["completed_session_id"] == "before-sleep"
    assert replayed == switched
    assert stopped["completed_session_id"] == "automatic-sleep"
    assert sessions == [("before-sleep", "2026-08-30", 5400), ("automatic-sleep", "2026-08-31", 36000)]
    assert changes == [("before-sleep",), ("automatic-sleep",)]
    assert backups == [("before-sleep",), ("automatic-sleep",)]


def test_current_note_updates_by_revision_and_reaches_history(tmp_path):
    service, path = _service(tmp_path)
    service.command(1, "start", _command("start", 0, "start", current_note="旧备注"))
    noted = service.command(1, "note", _command("note", 1, "note", current_note="任务标题"))
    assert noted["state"]["revision"] == 2
    assert noted["state"]["current_note"] == "任务标题"
    stale = service.command(1, "note", _command("note", 1, "stale-note", current_note="过期备注"))
    assert stale["error_code"] == "stale_timer_revision"
    stopped = service.command(1, "stop", _command("stop", 2, "stop"))
    assert stopped["state"]["current_note"] == "任务标题"
    conn = sqlite3.connect(path)
    summary = conn.execute("SELECT session_summary FROM server_study_sessions").fetchone()[0]
    conn.close()
    assert summary == "任务标题"


def test_active_start_from_another_device_becomes_next_segment(tmp_path):
    clock = [datetime(2026, 7, 24, 20, 0, tzinfo=BEIJING)]
    service, path = _service(tmp_path, now=lambda: clock[0])
    service.command(1, "start", _command("start", 0, "pc-start", session_id="stable-session"))
    clock[0] += timedelta(seconds=4)
    replaced = service.command(
        1, "start", _command("start", 1, "android-start", device="android", category="运动")
    )
    assert replaced["state"]["revision"] == 2
    assert replaced["state"]["session_id"] == "stable-session"
    assert replaced["state"]["category_name"] == "运动"
    assert replaced["state"]["active_elapsed_ms"] == 0
    conn = sqlite3.connect(path)
    segments = conn.execute(
        "SELECT category_name,active_elapsed_ms,ended_at FROM live_timer_segments ORDER BY created_at"
    ).fetchall()
    conn.close()
    assert segments[0][0:2] == ("输入", 4000)
    assert segments[0][2] is not None
    assert segments[1][0:2] == ("运动", 0)


def test_stale_current_intent_can_refresh_and_retry_once(tmp_path):
    service, _ = _service(tmp_path)
    service.command(1, "start", _command("start", 0, "start"))
    service.command(1, "switch", _command("switch", 1, "pc-switch", category="输出"))
    stale = service.command(
        1, "switch", _command("switch", 1, "android-attempt-1", device="android", category="家庭", intent="intent-a")
    )
    assert stale["error_code"] == "stale_timer_revision"
    assert stale["state"]["category_name"] == "输出"
    retried = service.command(
        1, "switch", _command("switch", 2, "android-attempt-2", device="android", category="家庭", intent="intent-a")
    )
    assert retried["status"] == "accepted"
    assert retried["state"]["revision"] == 3
    assert retried["state"]["category_name"] == "家庭"


def test_stop_is_cross_device_idempotent_and_publishes_one_history(tmp_path):
    clock = [datetime(2026, 7, 24, 20, 0, tzinfo=BEIJING)]
    service, path = _service(tmp_path, now=lambda: clock[0])
    service.command(1, "start", _command("start", 0, "start", session_id="stable-session"))
    clock[0] += timedelta(seconds=61)
    request = _command("stop", 1, "stop", device="android", session_summary="完成")
    stopped = service.command(1, "stop", request)
    replayed = service.command(1, "stop", request)
    assert stopped == replayed
    assert stopped["completed_session_id"] == "stable-session"
    assert stopped["state"]["state"] == "stopped"

    conn = sqlite3.connect(path)
    session = conn.execute(
        "SELECT id,net_duration_seconds,session_summary FROM server_study_sessions"
    ).fetchone()
    changes = conn.execute(
        "SELECT COUNT(*) FROM server_change_log WHERE table_name='server_study_sessions'"
    ).fetchone()[0]
    segments = conn.execute("SELECT COUNT(*) FROM live_timer_segments WHERE ended_at IS NOT NULL").fetchone()[0]
    backups = conn.execute(
        "SELECT stable_session_id,sync_state,COUNT(*) FROM server_atimelogger_backups "
        "GROUP BY stable_session_id,sync_state"
    ).fetchone()
    conn.close()
    assert session == ("stable-session", 61, "完成")
    assert changes == 1
    assert segments == 1
    assert backups == ("stable-session", "pending", 1)


def test_concurrent_same_revision_accepts_one_then_returns_latest_state(tmp_path):
    service, _ = _service(tmp_path)
    service.command(1, "start", _command("start", 0, "start"))
    requests = [
        _command("switch", 1, "pc", device="pc", category="输出"),
        _command("switch", 1, "android", device="android", category="家庭"),
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda payload: service.command(1, "switch", payload), requests))
    assert sorted(result["status"] for result in results) == ["accepted", "conflict"]
    assert max((result["state"] or {})["revision"] for result in results) == 2
