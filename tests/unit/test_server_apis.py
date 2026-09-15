# -*- coding: utf-8 -*-
import io
import importlib.util
import json
import os
import asyncio
import sqlite3
import pytest
import time
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from server.server import app
import server.server as server_module
from server.logging_config import LoggingConfigStore
from server.config_manager import ConfigManager
from server.models.server_schema import ensure_server_schema
from server.store import ServerSleepStore
from server.db_wrapper import ServerDBWrapper
from server.sync_hub import SyncHub, SYNC_TABLES
import server.sync_hub as sync_hub_module

TEST_DATE = datetime.now().strftime("%Y-%m-%d")


def _load_full_report_module():
    module_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "server", "skills", "time-management", "generate_full_report.py")
    )
    spec = importlib.util.spec_from_file_location("generate_full_report_test_module", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _login_headers(client, username="sleep_user"):
    client.post("/auth/register", json={"username": username, "password": "password123"})
    resp = client.post("/auth/login", json={"username": username, "password": "password123"})
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def _seed_ai_config(db_path, user_id=1):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO server_system_config (user_id, key, value, updated_at) VALUES (?, ?, ?, ?)",
            (user_id, "ai_model_config", json.dumps({
                "vision_base_url": "https://ai.example/v4",
                "vision_api_key": "vision-key",
                "vision_model": "vision-test",
                "text_base_url": "https://ai.example/v4",
                "text_api_key": "text-key",
                "text_model": "text-test",
            }), "2026-07-09 10:00:00"),
        )
        conn.commit()
    finally:
        conn.close()


def test_stale_sleep_upload_images_are_cleaned_without_removing_archives(tmp_path, monkeypatch):
    attachments_dir = tmp_path / "attachments"
    attachments_dir.mkdir()
    temp_image = attachments_dir / ("a" * 32 + "_sleep.jpg")
    archive_image = attachments_dir / "sleep_2026-07-01.jpg"
    temp_image.write_bytes(b"temp")
    archive_image.write_bytes(b"archive")
    old_time = time.time() - 7200
    os.utime(temp_image, (old_time, old_time))
    os.utime(archive_image, (old_time, old_time))

    monkeypatch.setattr(server_module, "ATTACHMENTS_DIR", str(attachments_dir))
    server_module._cleanup_stale_temp_upload_images(max_age_seconds=3600)

    assert not temp_image.exists()
    assert archive_image.exists()


def test_sleep_upload_temp_images_can_be_cleaned_immediately(tmp_path, monkeypatch):
    attachments_dir = tmp_path / "attachments"
    attachments_dir.mkdir()
    temp_image = attachments_dir / ("b" * 32 + "_sleep.jpg")
    archive_image = attachments_dir / "sleep_2026-07-02.jpg"
    temp_image.write_bytes(b"temp")
    archive_image.write_bytes(b"archive")

    monkeypatch.setattr(server_module, "ATTACHMENTS_DIR", str(attachments_dir))
    server_module._cleanup_stale_temp_upload_images(max_age_seconds=0)

    assert not temp_image.exists()
    assert archive_image.exists()


def test_full_sleep_report_uses_fixed_part2_numbering_and_unified_tone(tmp_path, monkeypatch):
    report_module = _load_full_report_module()
    report_path = tmp_path / "report.md"
    monkeypatch.setattr(report_module, "generate_report_filename", lambda date_str: str(report_path))

    data = {
        "date": "2026-07-01",
        "sleep": {
            "sleep_score": 67,
            "total_sleep_min": 286,
            "sleep_cycles": 3.18,
            "sleep_start": "00:42",
            "sleep_end": "06:36",
            "fall_asleep_min": 30,
            "wake_up_min": 90,
            "morning_diary": "早上复盘",
            "evening_diary": "晚上复盘",
            "official_advice": "建议保持规律作息，并改善睡前习惯。",
        },
        "atimelogger": {"activities": []},
        "summary": {"activity_breakdown": {}},
        "history_7day": [],
        "exercise": {},
    }
    analysis = {
        "insights": ["睡眠恢复不足"],
        "issues": ["睡眠时长不足"],
        "recommendations": ["今晚提前收尾"],
    }

    report_module.generate_full_report_file(data, analysis, "2026-07-01", include_time_analysis=True)
    content = report_path.read_text(encoding="utf-8")

    assert "### 2.5 待改善点" in content
    assert "### 2.6 行动建议" in content
    assert "### 2.7 晚间日记" in content
    assert "### 2.8" not in content
    assert "严厉批评" not in content
    assert "略显不足" not in content


def test_full_sleep_report_uses_fixed_section_template_and_improvement_points(tmp_path, monkeypatch):
    report_module = _load_full_report_module()
    report_path = tmp_path / "report.md"
    monkeypatch.setattr(report_module, "generate_report_filename", lambda date_str: str(report_path))

    data = {
        "date": "2026-07-01",
        "sleep": {
            "sleep_score": 80,
            "total_sleep_min": 333,
            "deep_sleep_min": 102,
            "sleep_cycles": 3.7,
            "awake_min": 33,
            "awake_count": 2,
            "fall_asleep_min": 132,
            "wake_up_min": 121,
            "atm_sleep_start": "22:04",
            "sleep_start": "00:47",
            "sleep_end": "08:54",
            "atm_sleep_end": "10:55",
            "morning_diary": "早上复盘",
            "evening_diary": "晚上复盘",
            "official_advice": "建议增加深睡比例，减少夜间醒来次数。",
        },
        "atimelogger": {"activities": []},
        "summary": {"activity_breakdown": {}},
        "history_7day": [
            {"date": "2026-06-30", "sleep_score": 70, "total_sleep_min": 300, "sleep_cycles": 3.3},
            {"date": "2026-07-01", "sleep_score": 80, "total_sleep_min": 333, "sleep_cycles": 3.7},
        ],
        "exercise": {"weight": 97.6, "daily_score": 12, "plan_version": "v1"},
    }
    report_module.generate_full_report_file(data, {"insights": [], "issues": [], "recommendations": []}, "2026-07-01", include_time_analysis=True)
    content = report_path.read_text(encoding="utf-8")

    assert "### 1.3 关键指标变化解读" in content
    assert "### 1.2.1" not in content
    assert "### 2.5 待改善点" in content
    assert "暂无明确核心问题点" not in content
    assert "睡眠周期只有 3.7 个" in content
    assert "浅睡时长" not in content
    assert "REM时长" not in content
    assert "睡眠连续性" not in content


def test_sleep_trend_merges_current_target_date_and_highlights_changes(tmp_path, monkeypatch):
    report_module = _load_full_report_module()
    report_path = tmp_path / "trend_report.md"
    monkeypatch.setattr(report_module, "generate_report_filename", lambda date_str: str(report_path))

    history = [
        {"date": "2026-06-25", "sleep_score": 81, "total_sleep_min": 418, "sleep_cycles": 4.66},
        {"date": "2026-06-30", "sleep_score": 60, "total_sleep_min": 174, "sleep_cycles": 1.93},
        {"date": "2026-07-01", "sleep_score": 77, "total_sleep_min": 333, "sleep_cycles": 3.70},
        {"date": "2026-07-02", "sleep_score": 68, "total_sleep_min": 300, "sleep_cycles": 3.33},
    ]
    current_sleep = {
        "date": "2026-07-03",
        "sleep_score": 82,
        "total_sleep_min": 390,
        "sleep_cycles": 4.33,
        "fall_asleep_min": 80,
        "wake_up_min": 20,
        "deep_sleep_ratio": 24,
        "awake_count": 1,
        "official_advice": "建议固定睡眠时间，保持安静睡眠环境。",
    }

    merged = report_module._merge_current_sleep_into_history(history, "2026-07-03", current_sleep)
    assert [row["date"] for row in merged][-1] == "2026-07-03"
    assert any(row["date"] == "2026-07-03" for row in merged)

    data = {
        "date": "2026-07-03",
        "sleep": current_sleep,
        "atimelogger": {"activities": []},
        "summary": {"activity_breakdown": {}},
        "history_7day": merged,
        "exercise": {},
    }
    report_module.generate_full_report_file(data, {"insights": ["趋势变化明显"], "recommendations": ["继续观察"]}, "2026-07-03", include_time_analysis=False)
    content = report_path.read_text(encoding="utf-8")

    assert "| 2026-07-03 | 82 分 |" in content
    assert "#### 重点趋势高亮" not in content
    assert "<div style=" not in content
    assert "#dc2626" in content
    assert "增长 20.59% ↑</span>" in content
    assert "14分" not in content
    decrease_lines = report_module.build_sleep_trend_insights([
        {"date": "2026-07-02", "sleep_score": 77, "total_sleep_min": 409, "sleep_cycles": 4.54},
        {"date": "2026-07-03", "sleep_score": 69, "total_sleep_min": 295, "sleep_cycles": 3.28},
    ])
    decrease_content = "\n".join(decrease_lines)
    assert "#16a34a" in decrease_content
    assert "减少 10.39% ↓</span>" in decrease_content
    assert "减少 27.87% ↓</span>" in decrease_content
    assert "8分" not in decrease_content
    assert "114分钟" not in decrease_content
    zero_base_lines = report_module.build_sleep_trend_insights([
        {"date": "2026-07-03", "wake_up_min": 0},
        {"date": "2026-07-04", "wake_up_min": 54},
    ])
    assert "增长 无法计算百分比 ↑</span>" in "\n".join(zero_base_lines)
    assert "增长 0.00%" not in "\n".join(zero_base_lines)


def test_sleep_report_requires_official_huawei_advice(tmp_path, monkeypatch):
    report_module = _load_full_report_module()
    report_path = tmp_path / "missing_advice.md"
    monkeypatch.setattr(report_module, "generate_report_filename", lambda date_str: str(report_path))

    data = {
        "date": "2026-07-04",
        "sleep": {
            "sleep_score": 69,
            "total_sleep_min": 295,
            "sleep_cycles": 3.28,
        },
        "atimelogger": {"activities": []},
        "summary": {"activity_breakdown": {}},
        "history_7day": [],
        "exercise": {},
    }

    with pytest.raises(ValueError, match="未识别到华为运动健康截图中的官方建议原文"):
        report_module.generate_full_report_file(data, {"insights": [], "recommendations": []}, "2026-07-04", include_time_analysis=False)

    assert not report_path.exists()


def test_sleep_report_renders_multiline_official_huawei_advice(tmp_path, monkeypatch):
    report_module = _load_full_report_module()
    report_path = tmp_path / "official_advice.md"
    monkeypatch.setattr(report_module, "generate_report_filename", lambda date_str: str(report_path))

    data = {
        "date": "2026-07-04",
        "sleep": {
            "sleep_score": 69,
            "total_sleep_min": 295,
            "sleep_cycles": 3.28,
            "official_advice": "睡眠质量待改善。睡眠时长严重不足，为 4 小时 19 分钟。长期睡眠不足可能使免疫力下降，导致容易感冒或肠胃问题。\n建议睡前洗热水澡，可促进血液循环、舒缓心情，改善睡眠质量。",
        },
        "atimelogger": {"activities": []},
        "summary": {"activity_breakdown": {}},
        "history_7day": [],
        "exercise": {},
    }

    report_module.generate_full_report_file(data, {"insights": [], "recommendations": []}, "2026-07-04", include_time_analysis=False)
    content = report_path.read_text(encoding="utf-8")

    assert "### 1.4 华为健康建议" in content
    assert "> 睡眠质量待改善。睡眠时长严重不足，为 4 小时 19 分钟。长期睡眠不足可能使免疫力下降，导致容易感冒或肠胃问题。" in content
    assert "> 建议睡前洗热水澡，可促进血液循环、舒缓心情，改善睡眠质量。" in content


def test_sleep_validation_error_reports_missing_field_details():
    valid, reason = server_module.SleepAnalyzer.validate_data({
        "sleep_score": 80,
        "deep_sleep_min": 90,
        "deep_sleep_ratio": 25,
        "sleep_start": "01:00",
        "sleep_end": "07:00",
        "total_sleep_min": 360,
    })

    assert valid is False
    assert "华为官方建议原文(official_advice)" in reason
    assert "睡眠评分(sleep_score)=80" in reason
    assert "夜间睡眠时长(total_sleep_min)=360" in reason


def test_sleep_validation_rejects_suggestion_only_official_advice():
    valid, reason = server_module.SleepAnalyzer.validate_data({
        "sleep_score": 62,
        "deep_sleep_min": 80,
        "light_sleep_min": 150,
        "rem_sleep_min": 29,
        "deep_sleep_ratio": 31,
        "sleep_start": "02:39",
        "sleep_end": "06:58",
        "total_sleep_min": 259,
        "official_advice": "建议睡前洗热水澡，可促进血液循环、舒缓心情，改善睡眠质量。",
    })

    assert valid is False
    assert "只识别到建议卡片" in reason
    assert "缺少“解读与建议”区域前半段解读原文" in reason


def test_exercise_summary_reads_server_db_wrapper_connection(tmp_path):
    report_module = _load_full_report_module()
    db_path = tmp_path / "server.db"
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE server_exercise_daily_logs (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            plan_version TEXT,
            weight REAL,
            score_snapshot TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO server_exercise_daily_logs (id, date, plan_version, weight, score_snapshot, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        ("log-1", "2026-07-01", "v1", 97.6, '{"total": 18, "cats": {"运动": {"s": 6, "m": 10}}}', "2026-07-01 12:00:00"),
    )
    conn.commit()
    conn.close()

    class WrapperOnlyGetConnection:
        def _get_connection(self):
            c = sqlite3.connect(db_path)
            c.row_factory = sqlite3.Row
            return c

    summary = report_module._build_exercise_summary(WrapperOnlyGetConnection(), "2026-07-01")
    assert summary["weight"] == 97.6
    assert summary["daily_score"] == 18
    assert summary["plan_version"] == "v1"


def test_exercise_summary_skips_weight_trend_when_target_weight_missing(tmp_path):
    report_module = _load_full_report_module()
    db_path = tmp_path / "server.db"
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE server_exercise_daily_logs (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            plan_version TEXT,
            weight REAL,
            score_snapshot TEXT,
            updated_at TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO server_exercise_daily_logs (id, date, plan_version, weight, score_snapshot, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("log-1", "2026-07-03", "v1", 100.0, '{"total": 70, "cats": {}}', "2026-07-03 08:00:00"),
            ("log-2", "2026-07-04", "v1", None, '{"total": 76, "cats": {}}', "2026-07-04 22:00:00"),
        ],
    )
    conn.commit()
    conn.close()

    class WrapperOnlyConnect:
        def _connect(self):
            c = sqlite3.connect(db_path)
            c.row_factory = sqlite3.Row
            return c

    summary = report_module._build_exercise_summary(WrapperOnlyConnect(), "2026-07-04")
    content = "\n".join(report_module.build_exercise_report_lines(summary))

    assert summary["weight"] is None
    assert "weight_delta" not in summary["trend"]
    assert "体重趋势" not in content
    assert "评分趋势" in content


class _TestSyncDb:
    def __init__(self, log_path):
        self.log_path = log_path


@pytest.fixture
def client_with_db(tmp_db_path):
    # Create a fresh store using the tmp_db_path
    test_store = ServerSleepStore(db_path=tmp_db_path)

    # Save the original store
    orig_store = server_module.store
    orig_sync_hub = server_module.sync_hub
    server_module.store = test_store
    server_module.sync_hub = SyncHub(_TestSyncDb(tmp_db_path))

    # Create a client
    client = TestClient(app)

    yield client, test_store

    # Restore original store
    server_module.store = orig_store
    server_module.sync_hub = orig_sync_hub


def test_ping_returns_core_health_correlation_headers():
    response = TestClient(app).get("/ping", headers={"X-Request-ID": "core-health-contract"})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["x-request-id"] == "core-health-contract"
    assert response.headers["x-core-stage"] == "responded"


def test_core_sync_routes_expose_correlation_without_provider_execution(client_with_db):
    client, _store = client_with_db
    headers = _login_headers(client, "core_health_user")

    pushed = client.post(
        "/api/sync/push",
        headers={**headers, "X-Sync-Run-ID": "core-push-contract"},
        json={"operations": [], "sync_scope": "core"},
    )
    pulled = client.get(
        "/api/sync/pull?sync_scope=core&refresh=false",
        headers={**headers, "X-Sync-Run-ID": "core-pull-contract"},
    )

    assert pushed.status_code == 200
    assert pushed.headers["x-request-id"] == "core-push-contract"
    assert pushed.headers["x-core-stage"] == "responded"
    assert pushed.json()["diagnostics"] == {
        "scope": "core", "provider_requested": False, "provider_executed": False,
    }
    assert pulled.status_code == 200
    assert pulled.headers["x-request-id"] == "core-pull-contract"
    assert pulled.headers["x-core-stage"] == "responded"
    assert pulled.json()["diagnostics"]["scope"] == "core"
    assert pulled.json()["diagnostics"]["provider_executed"] is False


def test_auth_second_registration_and_incomplete_seed_recovery(client_with_db):
    client, store = client_with_db
    for username in ("first_user", "second_user"):
        response = client.post("/auth/register", json={"username": username, "password": "password123"})
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    assert store.create_user("incomplete_user", "password123")
    incomplete_user_id = store.verify_user("incomplete_user", "password123")
    response = client.post("/auth/login", json={"username": "incomplete_user", "password": "password123"})

    assert response.status_code == 200
    with sqlite3.connect(store.db_path) as conn:
        marker = conn.execute(
            "SELECT 1 FROM server_sample_data_initializations WHERE user_id=? AND module='learning'",
            (incomplete_user_id,),
        ).fetchone()
    assert marker is not None


def test_auth_and_categories_sessions(client_with_db, monkeypatch):
    client, test_store = client_with_db

    # 1. Register a user
    resp = client.post("/auth/register", json={"username": "test_user", "password": "password123"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    # 2. Login
    resp = client.post("/auth/login", json={"username": "test_user", "password": "password123"})
    assert resp.status_code == 200
    token = resp.json()["token"]
    assert token is not None

    headers = {"Authorization": f"Bearer {token}"}

    # 3. Create a category
    resp = client.post("/api/categories", json={
        "name": "学习",
        "group_name": "输入",
        "icon": "📚",
        "color": "blue"
    }, headers=headers)
    assert resp.status_code == 200
    cat_id = resp.json()["category_id"]

    # 4. List categories
    resp = client.get("/api/categories", headers=headers)
    assert resp.status_code == 200
    cats = resp.json()["categories"]
    assert len(cats) == 16
    assert any(cat["name"] == "学习" for cat in cats)
    assert any(cat["name"] == "运动" and cat["icon"] == "atm:sp_068" for cat in cats)
    assert next(cat for cat in cats if cat["name"] == "学习")["id"] == cat_id

    # 5. Create a session
    resp = client.post("/api/sessions", json={
        "start_time": f"{TEST_DATE} 09:00:00",
        "end_time": f"{TEST_DATE} 10:00:00",
        "net_duration_minutes": 60.0,
        "date": TEST_DATE,
        "day_of_week": "Tuesday",
        "pause_count": 0,
        "category_id": cat_id
    }, headers=headers)
    assert resp.status_code == 200
    sess_id = resp.json()["session_id"]
    assert sess_id is not None

    # 6. List sessions
    resp = client.get("/api/sessions", headers=headers)
    assert resp.status_code == 200
    sessions = resp.json()["sessions"]
    assert len(sessions) == 1
    assert sessions[0]["net_duration_minutes"] == 60.0

    # 7. Get today summary
    resp = client.get(f"/api/sessions/today_summary?date={TEST_DATE}", headers=headers)
    assert resp.status_code == 200
    summary = resp.json()["summary"]
    assert summary["输入"] == 60.0

    # 8. Habits API
    # Create habit
    resp = client.post("/api/habits", json={"name": "早起", "icon": "🌅", "difficulty": "easy"}, headers=headers)
    assert resp.status_code == 200
    habit_id = resp.json()["habit_id"]

    # Checkin habit
    resp = client.post(f"/api/habits/{habit_id}/checkin", json={"date": TEST_DATE}, headers=headers)
    assert resp.status_code == 200

    # List today checkins
    resp = client.get(f"/api/habits/today_checkins?date={TEST_DATE}", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["checkins"]) == 1

    # Check wallet balance (easy habit = 5 coins)
    resp = client.get("/api/rewards/balance", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["balance"] == 5.0

    # 9. Goals API & Settle
    # Create goal (metric: duration, target: 45m, period: daily, reward: 20 coins)
    resp = client.post("/api/goals", json={
        "title": "每日学习",
        "category_id": cat_id,
        "metric": "duration",
        "target_value": 45.0,
        "period": "daily",
        "reward_coins": 20.0,
        "operator": ">="
    }, headers=headers)
    assert resp.status_code == 200
    goal_id = resp.json()["goal_id"]

    # Settle goals (sessions 60m >= target 45m -> awards 20 coins)
    next_day = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d 00:00:01")
    monkeypatch.setattr("server.store.now_str", lambda: next_day)
    resp = client.post("/api/goals/auto_settle", headers=headers)
    assert resp.status_code == 200
    settled = resp.json()["settled"]
    assert len(settled) == 1
    assert settled[0]["amount"] == 20.0

    # Balance should be 5 + 20 = 25
    resp = client.get("/api/rewards/balance", headers=headers)
    assert resp.json()["balance"] == 25.0

    # 10. Reward Shop & Backpack
    # Create shop reward (price: 15)
    resp = client.post("/api/rewards", json={"title": "看电影", "icon": "🎬", "price": 15.0}, headers=headers)
    assert resp.status_code == 200
    reward_id = resp.json()["reward_id"]

    # Buy reward (deducts 15, leaves 10)
    resp = client.post(f"/api/rewards/buy/{reward_id}", headers=headers)
    assert resp.status_code == 200

    resp = client.get("/api/rewards/balance", headers=headers)
    assert resp.json()["balance"] == 10.0

    # Check backpack
    resp = client.get("/api/rewards/backpack", headers=headers)
    assert resp.status_code == 200
    backpack = resp.json()["backpack"]
    assert len(backpack) == 1
    assert backpack[0]["title"] == "看电影"

    # Use item
    backpack_ledger_id = backpack[0]["id"]
    resp = client.post(f"/api/rewards/use_item/{backpack_ledger_id}", headers=headers)
    assert resp.status_code == 200

    # Backpack retains the consumed item as usage history.
    resp = client.get("/api/rewards/backpack", headers=headers)
    backpack = resp.json()["backpack"]
    assert len(backpack) == 1
    assert backpack[0]["is_used"] is True
    assert backpack[0]["used_at"]

    # 11. Sleep Data API
    # Save sleep data
    resp = client.post("/api/sleep/data", json={
        "date": TEST_DATE,
        "data": {"sleep_score": 85, "total_sleep_min": 480}
    }, headers=headers)
    assert resp.status_code == 200

    # Get sleep data
    resp = client.get(f"/api/sleep/data/{TEST_DATE}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["sleep_data"]["sleep_score"] == 85
    assert resp.json()["sleep_data"]["total_sleep_min"] == 480

    # 12. Tasks API
    # List active tasks (initially empty)
    resp = client.get("/api/tasks", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["tasks"]) == 0

    # Upsert task
    resp = client.post("/api/tasks", json={
        "task": {
            "id": "ticktick-task-1",
            "title": "编写单元测试",
            "priority": 3,
            "status": 0,
            "category_id": cat_id,
            "project_name": "Inbox"
        }
    }, headers=headers)
    assert resp.status_code == 200

    # List active tasks (now contains 1 active task)
    resp = client.get("/api/tasks", headers=headers)
    assert resp.status_code == 200
    tasks = resp.json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["id"] == "ticktick-task-1"
    assert tasks[0]["title"] == "编写单元测试"
    assert tasks[0]["priority"] == 3

    # Update task status (status=1 means completed)
    resp = client.put("/api/tasks/ticktick-task-1/status", json={"status": 1}, headers=headers)
    assert resp.status_code == 200

    # List active tasks (completed tasks should be filtered out)
    resp = client.get("/api/tasks", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["tasks"]) == 0

    # 13. ATM API
    # Save ATM data
    resp = client.post("/api/atm/data", json={
        "date": TEST_DATE,
        "data": {
            "activities": [
                {"activity_type": "编程", "start_time": f"{TEST_DATE} 14:00:00", "end_time": f"{TEST_DATE} 15:00:00", "duration_minutes": 60, "comment": "code"}
            ]
        }
    }, headers=headers)
    assert resp.status_code == 200

    # Get ATM data
    resp = client.get(f"/api/atm/data/{TEST_DATE}", headers=headers)
    assert resp.status_code == 200
    atm_data = resp.json()["atm_data"]
    assert atm_data["date"] == TEST_DATE
    assert len(atm_data["activities"]) == 1
    assert atm_data["activities"][0]["type"] == "编程"
    assert atm_data["activities"][0]["duration"] == 3600


def test_session_api_publishes_versioned_changes_and_rolls_back_on_log_failure(client_with_db, monkeypatch):
    client, store = client_with_db
    headers = _login_headers(client, "session_version_user")

    def version():
        with store._connect() as conn:
            return conn.execute("SELECT COALESCE(MAX(server_version), 0) FROM server_change_log WHERE user_id=1").fetchone()[0]

    def create(summary):
        return client.post("/api/sessions", headers=headers, json={
            "start_time": "2026-07-27 10:00:00", "end_time": "2026-07-27 10:10:00",
            "net_duration_minutes": 10, "date": "2026-07-27", "session_summary": summary,
        })

    before_create = version()
    created = create("跨端新增")
    assert created.status_code == 200
    session_id = created.json()["session_id"]
    created_pull = asyncio.run(server_module.sync_hub.handle_pull_by_version(before_create, user_id=1))
    assert created_pull["tables"]["study_sessions"][0]["id"] == session_id

    before_delete = version()
    assert client.delete(f"/api/sessions/{session_id}", headers=headers).status_code == 200
    deleted_pull = asyncio.run(server_module.sync_hub.handle_pull_by_version(before_delete, user_id=1))
    assert deleted_pull["tables"]["study_sessions"][0]["id"] == session_id
    assert deleted_pull["tables"]["study_sessions"][0]["_sync_operation"] == "delete"
    assert client.delete(f"/api/sessions/{session_id}", headers=headers).status_code == 404

    kept = create("事务回滚")
    kept_id = kept.json()["session_id"]
    monkeypatch.setattr(server_module.ServerDBWrapper, "write_server_change", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("log failed")))
    with pytest.raises(RuntimeError, match="log failed"):
        client.delete(f"/api/sessions/{kept_id}", headers=headers)
    with pytest.raises(RuntimeError, match="log failed"):
        create("新增回滚")
    with store._connect() as conn:
        assert conn.execute("SELECT 1 FROM server_study_sessions WHERE user_id=1 AND id=?", (kept_id,)).fetchone() is not None
        assert conn.execute("SELECT 1 FROM server_study_sessions WHERE user_id=1 AND session_summary='新增回滚'").fetchone() is None


def test_goal_reward_backpack_commands_are_versioned_idempotent_and_account_scoped(client_with_db, monkeypatch):
    client, store = client_with_db
    headers = _login_headers(client, "goal_reward_owner")

    reward = client.post("/api/rewards", headers=headers, json={"title": "解锁奖品", "icon": "🎁", "price": 0})
    assert reward.status_code == 200
    reward_id = reward.json()["reward_id"]
    with store._connect() as conn:
        before_goal = conn.execute("SELECT COALESCE(MAX(server_version), 0) FROM server_change_log WHERE user_id=1").fetchone()[0]

    goal = client.post("/api/goals", headers=headers, json={
        "title": "单次专注", "category_id": None, "metric": "count", "target_value": 1,
        "period": "per_session", "reward_coins": 0, "penalty_coins": 0, "operator": ">=", "reward_id": reward_id,
    })
    assert goal.status_code == 200
    pulled_goal = asyncio.run(server_module.sync_hub.handle_pull_by_version(before_goal, user_id=1))
    assert pulled_goal["tables"]["goals"][0]["period"] == "per_session"
    assert pulled_goal["tables"]["goals"][0]["reward_id"] is None

    with store._connect() as conn:
        conn.execute(
            "INSERT INTO server_tasks (id, user_id, title, status, updated_at) VALUES ('unlock-task', 1, '完成任务', 0, '2026-08-01 10:00:00')"
        )
        conn.commit()
    unlock_reward = client.post("/api/rewards", headers=headers, json={
        "title": "任务解锁", "icon": "🏆", "price": 0, "unlock_task_id": "unlock-task",
    })
    assert unlock_reward.status_code == 200
    with store._connect() as conn:
        conn.execute("UPDATE server_tasks SET status=2 WHERE id='unlock-task' AND user_id=1")
        conn.commit()

    client.get("/api/rewards", headers=headers)
    client.get("/api/rewards", headers=headers)
    backpack = client.get("/api/rewards/backpack", headers=headers).json()["backpack"]
    unlocked = next(item for item in backpack if item["title"] == "任务解锁")
    assert len([item for item in backpack if item["title"] == "任务解锁"]) == 1
    assert client.post(f"/api/rewards/use_item/{unlocked['id']}", headers=headers).status_code == 200
    assert client.post(f"/api/rewards/use_item/{unlocked['id']}", headers=headers).status_code == 200
    used = next(item for item in client.get("/api/rewards/backpack", headers=headers).json()["backpack"] if item["id"] == unlocked["id"])
    assert used["is_used"] is True and used["used_at"]

    assert client.delete(f"/api/rewards/{unlock_reward.json()['reward_id']}", headers=headers).status_code == 200
    retired = next(item for item in client.get("/api/rewards/backpack", headers=headers).json()["backpack"] if item["id"] == unlocked["id"])
    assert retired["title"] in {"任务解锁", "已下架奖励"}

    category = client.post("/api/categories", headers=headers, json={
        "name": "结算分类", "group_name": "输入", "icon": "📚", "color": "blue",
    })
    assert category.status_code == 200
    bound_goal = client.post("/api/goals", headers=headers, json={
        "title": "绑定奖品目标", "category_id": category.json()["category_id"], "metric": "duration", "target_value": 1,
        "period": "per_session", "reward_coins": 99, "penalty_coins": 0, "reward_id": reward_id,
    })
    assert bound_goal.status_code == 200
    assert client.put(f"/api/rewards/{reward_id}", headers=headers, json={
        "price": 0, "unlock_source_type": "goal", "unlock_source_id": bound_goal.json()["goal_id"],
    }).status_code == 200
    start = datetime.now() + timedelta(minutes=1)
    session = client.post("/api/sessions", headers=headers, json={
        "start_time": start.strftime("%Y-%m-%d %H:%M:%S"),
        "end_time": (start + timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S"),
        "net_duration_minutes": 2, "date": start.strftime("%Y-%m-%d"),
        "category_id": category.json()["category_id"], "session_summary": "绑定奖励结算",
    })
    assert session.status_code == 200
    assert client.post("/api/goals/auto_settle", headers=headers).status_code == 200
    assert client.post("/api/goals/auto_settle", headers=headers).status_code == 200
    bound_items = [item for item in client.get("/api/rewards/backpack", headers=headers).json()["backpack"] if item["reward_id"] == reward_id]
    assert len(bound_items) == 1
    assert client.get("/api/rewards/balance", headers=headers).json()["balance"] == 99.0

    monkeypatch.setattr(store, "_record_server_change", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("log failed")))
    with pytest.raises(RuntimeError, match="log failed"):
        client.post("/api/goals", headers=headers, json={
            "title": "日志失败目标", "category_id": None, "metric": "count", "target_value": 1,
            "period": "daily", "reward_coins": 0,
        })
    with store._connect() as conn:
        assert conn.execute("SELECT 1 FROM server_goals WHERE user_id=1 AND title='日志失败目标'").fetchone() is None
    monkeypatch.undo()

    second_headers = _login_headers(client, "goal_reward_other")
    ignored_legacy_binding = client.post("/api/goals", headers=second_headers, json={
        "title": "越权目标", "category_id": None, "metric": "count", "target_value": 1,
        "period": "daily", "reward_coins": 0, "reward_id": reward_id,
    })
    assert ignored_legacy_binding.status_code == 200
    assert client.post("/api/rewards", headers=second_headers, json={
        "title": "越权解锁", "price": 0, "unlock_task_id": f"goal_{goal.json()['goal_id']}",
    }).status_code == 400


def test_sleep_serves_mobile_sleep_page_and_root_is_not_sleep_entry(client_with_db):
    client, _ = client_with_db

    login_resp = client.get("/login")
    assert login_resp.status_code == 200
    assert "运动界面" in login_resp.text
    assert "睡眠界面" in login_resp.text

    resp = client.get("/sleep")

    assert resp.status_code == 200
    body = resp.text
    assert "MyTimeLogger 睡眠" in body
    assert "手机内网睡眠分析入口" in body
    assert "/upload?analyze=false&date=" in body
    assert "/status_by_date/" in body
    assert "sleepDates" in body
    assert "/api/sleep/history?limit=90" in body
    assert "图片已上传" in body
    assert "body.progress?.msg" in body
    assert "强制分析" in body
    assert "JSON.stringify({date: currentDate, full, force})" in body
    assert "runAnalysis(true, true)" in body
    assert "data-diary-edit" in body
    assert "diaryMarkdownToHtml" in body
    assert "实时预览" not in body
    assert "/morning_diary" in body
    assert "/evening_diary" in body
    assert "/generate_report" in body
    assert "/login?next=sleep" in body
    assert "Data Visualization" not in body
    assert "Sleep Dashboard" not in body

    root_resp = client.get("/")
    assert root_resp.status_code == 404


def test_exercise_page_and_server_checkin_flow(client_with_db, monkeypatch):
    client, store = client_with_db
    fixed_now = datetime(2026, 7, 10, 8, 0, 0, tzinfo=server_module.timezone(server_module.timedelta(hours=8)))
    monkeypatch.setattr(server_module, "_beijing_now", lambda: fixed_now)
    headers = _login_headers(client, "exercise_page_user")
    today = server_module._beijing_today()
    day_key = server_module._exercise_day_key(today)
    now = server_module._exercise_now_str()
    with store._connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO server_exercise_plan_versions
              (version, user_id, title, source_name, is_active, exercise_points, created_at, updated_at)
            VALUES ('v1', 1, '每日打卡表', 'client-sync', 1, 40, ?, ?)
            """,
            (now, now),
        )
        conn.execute(
            """INSERT INTO server_system_config(user_id,key,value,updated_at)
               VALUES(1,'active_exercise_plan_version','v1',?)
               ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
            (now,),
        )
        conn.execute(
            """
            INSERT INTO server_exercise_plan_schedule_items
              (id, user_id, plan_version, schedule_type, sort_order, time, item, note, accent, created_at, updated_at)
            VALUES ('sched-v1-0', 1, 'v1', 'weekday', 0, '7:30', '起床后空腹称体重、体脂并记录', '每天记，看趋势', 'sleep', ?, ?)
            """,
            (now, now),
        )
        conn.execute(
            """
            INSERT INTO server_exercise_plan_diet_rules
              (id, user_id, plan_version, sort_order, time, content, note, created_at, updated_at)
            VALUES ('diet-v1-0', 1, 'v1', 0, '早饭', '正常吃早饭', '主食减半', ?, ?)
            """,
            (now, now),
        )
        conn.execute(
            """
            INSERT INTO server_exercise_plan_score_rules
              (id, user_id, plan_version, day_type, sort_order, schedule_index, points, category, target_time, created_at, updated_at)
            VALUES
              ('score-v1-0', 1, 'v1', 'weekday', 0, 0, 5, '检验', NULL, ?, ?),
              ('score-v1-1', 1, 'v1', 'weekday', 1, 1, 7, '工作', NULL, ?, ?),
              ('score-v1-2', 1, 'v1', 'weekday', 2, 2, 2, '拉伸', NULL, ?, ?),
              ('score-v1-3', 1, 'v1', 'weekday', 3, 3, 2, '守时', NULL, ?, ?)
            """,
            (now, now, now, now, now, now, now, now),
        )
        conn.execute(
            """
            INSERT INTO server_exercise_plan_category_rules
              (id, user_id, plan_version, sort_order, category, created_at, updated_at)
            VALUES
              ('cat-v1-0', 1, 'v1', 0, '检验', ?, ?),
              ('cat-v1-1', 1, 'v1', 1, '工作', ?, ?),
              ('cat-v1-2', 1, 'v1', 2, '拉伸', ?, ?),
              ('cat-v1-3', 1, 'v1', 3, '守时', ?, ?),
              ('cat-v1-4', 1, 'v1', 4, '运动', ?, ?)
            """,
            (now, now, now, now, now, now, now, now, now, now),
        )
        conn.execute(
            """
            INSERT INTO server_exercise_plan_items
              (id, user_id, plan_version, day_key, variant, section, sort_order, name, sets, intensity, tags_json, progression, color, is_active, created_at, updated_at)
            VALUES (?, 1, 'v1', ?, 'schedule', '全天时刻表', 0, '起床后空腹称体重、体脂并记录', '7:30', '每天记，看趋势', '{}', NULL, NULL, 1, ?, ?)
            """,
            ("test-schedule-item", day_key, now, now),
        )
        conn.execute(
            """
            INSERT INTO server_exercise_plan_items
              (id, user_id, plan_version, day_key, variant, section, sort_order, name, sets, intensity, tags_json, progression, color, is_active, created_at, updated_at)
            VALUES (?, 1, 'v1', ?, 'gym', '无氧', 1, '高拉训练器（正握）', '3×15次', '最后2–3次感觉费力', '{}', NULL, NULL, 1, ?, ?)
            """,
            ("test-exercise-item", day_key, now, now),
        )
        conn.commit()

    page = client.get("/exercise")
    assert page.status_code == 200
    assert "MyTimeLogger 运动" in page.text
    assert "/api/exercise/state" in page.text
    assert "每日打卡表" in page.text
    assert "全天时刻表" in page.text
    assert "运动·饮食·其他" in page.text
    assert "ex-card ex-schedule" in page.text
    assert "if (tab === 'sched')" in page.text
    assert "const key = item.section || '运动'" in page.text
    assert "体重未填" not in page.text
    assert "recordSummary.classList.toggle('hidden', state.weight == null)" in page.text
    assert "timeZone: 'Asia/Shanghai'" in page.text
    assert "bottom-nav" not in page.text
    assert "/login?next=exercise" in page.text
    assert 'id="username"' not in page.text
    assert "实际打卡" in page.text
    assert "历史记录" in page.text
    assert "重置当天" not in page.text
    assert "导出CSV" not in page.text
    assert "新一周" not in page.text
    assert "参考面板" not in page.text

    state = client.get(f"/api/exercise/state?date={today}", headers=headers)
    assert state.status_code == 200
    body = state.json()
    assert body["status"] == "ok"
    assert body["locked"] is False
    assert body["items"]
    assert len(body["items"]) >= 2
    assert body["plan_definition"]["exercisePoints"] == 40
    assert any(row["item"] == "起床后空腹称体重、体脂并记录" for row in body["plan_definition"]["weekdaySchedule"])
    assert any(row["content"] == "正常吃早饭" for row in body["plan_definition"]["diet"])
    assert [0, 5, "检验"] in body["plan_definition"]["weekdayScore"]
    assert set(body["plan_definition"]["categoryOrder"]) >= {"检验", "工作", "拉伸", "守时", "运动"}
    assert set(body["score"]["cats"].keys()) >= {"检验", "工作", "拉伸", "守时", "运动"}
    assert any(item["section"] == "全天时刻表" for item in body["items"])
    assert any(item["section"] in ("无氧", "有氧", "回家后") for item in body["items"])
    assert body["weight_window"]["editable"] is True
    assert body["weight_window"]["overdue"] is False
    assert body["weight_window"]["start_hour"] == 6
    assert body["weight_window"]["end_hour"] == 9
    assert body["history"] == []
    item = body["items"][0]
    skip_item = body["items"][1]

    checkin = client.post(
        "/api/exercise/checkin",
        headers=headers,
        json={
            "date": today,
            "plan_version": body["plan_version"],
            "item_key": item["item_key"],
            "item_name": item["name"],
            "status": 1,
            "completed_time": "08:00",
        },
    )
    assert checkin.status_code == 200
    assert checkin.json()["checkin"]["completed_time"] == "08:00"
    with store._connect() as conn:
        saved_checkin = conn.execute(
            "SELECT completed_time FROM server_exercise_checkins WHERE user_id=? AND date=? AND item_key=?",
            (1, today, item["item_key"]),
        ).fetchone()
    assert saved_checkin["completed_time"] == "08:00"

    failed = client.post(
        "/api/exercise/checkin",
        headers=headers,
        json={
            "date": today,
            "plan_version": body["plan_version"],
            "item_key": skip_item["item_key"],
            "item_name": skip_item["name"],
            "status": -1,
            "completed_time": "08:30",
        },
    )
    assert failed.status_code == 200
    failed_body = failed.json()["checkin"]
    assert failed_body["status"] == -1
    assert failed_body["completed_time"] is None

    cancelled = client.post(
        "/api/exercise/checkin",
        headers=headers,
        json={
            "date": today,
            "plan_version": body["plan_version"],
            "item_key": skip_item["item_key"],
            "item_name": skip_item["name"],
            "status": 0,
            "completed_time": "08:40",
        },
    )
    assert cancelled.status_code == 200
    cancelled_body = cancelled.json()["checkin"]
    assert cancelled_body["status"] == 0
    assert cancelled_body["completed_time"] is None

    state_after = client.get(f"/api/exercise/state?date={today}&plan_version={body['plan_version']}", headers=headers)
    score = state_after.json()["score"]
    assert score["completed_items"] == 1

    daily = client.post(
        "/api/exercise/daily",
        headers=headers,
        json={
            "date": today,
            "plan_version": body["plan_version"],
            "day_name": state_after.json()["day_key"],
            "weight": 80.5,
            "body_fat_rate": 21.5,
            "completed_items": score["completed_items"],
            "total_items": score["total_items"],
            "score_snapshot": score,
        },
    )
    assert daily.status_code == 200
    assert daily.json()["daily_log"]["weight"] == 80.5
    assert daily.json()["daily_log"]["body_fat_rate"] == 21.5

    history_state = client.get(f"/api/exercise/state?date={today}&plan_version={body['plan_version']}", headers=headers).json()
    assert history_state["history"][0]["date"] == today
    assert history_state["history"][0]["weight"] == 80.5
    assert history_state["history"][0]["body_fat_rate"] == 21.5
    assert history_state["history"][0]["completed_items"] == 1
    assert history_state["history"][0]["total_items"] == score["total_items"]
    assert history_state["history"][0]["completion_rate"] >= 0

    late_now = datetime(2026, 7, 10, 10, 0, 0, tzinfo=server_module.timezone(server_module.timedelta(hours=8)))
    monkeypatch.setattr(server_module, "_beijing_now", lambda: late_now)
    late_state = client.get(f"/api/exercise/state?date={today}&plan_version={body['plan_version']}", headers=headers).json()
    assert late_state["weight_window"]["editable"] is True
    assert late_state["weight_window"]["overdue"] is False
    late_weight = client.post(
        "/api/exercise/daily",
        headers=headers,
        json={
            "date": today,
            "plan_version": body["plan_version"],
            "day_name": late_state["day_key"],
            "weight": 81.0,
            "completed_items": score["completed_items"],
            "total_items": score["total_items"],
            "score_snapshot": score,
        },
    )
    assert late_weight.status_code == 200
    assert late_weight.json()["daily_log"]["weight"] == 81.0
    invalid_weight = client.post(
        "/api/exercise/daily",
        headers=headers,
        json={**late_weight.json()["daily_log"], "weight": 201},
    )
    assert invalid_weight.status_code == 422
    invalid_body_fat = client.post(
        "/api/exercise/daily",
        headers=headers,
        json={**late_weight.json()["daily_log"], "body_fat_rate": 76},
    )
    assert invalid_body_fat.status_code == 422
    score_only = client.post(
        "/api/exercise/daily",
        headers=headers,
        json={
            "date": today,
            "plan_version": body["plan_version"],
            "day_name": late_state["day_key"],
            "weight": None,
            "completed_items": score["completed_items"],
            "total_items": score["total_items"],
            "score_snapshot": score,
        },
    )
    assert score_only.status_code == 200

    other_plan = client.get(f"/api/exercise/state?date={today}&plan_version=v1", headers=headers)
    assert other_plan.status_code == 200
    assert other_plan.json()["weight"] == 81.0
    assert other_plan.json()["body_fat_rate"] == 21.5

    yesterday = (server_module._beijing_now() - timedelta(days=1)).strftime("%Y-%m-%d")
    locked = client.post(
        "/api/exercise/checkin",
        headers=headers,
        json={"date": yesterday, "plan_version": "v0", "item_key": f"sc-{yesterday}-0", "status": 1},
    )
    assert locked.status_code == 409


def test_exercise_state_uses_database_only_when_plan_items_missing(client_with_db):
    client, _ = client_with_db
    headers = _login_headers(client, "exercise_empty_plan_user")
    today = server_module._beijing_today()

    state = client.get(f"/api/exercise/state?date={today}&plan_version=missing-v9", headers=headers)

    assert state.status_code == 200
    assert state.json()["items"] == []


def test_body_metric_deadline_lock_allows_data_backfill_without_reopening_checkin(client_with_db, monkeypatch):
    client, store = client_with_db
    fixed_now = datetime(2026, 7, 10, 9, 1, tzinfo=server_module.timezone(server_module.timedelta(hours=8)))
    monkeypatch.setattr(server_module, "_beijing_now", lambda: fixed_now)
    headers = _login_headers(client, "body_metric_deadline_user")
    date, now = server_module._beijing_today(), server_module._exercise_now_str()
    with store._connect() as conn:
        conn.execute("INSERT INTO server_exercise_plan_versions(version,user_id,title,source_name,is_active,created_at,updated_at) VALUES('deadline-v1',1,'每日打卡表','test',1,?,?)", (now, now))
        conn.execute("INSERT INTO server_system_config(user_id,key,value,updated_at) VALUES(1,'active_exercise_plan_version','deadline-v1',?) ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value", (now,))
        conn.execute("INSERT INTO server_system_config(user_id,key,value,updated_at) VALUES(1,'statistics_start_date',?,?) ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value", (date, now))
        conn.execute("INSERT INTO server_exercise_plan_schedule_items(id,user_id,plan_version,schedule_type,sort_order,time,item,accent,created_at,updated_at) VALUES('deadline-weight',1,'deadline-v1','weekday',0,'7:30','起床后空腹称体重、体脂并记录','sleep',?,?)", (now, now))
        conn.commit()

    assert server_module._lock_overdue_body_metrics() == 1
    state = client.get(f"/api/exercise/state?date={date}&plan_version=deadline-v1", headers=headers).json()
    locked = state["checkins"][0]
    assert locked["status"] == -1 and locked["locked_at"] and locked["lock_reason"] == "body_metrics_missing_at_09:00"
    with store._connect() as conn:
        penalty = conn.execute("SELECT amount,source_type,source_id,target_date FROM server_reward_ledger WHERE user_id=1").fetchone()
    assert tuple(penalty) == (-50, "body_metric_deadline_penalty", f"body-metric-deadline:{date}", date)
    assert server_module._lock_overdue_body_metrics() == 0
    assert client.post("/api/exercise/checkin", headers=headers, json={"date": date, "plan_version": "deadline-v1", "item_key": locked["item_key"], "status": 0}).status_code == 409
    backfill = client.post("/api/exercise/daily", headers=headers, json={"date": date, "plan_version": "deadline-v1", "weight": 80, "body_fat_rate": 20, "completed_items": 99, "total_items": 99, "score_snapshot": {"total": 100}})
    assert backfill.status_code == 200
    assert backfill.json()["daily_log"]["weight"] == 80 and backfill.json()["daily_log"]["body_fat_rate"] == 20
    monkeypatch.setattr(sync_hub_module, "_cst_today", lambda: date)
    ok, rejected = server_module.sync_hub.upsert("exercise_daily_logs", {"id": "offline-daily", "date": date, "plan_version": "deadline-v1", "weight": 81, "body_fat_rate": 21, "completed_items": 99, "total_items": 99, "score_snapshot": "{\"total\":100}"}, 1)
    assert ok and not rejected
    with store._connect() as conn:
        daily = conn.execute("SELECT weight,body_fat_rate,completed_items,total_items,score_snapshot FROM server_exercise_daily_logs WHERE user_id=1 AND date=? AND plan_version='deadline-v1'", (date,)).fetchone()
        penalty_count = conn.execute("SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=1 AND source_type='body_metric_deadline_penalty'", ()).fetchone()[0]
    assert tuple(daily) == (81, 21, 0, 0, None) and penalty_count == 1
    refreshed = client.get(f"/api/exercise/state?date={date}&plan_version=deadline-v1", headers=headers).json()
    refreshed_lock = refreshed["checkins"][0]
    assert refreshed["weight"] == 81 and refreshed["body_fat_rate"] == 21 and refreshed["body_metric_locked"] is True
    assert refreshed_lock["status"] == -1 and refreshed_lock["deadline_penalty_source_id"] == f"body-metric-deadline:{date}"
    allowed = client.post("/api/exercise/checkin", headers=headers, json={"date": date, "plan_version": "deadline-v1", "item_key": f"sc-{date}-1", "item_name": "普通项目", "status": 1})
    assert allowed.status_code == 200
    ok, rejected = server_module.sync_hub.upsert("exercise_checkins", {"id": "offline", "date": date, "plan_version": "deadline-v1", "item_key": locked["item_key"], "status": 1}, 1)
    assert not ok and rejected[0]["reason"] == "body_metrics_deadline_locked"


def test_exercise_checkin_persists_completed_time(client_with_db):
    client, store = client_with_db
    headers = _login_headers(client, "exercise_checkin_time_user")
    today = server_module._beijing_today()
    resp = client.post(
        "/api/exercise/checkin",
        headers=headers,
        json={
            "date": today,
            "plan_version": "v0",
            "item_key": "actual-time-check",
            "item_name": "记录实际打卡时间",
            "status": 1,
            "completed_time": "2026-07-05 08:00:00",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["checkin"]["completed_time"] == "2026-07-05 08:00:00"
    with store._connect() as conn:
        row = conn.execute(
            "SELECT completed_time FROM server_exercise_checkins WHERE user_id=? AND date=? AND item_key=?",
            (1, today, "actual-time-check"),
        ).fetchone()
    assert row["completed_time"] == "2026-07-05 08:00:00"
    with store._connect() as conn:
        reward_count = conn.execute(
            "SELECT COUNT(*) FROM server_reward_ledger WHERE user_id=? AND source_type='exercise_checkin'", (1,)
        ).fetchone()[0]
    assert reward_count == 0


def test_server_sample_data_initialization_is_idempotent_after_login(client_with_db):
    client, store = client_with_db
    client.post("/auth/register", json={"username": "sample_user", "password": "password123"})
    login = client.post("/auth/login", json={"username": "sample_user", "password": "password123"})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['token']}"}

    with store._connect() as conn:
        categories = conn.execute("SELECT COUNT(*) AS count FROM server_categories WHERE user_id=1").fetchone()["count"]
        objectives = conn.execute("SELECT COUNT(*) AS count FROM server_learning_objectives WHERE user_id=1").fetchone()["count"]
        krs = conn.execute("SELECT COUNT(*) AS count FROM server_learning_krs WHERE user_id=1").fetchone()["count"]
        tasks = conn.execute("SELECT COUNT(*) AS count FROM server_learning_tasks WHERE user_id=1").fetchone()["count"]
        exercise_versions = conn.execute("SELECT COUNT(*) AS count FROM server_exercise_plan_versions WHERE user_id=1").fetchone()["count"]
        exercise_items = conn.execute("SELECT COUNT(*) AS count FROM server_exercise_plan_items WHERE user_id=1").fetchone()["count"]
        exercise_schedules = conn.execute("SELECT COUNT(*) AS count FROM server_exercise_plan_schedule_items WHERE user_id=1").fetchone()["count"]
        active_plan = conn.execute(
            "SELECT value FROM server_system_config WHERE user_id=1 AND key='active_exercise_plan_version'"
        ).fetchone()["value"]
        markers = conn.execute("SELECT COUNT(*) AS count FROM server_sample_data_initializations WHERE user_id=1").fetchone()["count"]
    assert categories == 15
    assert objectives == 1
    assert krs == 4
    assert tasks == 32
    assert exercise_versions == 2
    assert exercise_items == 180
    assert exercise_schedules == 30
    assert active_plan == "v1"
    assert markers == 5

    second_login = client.post("/auth/login", json={"username": "sample_user", "password": "password123"})
    assert second_login.status_code == 200
    with store._connect() as conn:
        categories_after = conn.execute("SELECT COUNT(*) AS count FROM server_categories WHERE user_id=1").fetchone()["count"]
        objectives_after = conn.execute("SELECT COUNT(*) AS count FROM server_learning_objectives WHERE user_id=1").fetchone()["count"]
        exercise_items_after = conn.execute("SELECT COUNT(*) AS count FROM server_exercise_plan_items WHERE user_id=1").fetchone()["count"]
    assert categories_after == 15
    assert objectives_after == 1
    assert exercise_items_after == 180

    pulled = client.get("/api/sync/pull", headers=headers)
    assert pulled.status_code == 200
    tables = pulled.json()["tables"]
    assert len(tables["categories"]) == 15
    assert len(tables["learning_objectives"]) == 1
    assert len(tables["learning_krs"]) == 4
    assert len(tables["learning_tasks"]) == 32
    assert len(tables["exercise_plan_versions"]) == 2
    assert len(tables["exercise_plan_items"]) == 180
    assert len(tables["exercise_plan_schedule_items"]) == 30


def test_legacy_seed_marker_migrates_to_sample_data_initialization(client_with_db):
    _client, store = client_with_db
    with store._connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (id, username, password_hash, created_at) VALUES (1, 'legacy-marker-user', 'x', '2026-07-02 00:00:00')"
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO server_seed_initializations
              (id, user_id, module, seed_version, status, created_at, updated_at)
            VALUES ('legacy-marker', 1, 'learning', '20260702-server-authoritative-seed', 'applied', '2026-07-02 00:00:00', '2026-07-02 00:00:00')
            """,
        )
        conn.execute("DELETE FROM server_sample_data_initializations WHERE id='legacy-marker'")
        ensure_server_schema(conn)
        marker = conn.execute(
            """
            SELECT sample_data_version
            FROM server_sample_data_initializations
            WHERE id='legacy-marker' AND module='learning'
            """,
        ).fetchone()

    assert marker["sample_data_version"] == "20260702-server-authoritative-seed"


def test_server_default_timer_categories_do_not_resurrect_after_user_changes(client_with_db):
    client, store = client_with_db
    client.post("/auth/register", json={"username": "category_user", "password": "password123"})
    login = client.post("/auth/login", json={"username": "category_user", "password": "password123"})
    assert login.status_code == 200

    with store._connect() as conn:
        conn.execute("UPDATE server_categories SET name='输入-用户改名' WHERE user_id=1 AND name='输入'")
        conn.execute("DELETE FROM server_categories WHERE user_id=1 AND name='输出'")
        conn.commit()

    second_login = client.post("/auth/login", json={"username": "category_user", "password": "password123"})
    assert second_login.status_code == 200

    with store._connect() as conn:
        categories = conn.execute("SELECT name FROM server_categories WHERE user_id=1").fetchall()
    names = {row["name"] for row in categories}
    assert len(names) == 14
    assert "输入-用户改名" in names
    assert "输入" not in names
    assert "输出" not in names


def test_exercise_plan_definition_tables_are_sync_whitelisted():
    expected = {
        "exercise_plan_schedule_items",
        "exercise_plan_diet_rules",
        "exercise_plan_score_rules",
        "exercise_plan_category_rules",
        "exercise_plan_progress_items",
    }
    assert expected.issubset(set(SYNC_TABLES))
    for table in expected:
        assert server_module.store._TABLE_MAP[table] == f"server_{table}"


def test_habit_makeup_discount_server(client_with_db):
    client, test_store = client_with_db

    # 1. Register and Login
    client.post("/auth/register", json={"username": "test_user2", "password": "password123"})
    resp = client.post("/auth/login", json={"username": "test_user2", "password": "password123"})
    token = resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create Habit (medium difficulty)
    resp = client.post("/api/habits", json={"name": "冥想", "icon": "🧘", "difficulty": "medium"}, headers=headers)
    assert resp.status_code == 200
    habit_id = resp.json()["habit_id"]

    # 3. Checkin yesterday (makeup)
    from datetime import datetime, timedelta
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_lbl = (datetime.now() - timedelta(days=1)).strftime("%m-%d")

    resp = client.post(f"/api/habits/{habit_id}/checkin", json={"date": yesterday}, headers=headers)
    assert resp.status_code == 200

    # 4. Verify wallet balance (medium difficulty = 10.0 coins, discounted to 5.0 coins)
    resp = client.get("/api/rewards/balance", headers=headers)
    assert resp.json()["balance"] == 5.0

    # 5. Verify ledger entry description
    conn = test_store._connect()
    row = conn.execute("SELECT amount, description FROM server_reward_ledger WHERE user_id=? AND source_type='habit_checkin'", (1,)).fetchone()
    assert row is not None
    assert row["amount"] == 5.0
    assert "[补]" in row["description"]
    assert "冥想" in row["description"]
    conn.close()

    # 6. Cancel checkin
    resp = client.delete(f"/api/habits/{habit_id}/checkin?date={yesterday}", headers=headers)
    assert resp.status_code == 200

    # 7. Verify wallet balance after cancellation (should be 0.0)
    resp = client.get("/api/rewards/balance", headers=headers)
    assert resp.json()["balance"] == 0.0


def test_sync_endpoint(client_with_db):
    client, test_store = client_with_db

    # 1. Register and Login
    client.post("/auth/register", json={"username": "test_sync_user", "password": "password123"})
    resp = client.post("/auth/login", json={"username": "test_sync_user", "password": "password123"})
    token = resp.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Add category
    resp = client.post("/api/categories", json={
        "name": "同步学习",
        "group_name": "输入",
        "icon": "📚",
        "color": "blue"
    }, headers=headers)
    assert resp.status_code == 200

    # 3. Add habit
    resp = client.post("/api/habits", json={"name": "同步习惯", "icon": "🏃", "difficulty": "easy"}, headers=headers)
    assert resp.status_code == 200
    habit_id = resp.json()["habit_id"]

    # 4. Checkin habit
    resp = client.post(f"/api/habits/{habit_id}/checkin", json={"date": TEST_DATE}, headers=headers)
    assert resp.status_code == 200

    # 5. Call sync pull API
    resp = client.get("/api/sync/pull", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    tables = data["tables"]
    assert len(tables["categories"]) == 16
    assert any(row["name"] == "同步学习" for row in tables["categories"])
    assert tables["categories"][0]["name"] == "同步学习"
    assert len(tables["habits"]) == 1
    assert tables["habits"][0]["name"] == "同步习惯"
    assert len(tables["habit_checkins"]) == 1
    assert tables["habit_checkins"][0]["habit_id"] == habit_id


def test_admin_logging_config_updates_runtime_level(client_with_db, tmp_path):
    client, _ = client_with_db
    orig_store = server_module.logging_config_store
    orig_log_dir = server_module.LOG_DIR
    server_module.logging_config_store = LoggingConfigStore(str(tmp_path / "logging_config.json"))
    server_module.LOG_DIR = str(tmp_path / "log")
    try:
        client.post("/auth/register", json={"username": "log_user", "password": "password123"})
        login = client.post("/auth/login", json={"username": "log_user", "password": "password123"})
        headers = {"Authorization": f"Bearer {login.json()['token']}"}

        response = client.put("/admin/logging/config", json={
            "global_level": "WARNING",
            "module_levels": {"server.sync_hub": "DEBUG"},
        }, headers=headers)

        assert response.status_code == 200
        body = response.json()
        assert body["global_level"] == "WARNING"
        assert body["module_levels"]["server.sync_hub"] == "DEBUG"
        assert server_module.logging.getLogger().level == server_module.logging.WARNING
        assert server_module.logging.getLogger("server.sync_hub").level == server_module.logging.DEBUG
        assert client.get("/admin/logging/config", headers=headers).status_code == 200
    finally:
        server_module.logging_config_store = orig_store
        server_module.LOG_DIR = orig_log_dir


def test_logging_config_rejects_non_manager_without_side_effect(client_with_db, tmp_path, monkeypatch):
    client, _ = client_with_db
    monkeypatch.setattr(server_module, "_ensure_sample_data_for_user", lambda user_id: None)
    orig_store, orig_log_dir = server_module.logging_config_store, server_module.LOG_DIR
    server_module.logging_config_store = LoggingConfigStore(str(tmp_path / "logging_config.json"))
    server_module.LOG_DIR = str(tmp_path / "log")
    try:
        manager = _login_headers(client, "log_manager")
        ordinary = _login_headers(client, "log_ordinary")
        assert client.put("/admin/logging/config", headers=manager, json={"global_level": "ERROR"}).status_code == 200
        before = server_module.logging_config_store.path.read_text(encoding="utf-8")
        before_level = server_module.logging.getLogger().level

        assert client.get("/admin/logging/config", headers=ordinary).status_code == 403
        denied = client.put("/admin/logging/config", headers=ordinary, json={"global_level": "DEBUG"})
        assert denied.status_code == 403
        assert server_module.logging_config_store.path.read_text(encoding="utf-8") == before
        assert server_module.logging.getLogger().level == before_level
    finally:
        server_module.logging_config_store, server_module.LOG_DIR = orig_store, orig_log_dir


def test_lifespan_reapplies_logging_after_uvicorn_reset(tmp_path, monkeypatch):
    orig_store, orig_log_dir = server_module.logging_config_store, server_module.LOG_DIR
    server_module.logging_config_store = LoggingConfigStore(str(tmp_path / "logging_config.json"))
    server_module.logging_config_store.save({"global_level": "WARNING"})
    server_module.LOG_DIR = str(tmp_path / "log")
    monkeypatch.setattr(server_module, "_cleanup_stale_temp_upload_images", lambda **_: None)
    monkeypatch.setattr(server_module.time_logger_db, "reload_category_cache", lambda: None)
    try:
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            server_module.logging.getLogger(name).setLevel(server_module.logging.INFO)

        async def verify_startup():
            async with server_module.lifespan(server_module.app):
                for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
                    assert server_module.logging.getLogger(name).level == server_module.logging.WARNING

        server_module.asyncio.run(verify_startup())
    finally:
        server_module.logging_config_store, server_module.LOG_DIR = orig_store, orig_log_dir


def test_admin_server_config_requires_auth_and_ignores_user_secret_sections(client_with_db, tmp_path, monkeypatch):
    client, _ = client_with_db
    manager = ConfigManager(str(tmp_path / "config.json"))
    monkeypatch.setattr(server_module, "server_config", manager)
    s3_reloads = []
    monkeypatch.setattr(server_module.s3_backup, "reload_config", lambda: s3_reloads.append(True))

    unauthorized = client.get("/admin/server-config")
    assert unauthorized.status_code == 401

    headers = _login_headers(client, "server_config_user")
    response = client.put(
        "/admin/server-config",
        headers=headers,
        json={"raw_text": '{"ai_model": {"vision_model": "Qwen/Qwen3.5-35B-A3B", "backup_model": "glm-4.6v-flash"}, "s3_backup": {"endpoint": "https://deployment-s3"}}'},
    )

    assert response.status_code == 200
    assert manager.get_ai("vision_model") is None
    assert manager.get_ai("backup_model") is None
    assert s3_reloads == []
    saved = client.get("/admin/server-config", headers=headers).json()["raw_text"]
    assert "backup_base_url" not in saved
    assert "backup_api_key" not in saved
    assert "backup_model" not in saved


def test_admin_server_config_invalid_jsonc_reports_chinese_error(client_with_db, tmp_path, monkeypatch):
    client, _ = client_with_db
    manager = ConfigManager(str(tmp_path / "config.json"))
    original = manager.get_raw_text()
    monkeypatch.setattr(server_module, "server_config", manager)
    monkeypatch.setattr(server_module.s3_backup, "reload_config", lambda: None)

    headers = _login_headers(client, "server_config_invalid_user")
    response = client.put("/admin/server-config", headers=headers, json={"raw_text": '{"ai_model": '})

    assert response.status_code == 400
    assert "配置不是合法 JSONC" in response.json()["detail"]
    assert manager.get_raw_text() == original


def test_provider_bindings_config_returns_current_user_private_summary(client_with_db):
    client, _ = client_with_db
    headers = _login_headers(client, "service_config_user")

    assert client.put(
        "/admin/provider-bindings/ticktick",
        headers=headers,
        json={"access_token": "tick-secret", "host": "dida365.com"},
    ).status_code == 200
    assert client.put(
        "/admin/provider-bindings/ai-model",
        headers=headers,
        json={
            "text_base_url": "https://text.example/v1",
            "text_api_key": "text-secret",
            "text_model": "text-model",
            "vision_base_url": "https://vision.example/v1",
            "vision_api_key": "vision-secret",
            "vision_model": "vision-model",
            "text_backup_1_base_url": "https://text-backup.example/v1", "text_backup_1_api_key": "text-backup-secret", "text_backup_1_model": "text-backup-model",
            "vision_backup_2_base_url": "https://vision-backup.example/v1", "vision_backup_2_api_key": "vision-backup-secret", "vision_backup_2_model": "vision-backup-model",
        },
    ).status_code == 200

    response = client.get("/admin/provider-bindings/config", headers=headers)
    assert response.status_code == 200
    body = response.json()
    payload = json.dumps(body, ensure_ascii=False)

    assert body["ticktick"]["token_configured"] is True
    assert body["s3_backup"]["scope"] == "personal"
    assert body["ai_model"]["text_model"] == "text-model"
    assert body["ai_model"]["vision_model"] == "vision-model"
    assert body["ai_model"]["text_backup_1_model"] == "text-backup-model"
    assert body["ai_model"]["vision_backup_2_key_configured"] is True
    assert body["ai_model"]["text_key_configured"] is True
    assert "tick-secret" not in payload
    assert "text-secret" not in payload
    assert "vision-secret" not in payload
    assert "text-backup-secret" not in payload
    assert "vision-backup-secret" not in payload


def test_new_account_services_are_enabled_but_pending_private_configuration(client_with_db):
    client, _ = client_with_db
    headers = _login_headers(client, "service_defaults_user")

    response = client.get("/admin/integration-config/status", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["ticktick"]["enabled"] is True and body["ticktick"]["configured"] is False
    assert body["ticktick"]["status"] == "pending_configuration"
    assert body["s3_backup"]["enabled"] is True and body["s3_backup"]["configured"] is False
    assert body["s3_backup"]["scope"] == "personal"
    assert body["text_model"]["enabled"] is True and body["text_model"]["configured"] is False
    assert body["text_model"]["status"] == "pending_configuration"


def test_new_account_does_not_inherit_another_users_provider_configuration(client_with_db):
    client, _ = client_with_db
    first = _login_headers(client, "configured_service_owner")
    second = _login_headers(client, "unconfigured_service_user")
    assert client.put("/admin/provider-bindings/ticktick", headers=first, json={"access_token": "first-user-token"}).status_code == 200
    status = client.get("/admin/integration-config/status", headers=second).json()

    assert status["ticktick"]["configured"] is False
    assert status["text_model"]["configured"] is False
    assert status["text_model"]["model"] == ""
    assert "first-user-token" not in json.dumps(status, ensure_ascii=False)


def test_ordinary_user_cannot_access_deployment_s3_backup_controls(client_with_db, monkeypatch):
    client, _ = client_with_db
    manager = _login_headers(client, "s3_service_manager")
    ordinary = _login_headers(client, "s3_ordinary_user")
    reloads = []
    monkeypatch.setattr(server_module.s3_backup, "reload_config", lambda: reloads.append(server_module._service_manager_s3_config().endpoint))
    assert client.put("/admin/provider-bindings/s3", headers=manager, json={"endpoint": "https://manager-s3", "secret_key": "manager-secret"}).status_code == 200
    assert client.put("/admin/provider-bindings/s3", headers=ordinary, json={"endpoint": "https://ordinary-s3", "secret_key": "ordinary-secret"}).status_code == 200
    assert reloads == ["https://manager-s3"]
    assert server_module._service_manager_s3_config().endpoint == "https://manager-s3"
    assert client.get("/admin/s3-backup/config", headers=manager).status_code == 200

    for method, path, payload in (
        (client.get, "/admin/s3-backup/config", None),
        (client.get, "/admin/s3-backup/status", None),
        (client.put, "/admin/s3-backup/config", {"secret_key": "must-not-save"}),
        (client.post, "/admin/s3-backup/test", {"secret_key": "must-not-test"}),
    ):
        response = method(path, headers=ordinary, json=payload) if payload else method(path, headers=ordinary)
        assert response.status_code == 403
        assert "must-not" not in response.text

    public_status = client.get("/admin/integration-config/status", headers=ordinary).json()["s3_backup"]
    assert {"bucket", "sqlite_prefix", "reports_prefix", "last_success", "secret_configured"}.isdisjoint(public_status)


def test_service_manager_s3_save_reloads_disabled_and_enabled_values(client_with_db, monkeypatch):
    client, _ = client_with_db
    manager = _login_headers(client, "s3_reload_manager")
    loaded = []
    monkeypatch.setattr(server_module.s3_backup.store, "load", lambda: (_ for _ in ()).throw(AssertionError("deployment fallback")))
    monkeypatch.setattr(server_module.s3_backup, "reload_config", lambda: loaded.append(server_module._service_manager_s3_config()))

    disabled = client.put("/admin/provider-bindings/s3", headers=manager, json={"enabled": False, "endpoint": "https://saved-s3", "secret_key": "saved-secret"})
    enabled = client.put("/admin/provider-bindings/s3", headers=manager, json={"enabled": True, "secret_key": ""})
    public = client.get("/admin/s3-backup/config", headers=manager).json()

    assert disabled.status_code == 200 and enabled.status_code == 200
    assert [config.enabled for config in loaded] == [False, True]
    assert loaded[-1].secret_key == "saved-secret"
    assert public["endpoint"] == "https://saved-s3" and public["secret_configured"] is True


def test_provider_bindings_export_returns_current_user_private_secrets(client_with_db, monkeypatch):
    monkeypatch.setattr(server_module, "_ensure_sample_data_for_user", lambda user_id: None)
    client, _ = client_with_db
    headers = _login_headers(client, "service_export_user")
    other_headers = _login_headers(client, "service_export_other_user")

    assert client.put(
        "/admin/provider-bindings/ticktick",
        headers=headers,
        json={"access_token": "tick-export-secret", "host": "dida365.com"},
    ).status_code == 200
    assert client.put(
        "/admin/provider-bindings/ai-model",
        headers=headers,
        json={
            "text_base_url": "https://text.example/v1",
            "text_api_key": "text-export-secret",
            "text_model": "text-model",
            "vision_base_url": "https://vision.example/v1",
            "vision_api_key": "vision-export-secret",
            "vision_model": "vision-model",
            "backup_base_url": "https://backup.example/v1",
            "backup_api_key": "backup-export-secret",
            "backup_model": "backup-model",
        },
    ).status_code == 200
    assert client.put(
        "/admin/provider-bindings/ticktick",
        headers=other_headers,
        json={"access_token": "other-tick-secret", "host": "dida365.com"},
    ).status_code == 200

    response = client.get("/admin/provider-bindings/export", headers=headers)
    assert response.status_code == 200
    assert '\n  "schema":' in response.text
    assert '\n  "ticktick": {' in response.text
    body = response.json()
    payload = json.dumps(body, ensure_ascii=False)

    assert body["schema"] == server_module.USER_SERVICE_CONFIG_SCHEMA
    assert body["ticktick"]["access_token"] == "tick-export-secret"
    assert body["s3_backup"] == {}
    assert body["ai_model"]["text_api_key"] == "text-export-secret"
    assert body["ai_model"]["vision_api_key"] == "vision-export-secret"
    assert body["ai_model"]["backup_api_key"] == "backup-export-secret"
    assert "other-tick-secret" not in payload


def test_provider_bindings_import_writes_current_user_not_json_user(client_with_db, monkeypatch):
    monkeypatch.setattr(server_module, "_ensure_sample_data_for_user", lambda user_id: None)
    client, _ = client_with_db
    target_headers = _login_headers(client, "service_import_target")
    other_headers = _login_headers(client, "service_import_other")
    reloaded = []
    monkeypatch.setattr(server_module.s3_backup, "reload_config", lambda: reloaded.append(server_module._service_manager_s3_config().endpoint))

    assert client.put(
        "/admin/provider-bindings/ticktick",
        headers=other_headers,
        json={"access_token": "other-before-secret", "host": "dida365.com"},
    ).status_code == 200

    imported = {
        "schema": server_module.USER_SERVICE_CONFIG_SCHEMA,
        "exported_at": "2026-07-09 18:00:00",
        "environment": "testing",
        "user": {"id": 999, "username": "service_import_other"},
        "ticktick": {"enabled": True, "access_token": "target-import-tick", "host": "dida365.com", "sync_interval": "120"},
        "s3_backup": {
            "enabled": True,
            "endpoint": "https://s3.import",
            "bucket": "import-bucket",
            "region": "us-east-1",
            "access_key": "target-import-ak",
            "secret_key": "target-import-sk",
            "sqlite_prefix": "sqlite",
            "reports_prefix": "reports",
            "interval_hours": 6,
            "retention_count": 28,
        },
        "ai_model": {
            "text_base_url": "https://text.import/v1",
            "text_api_key": "target-import-text",
            "text_model": "text-import",
            "vision_base_url": "https://vision.import/v1",
            "vision_api_key": "target-import-vision",
            "vision_model": "vision-import",
            "backup_base_url": "https://backup.import/v1",
            "backup_api_key": "target-import-backup",
            "backup_model": "backup-import",
        },
    }

    response = client.post("/admin/provider-bindings/import", headers=target_headers, json=imported)
    assert response.status_code == 200
    summary = response.json()
    assert summary["s3_backup"]["configured"] is True
    assert summary["s3_backup"]["endpoint"] == "https://s3.import"
    assert summary["s3_backup"]["bucket"] == "import-bucket"
    assert summary["s3_backup"]["secret_configured"] is True
    assert summary["user"] == {"username": "service_import_target"}
    assert "target-import-sk" not in json.dumps(summary, ensure_ascii=False)

    target_export = client.get("/admin/provider-bindings/export", headers=target_headers).json()
    other_export = client.get("/admin/provider-bindings/export", headers=other_headers).json()

    assert target_export["ticktick"]["access_token"] == "target-import-tick"
    assert target_export["s3_backup"]["endpoint"] == "https://s3.import"
    assert target_export["s3_backup"]["secret_key"] == "target-import-sk"
    assert target_export["ai_model"]["text_api_key"] == "target-import-text"
    assert reloaded == ["https://s3.import"]
    assert other_export["ticktick"]["access_token"] == "other-before-secret"
    assert "target-import-tick" not in json.dumps(other_export, ensure_ascii=False)


def test_provider_import_requires_empty_s3_snapshot_and_clears_existing_s3(client_with_db, monkeypatch):
    client, _ = client_with_db
    manager = _login_headers(client, "service_import_without_s3")
    reloads = []
    monkeypatch.setattr(server_module.s3_backup, "reload_config", lambda: reloads.append(True))
    assert client.put(
        "/admin/provider-bindings/s3", headers=manager,
        json={"endpoint": "https://keep-s3", "secret_key": "keep-secret"},
    ).status_code == 200
    reloads.clear()

    response = client.post("/admin/provider-bindings/import", headers=manager, json={
        "schema": server_module.USER_SERVICE_CONFIG_SCHEMA,
        "ticktick": {},
        "s3_backup": {},
        "ai_model": {},
    })
    exported = client.get("/admin/provider-bindings/export", headers=manager).json()

    assert response.status_code == 200
    assert exported["s3_backup"].get("endpoint", "") == ""
    assert exported["s3_backup"].get("secret_key", "") == ""
    assert reloads == []


def test_provider_import_requires_all_v1_sections_without_partial_write(client_with_db, monkeypatch):
    monkeypatch.setattr(server_module, "_ensure_sample_data_for_user", lambda user_id: None)
    client, _ = client_with_db
    headers = _login_headers(client, "service_import_atomic")
    assert client.put("/admin/provider-bindings/ticktick", headers=headers, json={"access_token": "before-tick"}).status_code == 200

    response = client.post("/admin/provider-bindings/import", headers=headers, json={
        "schema": server_module.USER_SERVICE_CONFIG_SCHEMA,
        "ticktick": {"access_token": "after-tick"},
        "ai_model": {},
    })
    exported = client.get("/admin/provider-bindings/export", headers=headers).json()

    assert response.status_code == 400
    assert "s3_backup" in response.json()["detail"]
    assert exported["ticktick"]["access_token"] == "before-tick"


def test_provider_bindings_import_rejects_invalid_schema(client_with_db, monkeypatch):
    monkeypatch.setattr(server_module, "_ensure_sample_data_for_user", lambda user_id: None)
    client, _ = client_with_db
    headers = _login_headers(client, "service_import_invalid")
    response = client.post(
        "/admin/provider-bindings/import",
        headers=headers,
        json={"schema": "wrong", "ticktick": {}, "s3_backup": {}, "ai_model": {}},
    )
    assert response.status_code == 400
    assert "schema" in response.json()["detail"]


def test_provider_config_reports_current_authenticated_username(client_with_db, monkeypatch):
    monkeypatch.setattr(server_module, "_ensure_sample_data_for_user", lambda user_id: None)
    client, _ = client_with_db
    headers = _login_headers(client, "config_identity_user")

    response = client.get("/admin/provider-bindings/config", headers=headers)

    assert response.status_code == 200
    assert response.json()["user"] == {"username": "config_identity_user"}


def test_sync_cors_preflight_uses_config_json_allowlist(monkeypatch, tmp_path):
    manager = ConfigManager(str(tmp_path / "config.json"), legacy_path=str(tmp_path / "missing.jsonc"))
    monkeypatch.setattr(server_module, "server_config", manager)
    client = TestClient(app)

    local = client.options(
        "/api/sync/push",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    remote = client.options(
        "/api/sync/push",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert local.status_code == 200
    assert local.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert remote.status_code == 400
    assert "access-control-allow-origin" not in remote.headers


def test_capacitor_cors_preflight_covers_auth_sync_and_sse(monkeypatch, tmp_path):
    manager = ConfigManager(str(tmp_path / "config.json"), legacy_path=str(tmp_path / "missing.jsonc"))
    monkeypatch.setattr(server_module, "server_config", manager)
    client = TestClient(app)
    for origin in ("https://localhost", "capacitor://localhost"):
        for path, method in (("/auth/login", "POST"), ("/api/sync/push", "POST"), ("/api/sync/pull", "GET"), ("/api/sync/events", "GET")):
            response = client.options(path, headers={"Origin": origin, "Access-Control-Request-Method": method, "Access-Control-Request-Headers": "authorization,content-type"})
            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == origin
            assert response.headers["access-control-allow-credentials"] == "true"
            assert response.headers["vary"] == "Origin"
            assert "authorization" in response.headers["access-control-allow-headers"]


def test_server_config_save_reloads_cors_without_restart(client_with_db, monkeypatch, tmp_path):
    client, _store = client_with_db
    manager = ConfigManager(str(tmp_path / "config.json"), legacy_path=str(tmp_path / "missing.jsonc"))
    monkeypatch.setattr(server_module, "server_config", manager)
    monkeypatch.setattr(server_module.s3_backup, "reload_config", lambda: None)
    headers = _login_headers(client, "cors_reload_user")

    response = client.put(
        "/admin/server-config",
        headers=headers,
        json={"raw_text": '{"cors": {"allowed_origins": ["http://localhost:6188"]}}'},
    )
    assert response.status_code == 200

    allowed = client.options(
        "/api/sync/pull",
        headers={
            "Origin": "http://localhost:6188",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    old_default = client.options(
        "/api/sync/pull",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:6188"
    assert old_default.status_code == 400


def test_store_image_hash_lookup_is_user_and_status_scoped(client_with_db):
    _, store = client_with_db
    store.create_user("hash_user_1", "password123")
    store.create_user("hash_user_2", "password123")
    image_hash = "abc123"
    store.create_job("done-user-1", "one.jpg", user_id=1, image_hash=image_hash)
    store.mark_done("done-user-1", "2026-06-25", {"date": "2026-06-25", "sleep_score": 81}, "report")
    store.create_job("error-user-1", "two.jpg", user_id=1, image_hash="error-hash")
    store.mark_error("error-user-1", "bad image")
    store.create_job("done-user-2", "three.jpg", user_id=2, image_hash=image_hash)
    store.mark_done("done-user-2", "2026-06-25", {"date": "2026-06-25", "sleep_score": 90}, "report")

    assert store.get_done_job_by_image_hash(image_hash, 1)["request_id"] == "done-user-1"
    assert store.get_done_job_by_image_hash(image_hash, 2)["request_id"] == "done-user-2"
    assert store.get_done_job_by_image_hash("error-hash", 1) is None


def test_upload_reuses_completed_job_by_image_hash(client_with_db, monkeypatch):
    client, store = client_with_db
    headers = _login_headers(client, "hash_user")
    content = b"same-image-bytes"
    image_hash = server_module._hash_bytes(content)
    store.create_job("existing-hash-job", "old.jpg", user_id=1, image_hash=image_hash)
    store.mark_done("existing-hash-job", "2026-06-25", {"date": "2026-06-25", "sleep_score": 81}, "report")

    calls = {"count": 0}

    def fake_run_analysis(*args, **kwargs):
        calls["count"] += 1

    monkeypatch.setattr(server_module, "_run_analysis", fake_run_analysis)

    resp = client.post(
        "/upload",
        headers=headers,
        files={"file": ("sleep.jpg", io.BytesIO(content), "image/jpeg")},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["request_id"] == "existing-hash-job"
    assert body["reused"] is True
    assert body["cache_reason"] == "image_hash"
    assert calls["count"] == 0


def test_upload_only_mode_binds_date_without_starting_analysis(client_with_db, monkeypatch, tmp_path):
    client, store = client_with_db
    headers = _login_headers(client, "upload_only_user")
    monkeypatch.setattr(server_module, "ATTACHMENTS_DIR", str(tmp_path))
    analysis_calls = {"count": 0}
    validation_calls = {"count": 0}

    def fake_run_analysis(*args, **kwargs):
        analysis_calls["count"] += 1

    def fake_run_upload_validation(*args, **kwargs):
        validation_calls["count"] += 1

    monkeypatch.setattr(server_module, "_run_analysis", fake_run_analysis)
    monkeypatch.setattr(server_module, "_run_upload_validation", fake_run_upload_validation)

    resp = client.post(
        "/upload?analyze=false&date=2026-05-25",
        headers=headers,
        files={"file": ("sleep.jpg", io.BytesIO(b"upload-only"), "image/jpeg")},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["uploaded"] is True
    assert body["analyze"] is False
    assert body["date"] == "2026-05-25"
    assert analysis_calls["count"] == 0
    assert validation_calls["count"] == 1
    job = store.get_job(body["request_id"], user_id=1)
    assert job["date"] == "2026-05-25"
    assert job["status"] == "queued"
    assert not (tmp_path / "sleep_2026-05-25.jpg").exists()
    assert job["image_path"].endswith("_sleep.jpg")


def test_upload_validation_marks_uploaded_without_report(monkeypatch, tmp_db_path, tmp_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    store.create_user("upload_validation_user", "password123")
    _seed_ai_config(store.db_path, 1)
    orig_store = server_module.store
    orig_analyzer = server_module.SleepAnalyzer
    orig_attachments_dir = server_module.ATTACHMENTS_DIR
    server_module.store = store
    server_module.ATTACHMENTS_DIR = str(tmp_path)
    temp_image = tmp_path / "request_sleep.jpg"
    temp_image.write_bytes(b"upload-validation")

    class FakeAnalyzer:
        report_generation_calls = 0

        def __init__(self, *args, **kwargs):
            assert kwargs.get("date_str") == "2026-05-25"

        def _extract_sleep_data(self):
            return {
                "sleep_date": "2026-05-25",
                "sleep_score": 80,
                "total_sleep_min": 360,
                "deep_sleep_min": 90,
                "light_sleep_min": 210,
                "rem_sleep_min": 60,
                "deep_sleep_ratio": 25,
                "sleep_start": "01:00",
                "sleep_end": "07:00",
                "official_advice": "解读：睡眠时长不足，深睡比例良好。\n建议：保持规律作息，睡前减少刺激。",
            }

        @staticmethod
        def validate_data(data):
            return orig_analyzer.validate_data(data)

    try:
        monkeypatch.setattr(server_module, "SleepAnalyzer", FakeAnalyzer)
        monkeypatch.setattr(server_module, "_cleanup_queue", lambda *args, **kwargs: None)
        store.create_job("upload-validation-job", str(temp_image), user_id=1, date="2026-05-25", image_hash="hash-upload-validation")

        server_module._run_upload_validation("upload-validation-job", str(temp_image), user_id=1)

        job = store.get_job("upload-validation-job", user_id=1)
        assert job["status"] == "uploaded"
        assert job["date"] == "2026-05-25"
        assert job["analysis_report"] == ""
        assert job["sleep_data"]["date"] == "2026-05-25"
        assert (tmp_path / "sleep_2026-05-25.jpg").exists()
        assert not temp_image.exists()
        assert FakeAnalyzer.report_generation_calls == 0
    finally:
        server_module.store = orig_store
        server_module.SleepAnalyzer = orig_analyzer
        server_module.ATTACHMENTS_DIR = orig_attachments_dir


def test_upload_validation_failure_cleans_temp_image(monkeypatch, tmp_db_path, tmp_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    store.create_user("upload_validation_fail_user", "password123")
    _seed_ai_config(store.db_path, 1)
    orig_store = server_module.store
    orig_analyzer = server_module.SleepAnalyzer
    orig_attachments_dir = server_module.ATTACHMENTS_DIR
    server_module.store = store
    server_module.ATTACHMENTS_DIR = str(tmp_path)
    temp_image = tmp_path / "failed-upload_sleep.jpg"
    temp_image.write_bytes(b"bad-upload")

    class FakeAnalyzer:
        def __init__(self, *args, **kwargs):
            pass

        def _extract_sleep_data(self):
            return {"sleep_date": "2026-05-25"}

        @staticmethod
        def validate_data(data):
            return False, "缺失睡眠评分"

    try:
        monkeypatch.setattr(server_module, "SleepAnalyzer", FakeAnalyzer)
        monkeypatch.setattr(server_module, "_cleanup_queue", lambda *args, **kwargs: None)
        store.create_job("failed-upload", str(temp_image), user_id=1, date="2026-05-25", image_hash="hash-upload-failed")

        server_module._run_upload_validation("failed-upload", str(temp_image), user_id=1)

        job = store.get_job("failed-upload", user_id=1)
        assert job["status"] == "error"
        assert "缺失睡眠评分" in job["error"]
        assert not temp_image.exists()
        assert not (tmp_path / "sleep_2026-05-25.jpg").exists()
    finally:
        server_module.store = orig_store
        server_module.SleepAnalyzer = orig_analyzer
        server_module.ATTACHMENTS_DIR = orig_attachments_dir


def test_upload_default_still_starts_analysis(client_with_db, monkeypatch):
    client, _ = client_with_db
    headers = _login_headers(client, "upload_default_user")
    calls = {"count": 0}

    def fake_run_analysis(*args, **kwargs):
        calls["count"] += 1

    monkeypatch.setattr(server_module, "_run_analysis", fake_run_analysis)

    resp = client.post(
        "/upload",
        headers=headers,
        files={"file": ("sleep.jpg", io.BytesIO(b"default-upload"), "image/jpeg")},
    )

    assert resp.status_code == 200
    assert resp.json()["analyze"] is True
    assert calls["count"] == 1


def test_run_analysis_reuses_existing_done_job_after_sleep_date(monkeypatch, tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    store.create_user("date_user", "password123")
    _seed_ai_config(store.db_path, 1)
    orig_store = server_module.store
    orig_analyzer = server_module.SleepAnalyzer
    server_module.store = store

    class FakeResult:
        status = "done"
        date = "2026-06-25"
        sleep_data = {"date": "2026-06-25", "sleep_score": 77}
        analysis_report = "new report should not be used"
        report_path = None
        error = None

    class FakeAnalyzer:
        calls = 0
        report_generation_calls = 0

        def __init__(self, *args, **kwargs):
            self.pre_report_callback = kwargs.get("pre_report_callback")

        def analyze(self):
            FakeAnalyzer.calls += 1
            cached = self.pre_report_callback("2026-06-25", {"date": "2026-06-25", "sleep_score": 77})
            if cached:
                return type("CachedResult", (), {
                    "status": "done",
                    "date": cached["date"],
                    "sleep_data": cached["sleep_data"],
                    "analysis_report": cached["analysis_report"],
                    "report_path": "",
                    "error": None,
                })()
            FakeAnalyzer.report_generation_calls += 1
            return FakeResult()

        @staticmethod
        def validate_data(data):
            return True, ""

    try:
        monkeypatch.setattr(server_module, "SleepAnalyzer", FakeAnalyzer)
        store.create_job("existing-date-job", "old.jpg", user_id=1, date="2026-06-25")
        store.mark_done("existing-date-job", "2026-06-25", {"date": "2026-06-25", "sleep_score": 81}, "old report")
        store.create_job("current-upload-job", "new.jpg", user_id=1, image_hash="different-hash")

        server_module._run_analysis("current-upload-job", "new.jpg", user_id=1, full=False, force_refresh=False)

        assert FakeAnalyzer.calls == 1
        assert FakeAnalyzer.report_generation_calls == 0
        current = store.get_job("current-upload-job", user_id=1)
        assert current["status"] == "reused"
        assert current["sleep_data"]["sleep_score"] == 81
        assert current["analysis_report"] == "old report"
        existing = store.get_job("existing-date-job", user_id=1)
        assert existing["image_hash"] == "different-hash"
        done_rows = store.list_done_since("", user_id=1)
        assert [row["request_id"] for row in done_rows] == ["existing-date-job"]
    finally:
        server_module.store = orig_store
        server_module.SleepAnalyzer = orig_analyzer


def test_run_analysis_archives_by_recognized_sleep_date(monkeypatch, tmp_db_path, tmp_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    store.create_user("archive_date_user", "password123")
    _seed_ai_config(store.db_path, 1)
    orig_store = server_module.store
    orig_analyzer = server_module.SleepAnalyzer
    orig_attachments_dir = server_module.ATTACHMENTS_DIR
    server_module.store = store
    server_module.ATTACHMENTS_DIR = str(tmp_path)
    temp_image = tmp_path / "request_upload.jpg"
    temp_image.write_bytes(b"uploaded")

    class FakeResult:
        status = "done"
        date = "2026-05-12"
        sleep_data = {"date": "2026-05-12", "sleep_score": 71}
        analysis_report = ""
        report_path = None
        error = None

    class FakeAnalyzer:
        def __init__(self, *args, **kwargs):
            pass

        def analyze(self):
            return FakeResult()

    try:
        monkeypatch.setattr(server_module, "SleepAnalyzer", FakeAnalyzer)
        monkeypatch.setattr(server_module, "_cleanup_queue", lambda *args, **kwargs: None)
        store.create_job("archive-date-job", str(temp_image), user_id=1, image_hash="hash-a")

        server_module._run_analysis("archive-date-job", str(temp_image), user_id=1, full=False, force_refresh=False)

        final_path = tmp_path / "sleep_2026-05-12.jpg"
        assert final_path.exists()
        assert not (tmp_path / "sleep_2026-06-29.jpg").exists()
        job = store.get_job("archive-date-job", user_id=1)
        assert job["date"] == "2026-05-12"
        assert job["image_path"] == str(final_path)
    finally:
        server_module.store = orig_store
        server_module.SleepAnalyzer = orig_analyzer
        server_module.ATTACHMENTS_DIR = orig_attachments_dir


def test_run_analysis_marks_insufficient_tracked_time_done(monkeypatch, tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    store.create_user("insufficient_tracking_user", "password123")
    _seed_ai_config(store.db_path, 1)
    original_store, original_analyzer = server_module.store, server_module.SleepAnalyzer
    server_module.store = store

    class FakeAnalyzer:
        def __init__(self, *args, **kwargs):
            pass

        def analyze(self):
            return type("Result", (), {
                "status": "done", "date": "2026-06-30", "analysis_report": "",
                "report_path": "", "error": "", "sleep_data": {
                    "date": "2026-06-30", "report_status": 1,
                    "full_report_state": "insufficient_time_records", "tracked_duration_seconds": 71999,
                },
            })()

    try:
        monkeypatch.setattr(server_module, "SleepAnalyzer", FakeAnalyzer)
        store.create_job("insufficient-tracking-job", "missing.jpg", user_id=1, date="2026-06-30")
        server_module._run_analysis("insufficient-tracking-job", "missing.jpg", user_id=1, full=True)
        job = store.get_job("insufficient-tracking-job", user_id=1)
        assert job["status"] == "done"
        assert job["sleep_data"]["full_report_state"] == "insufficient_time_records"
        assert job["sleep_data"]["tracked_duration_seconds"] == 71999
    finally:
        server_module.store, server_module.SleepAnalyzer = original_store, original_analyzer


def test_run_analysis_scores_after_report_body_exists(monkeypatch, tmp_db_path):
    store = ServerSleepStore(db_path=tmp_db_path); store.create_user("auto_score_user", "password123")
    _seed_ai_config(store.db_path, 1)
    original_store, original_analyzer = server_module.store, server_module.SleepAnalyzer
    server_module.store = store
    metrics = {"date": "2026-09-08", "sleep_start": "23:00", "sleep_end": "07:00", "sleep_score": 90,
               "deep_sleep_min": 95, "sleep_cycles": 5.5, "awake_min": 10, "awake_count": 1,
               "fall_asleep_min": 20, "wake_up_min": 10}

    class FakeAnalyzer:
        def __init__(self, *args, **kwargs): pass
        def analyze(self):
            return type("Result", (), {"status": "done", "date": "2026-09-08", "analysis_report": "# 快速报告",
                                       "report_path": "", "error": "", "sleep_data": metrics.copy()})()

    try:
        monkeypatch.setattr(server_module, "SleepAnalyzer", FakeAnalyzer)
        store.create_job("auto-score-job", "missing.jpg", user_id=1, date="2026-09-08")
        server_module._run_analysis("auto-score-job", "missing.jpg", user_id=1, full=False)
        job = store.get_job("auto-score-job", user_id=1)
        assert job["sleep_data"]["score_settlement"]["status"] == "scored"
        assert job["sleep_data"]["score_settlement"]["score_total"] == 95
    finally:
        server_module.store, server_module.SleepAnalyzer = original_store, original_analyzer


def test_run_analysis_does_not_overwrite_existing_same_date_backup(monkeypatch, tmp_db_path, tmp_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    store.create_user("archive_idempotent_user", "password123")
    _seed_ai_config(store.db_path, 1)
    orig_store = server_module.store
    orig_analyzer = server_module.SleepAnalyzer
    orig_attachments_dir = server_module.ATTACHMENTS_DIR
    server_module.store = store
    server_module.ATTACHMENTS_DIR = str(tmp_path)
    final_path = tmp_path / "sleep_2026-05-12.jpg"
    final_path.write_bytes(b"original-backup")
    temp_image = tmp_path / "request_upload.jpg"
    temp_image.write_bytes(b"new-upload")

    class FakeResult:
        status = "done"
        date = "2026-05-12"
        sleep_data = {"date": "2026-05-12", "sleep_score": 72}
        analysis_report = ""
        report_path = None
        error = None

    class FakeAnalyzer:
        def __init__(self, *args, **kwargs):
            pass

        def analyze(self):
            return FakeResult()

    try:
        monkeypatch.setattr(server_module, "SleepAnalyzer", FakeAnalyzer)
        monkeypatch.setattr(server_module, "_cleanup_queue", lambda *args, **kwargs: None)
        store.create_job("archive-idempotent-job", str(temp_image), user_id=1, image_hash="hash-b")

        server_module._run_analysis("archive-idempotent-job", str(temp_image), user_id=1, full=False, force_refresh=True)

        assert final_path.read_bytes() == b"original-backup"
        assert not temp_image.exists()
        job = store.get_job("archive-idempotent-job", user_id=1)
        assert job["image_path"] == str(final_path)
    finally:
        server_module.store = orig_store
        server_module.SleepAnalyzer = orig_analyzer
        server_module.ATTACHMENTS_DIR = orig_attachments_dir


def test_run_analysis_reuse_does_not_replace_same_date_backup(monkeypatch, tmp_db_path, tmp_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    store.create_user("archive_reuse_user", "password123")
    _seed_ai_config(store.db_path, 1)
    orig_store = server_module.store
    orig_analyzer = server_module.SleepAnalyzer
    orig_attachments_dir = server_module.ATTACHMENTS_DIR
    server_module.store = store
    server_module.ATTACHMENTS_DIR = str(tmp_path)
    final_path = tmp_path / "sleep_2026-05-12.jpg"
    final_path.write_bytes(b"existing-backup")
    temp_image = tmp_path / "request_upload.jpg"
    temp_image.write_bytes(b"different-upload")

    class FakeAnalyzer:
        def __init__(self, *args, **kwargs):
            self.pre_report_callback = kwargs.get("pre_report_callback")

        def analyze(self):
            cached = self.pre_report_callback("2026-05-12", {"date": "2026-05-12", "sleep_score": 73})
            return type("CachedResult", (), {
                "status": "done",
                "date": cached["date"],
                "sleep_data": cached["sleep_data"],
                "analysis_report": cached["analysis_report"],
                "report_path": "",
                "error": None,
            })()

    try:
        monkeypatch.setattr(server_module, "SleepAnalyzer", FakeAnalyzer)
        monkeypatch.setattr(server_module, "_cleanup_queue", lambda *args, **kwargs: None)
        store.create_job("existing-date-job", str(final_path), user_id=1, date="2026-05-12")
        store.mark_done("existing-date-job", "2026-05-12", {"date": "2026-05-12", "sleep_score": 81}, "old report")
        store.create_job("current-upload-job", str(temp_image), user_id=1, image_hash="different-hash")

        server_module._run_analysis("current-upload-job", str(temp_image), user_id=1, full=False, force_refresh=False)

        assert final_path.read_bytes() == b"existing-backup"
        assert not temp_image.exists()
        current = store.get_job("current-upload-job", user_id=1)
        assert current["status"] == "reused"
        assert current["image_path"] == str(final_path)
        assert current["sleep_data"]["sleep_score"] == 81
    finally:
        server_module.store = orig_store
        server_module.SleepAnalyzer = orig_analyzer
        server_module.ATTACHMENTS_DIR = orig_attachments_dir


def test_run_analysis_date_mismatch_stops_without_backup(monkeypatch, tmp_db_path, tmp_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    store.create_user("date_mismatch_user", "password123")
    _seed_ai_config(store.db_path, 1)
    orig_store = server_module.store
    orig_analyzer = server_module.SleepAnalyzer
    orig_attachments_dir = server_module.ATTACHMENTS_DIR
    server_module.store = store
    server_module.ATTACHMENTS_DIR = str(tmp_path)
    temp_image = tmp_path / "request_upload.jpg"
    temp_image.write_bytes(b"wrong-date-upload")

    class FakeResult:
        status = "error"
        date = ""
        sleep_data = {"sleep_date": "2026-05-26"}
        analysis_report = ""
        report_path = None
        error = "日期不匹配！截图日期是 2026-05-26，而当前处理日期是 2026-06-29。请确认是否选错了图。"

    class FakeAnalyzer:
        report_generation_calls = 0

        def __init__(self, *args, **kwargs):
            assert kwargs.get("date_str") == "2026-06-29"

        def analyze(self):
            return FakeResult()

    try:
        monkeypatch.setattr(server_module, "SleepAnalyzer", FakeAnalyzer)
        monkeypatch.setattr(server_module, "_cleanup_queue", lambda *args, **kwargs: None)
        store.create_job("date-mismatch-job", str(temp_image), user_id=1, date="2026-06-29", image_hash="hash-mismatch")

        server_module._run_analysis("date-mismatch-job", str(temp_image), user_id=1, full=False, force_refresh=False)

        job = store.get_job("date-mismatch-job", user_id=1)
        assert job["status"] == "error"
        assert "2026-05-26" in job["error"]
        assert "2026-06-29" in job["error"]
        assert not (tmp_path / "sleep_2026-05-26.jpg").exists()
        assert not (tmp_path / "sleep_2026-06-29.jpg").exists()
        assert not temp_image.exists()
        assert FakeAnalyzer.report_generation_calls == 0
    finally:
        server_module.store = orig_store
        server_module.SleepAnalyzer = orig_analyzer
        server_module.ATTACHMENTS_DIR = orig_attachments_dir


def test_run_analysis_exception_cleans_temp_upload(monkeypatch, tmp_db_path, tmp_path):
    store = ServerSleepStore(db_path=tmp_db_path)
    store.create_user("analysis_exception_user", "password123")
    _seed_ai_config(store.db_path, 1)
    orig_store = server_module.store
    orig_analyzer = server_module.SleepAnalyzer
    orig_attachments_dir = server_module.ATTACHMENTS_DIR
    server_module.store = store
    server_module.ATTACHMENTS_DIR = str(tmp_path)

    class FakeAnalyzer:
        def __init__(self, *args, **kwargs):
            pass

        def analyze(self):
            raise RuntimeError("boom")

    try:
        monkeypatch.setattr(server_module, "SleepAnalyzer", FakeAnalyzer)
        monkeypatch.setattr(server_module, "_cleanup_queue", lambda *args, **kwargs: None)
        request_id = "exception"
        temp_image = tmp_path / f"{request_id}_upload.jpg"
        temp_image.write_bytes(b"analysis-exception")
        store.create_job(request_id, str(temp_image), user_id=1, date="2026-06-29", image_hash="hash-exception")

        server_module._run_analysis(request_id, str(temp_image), user_id=1, full=False, force_refresh=False)

        job = store.get_job(request_id, user_id=1)
        assert job["status"] == "error"
        assert "boom" in job["error"]
        assert not temp_image.exists()
        assert not (tmp_path / "sleep_2026-06-29.jpg").exists()
    finally:
        server_module.store = orig_store
        server_module.SleepAnalyzer = orig_analyzer
        server_module.ATTACHMENTS_DIR = orig_attachments_dir


def test_service_report_is_readable_by_date_and_sync(client_with_db):
    client, store = client_with_db
    headers = _login_headers(client, "service_report_user")
    date = "2026-07-01"
    report = "# 服务端报告\n\n统一同步可见。"
    store.create_job("service-report-job", "sleep_2026-07-01.jpg", user_id=1, date=date)
    store.mark_done(
        "service-report-job",
        date,
        {"date": date, "sleep_score": 88, "report_status": 2},
        report,
    )

    by_date = client.get(f"/status_by_date/{date}", headers=headers)
    assert by_date.status_code == 200
    by_date_body = by_date.json()
    assert by_date_body["status"] == "done"
    assert by_date_body["result"]["analysis_report"] == report
    assert "analysis_html" in by_date_body["result"]

    sync_resp = client.get("/sync_data", headers=headers)
    assert sync_resp.status_code == 200
    synced = [item for item in sync_resp.json()["data"] if item["date"] == date]
    assert len(synced) == 1
    assert synced[0]["analysis_report"] == report


def test_upload_same_hash_date_mismatch_returns_error_without_analysis(client_with_db, monkeypatch):
    client, store = client_with_db
    headers = _login_headers(client, "hash_date_mismatch_user")
    content = b"same-image-wrong-date"
    image_hash = server_module._hash_bytes(content)
    store.create_job("existing-hash-date-job", "old.jpg", user_id=1, image_hash=image_hash)
    store.mark_done("existing-hash-date-job", "2026-05-26", {"date": "2026-05-26", "sleep_score": 81}, "report")
    calls = {"count": 0}

    def fake_run_analysis(*args, **kwargs):
        calls["count"] += 1

    monkeypatch.setattr(server_module, "_run_analysis", fake_run_analysis)

    resp = client.post(
        "/upload?date=2026-06-29",
        headers=headers,
        files={"file": ("sleep.jpg", io.BytesIO(content), "image/jpeg")},
    )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["error_code"] == "date_mismatch"
    assert detail["actual_date"] == "2026-05-26"
    assert detail["expected_date"] == "2026-06-29"
    assert calls["count"] == 0


def test_full_report_reuse_rejects_stale_status_without_generated_state():
    stale = {"analysis_report": "# 普通睡眠报告", "sleep_data": {"report_status": 2}}
    full = {"analysis_report": "# 完整报告", "sleep_data": {"report_status": 2, "full_report_state": "generated"}}
    assert not server_module._can_reuse_sleep_report(stale, full=True, force=False)
    assert server_module._can_reuse_sleep_report(full, full=True, force=False)


def test_generate_report_reuses_existing_report_and_force_bypasses(client_with_db, monkeypatch, tmp_path):
    client, store = client_with_db
    headers = _login_headers(client, "report_user")
    date = "2026-06-25"
    store.create_job("existing-report-job", "old.jpg", user_id=1, date=date)
    store.mark_done("existing-report-job", date, {"date": date, "sleep_score": 81, "report_status": 2, "full_report_state": "generated"}, "# existing report")

    calls = {"count": 0}

    def fake_run_analysis(*args, **kwargs):
        calls["count"] += 1

    async def noop_coro():
        return None

    def fake_to_thread(func, *args, **kwargs):
        func(*args, **kwargs)
        return noop_coro()

    class DoneTask:
        def cancel(self):
            return None

    monkeypatch.setattr(server_module, "_run_analysis", fake_run_analysis)
    monkeypatch.setattr(server_module.asyncio, "to_thread", fake_to_thread)
    def fake_create_task(coro):
        coro.close()
        return DoneTask()

    monkeypatch.setattr(server_module.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(server_module, "ATTACHMENTS_DIR", str(tmp_path))
    (tmp_path / f"sleep_{date}.jpg").write_bytes(b"backup")

    resp = client.post("/generate_report", headers=headers, json={"date": date, "full": True, "force": False})
    assert resp.status_code == 200
    assert resp.json()["request_id"] == "existing-report-job"
    assert resp.json()["reused"] is True
    assert calls["count"] == 0

    resp = client.post("/generate_report", headers=headers, json={"date": date, "full": True, "force": True})
    assert resp.status_code == 200
    new_request_id = resp.json()["request_id"]
    assert new_request_id != "existing-report-job"
    assert calls["count"] == 1
    existing = store.get_job("existing-report-job", user_id=1)
    assert existing["status"] == "done"
    assert existing["analysis_report"] == "# existing report"
    forced = store.get_job(new_request_id, user_id=1)
    assert forced["status"] == "queued"


def test_generate_full_report_does_not_reuse_quick_report(client_with_db, monkeypatch, tmp_path):
    client, store = client_with_db
    headers = _login_headers(client, "quick_report_upgrade_user")
    date = "2026-06-25"
    image_path = tmp_path / "sleep.jpg"
    image_path.write_bytes(b"image")
    store.create_job("quick-report-job", str(image_path), user_id=1, date=date)
    store.mark_done("quick-report-job", date, {"date": date, "sleep_score": 81, "report_status": 1}, "")
    calls = {"count": 0}

    def fake_run_analysis(*_args, **_kwargs):
        calls["count"] += 1

    async def noop_coro():
        return None

    class DoneTask:
        def cancel(self):
            return None

    def fake_to_thread(func, *args, **kwargs):
        func(*args, **kwargs)
        return noop_coro()

    def fake_create_task(coro):
        coro.close()
        return DoneTask()

    monkeypatch.setattr(server_module, "_run_analysis", fake_run_analysis)
    monkeypatch.setattr(server_module.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(server_module.asyncio, "create_task", fake_create_task)

    response = client.post("/generate_report", headers=headers, json={"date": date, "full": True, "force": False})

    assert response.status_code == 200
    assert response.json()["request_id"] == "quick-report-job"
    assert response.json().get("reused") is None
    assert calls["count"] == 1


def test_sync_huawei_sleep_data_upsert_by_user_and_date(client_with_db):
    client, store = client_with_db
    _login_headers(client, "sleep_sync_user")
    hub = SyncHub(_TestSyncDb(store.db_path))
    store.save_huawei_sleep_data(1, "2026-06-25", {
        "sleep_score": 76,
        "morning_diary": "早上记录",
        "analysis_report": "旧报告",
    })

    ok, rejected = hub.upsert("huawei_sleep_data", {
        "id": 999,
        "date": "2026-06-25",
        "sleep_score": 81,
        "analysis_report": "新报告",
        "analysis_html": "<h1>新报告</h1>",
        "official_advice": "官方建议原文",
    }, user_id=1)

    assert ok is True
    assert rejected == []
    row = store.get_huawei_sleep_data(1, "2026-06-25")
    assert row["sleep_score"] == 81
    assert row["analysis_report"] == "新报告"
    assert row["analysis_html"] == "<h1>新报告</h1>"
    assert row["official_advice"] == "官方建议原文"
    assert row["morning_diary"] == "早上记录"


def test_huawei_sleep_save_writes_version_log_and_version_pull(client_with_db):
    _client, store = client_with_db
    store.create_user("sleep_version_user", "password123")
    user_id = store.verify_user("sleep_version_user", "password123")

    store.save_huawei_sleep_data(user_id, "2026-07-05", {
        "sleep_score": 88,
        "analysis_html": "<p>server report</p>",
        "report_status": 1,
    })

    conn = store._connect()
    try:
        change = conn.execute(
            """
            SELECT server_version, table_name, record_id
            FROM server_change_log
            WHERE user_id=? AND table_name='huawei_sleep_data'
            """,
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    assert change is not None
    assert int(change["server_version"]) >= 1

    hub = SyncHub(_TestSyncDb(store.db_path))
    result = asyncio.run(hub.handle_pull_by_version(0, user_id=user_id, limit=50))

    rows = result["tables"]["huawei_sleep_data"]
    assert rows[0]["date"] == "2026-07-05"
    assert rows[0]["sleep_score"] == 88


def test_db_wrapper_huawei_sleep_save_writes_version_log(client_with_db):
    _client, store = client_with_db
    store.create_user("wrapper_sleep_user", "password123")
    wrapper = ServerDBWrapper()
    wrapper.log_path = store.db_path

    assert wrapper.save_huawei_sleep_data("2026-07-06", {"sleep_score": 90}) is True

    conn = store._connect()
    try:
        row = conn.execute(
            """
            SELECT c.server_version, h.date, h.sleep_score
            FROM server_change_log c
            JOIN server_huawei_sleep_data h ON h.id = CAST(c.record_id AS INTEGER)
            WHERE c.table_name='huawei_sleep_data' AND h.date='2026-07-06'
            """,
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert int(row["server_version"]) >= 1
    assert row["sleep_score"] == 90


def test_ticktick_same_provider_habit_id_is_isolated_per_user(client_with_db):
    _client, store = client_with_db
    store.create_user("habit_owner", "password123")
    store.create_user("habit_other", "password123")
    owner_id = store.verify_user("habit_owner", "password123")
    other_id = store.verify_user("habit_other", "password123")
    hub = SyncHub(_TestSyncDb(store.db_path))

    class FakeTickTickClient:
        async def get_habits(self):
            return [{
                "id": "provider-habit-1",
                "name": "早睡",
                "status": 0,
                "iconRes": "txt_🌙",
                "sortOrder": 1,
                "sectionId": "",
                "repeatRule": "RRULE:FREQ=DAILY",
                "etag": "etag-1",
                "modifiedTime": "2026-07-08T08:00:00+00:00",
            }]

        async def get_habit_sections(self):
            return []

        async def get_habit_checkins(self, habit_ids, start, end):
            return []

    stats_owner = asyncio.run(hub._pull_habits(FakeTickTickClient(), owner_id))
    stats_other = asyncio.run(hub._pull_habits(FakeTickTickClient(), other_id))

    conn = store._connect()
    try:
        rows = conn.execute("SELECT id, user_id FROM server_habits ORDER BY user_id").fetchall()
    finally:
        conn.close()

    assert stats_owner["habit_changes"] == 1
    assert stats_other["habit_changes"] == 1
    assert [(row["id"], row["user_id"]) for row in rows] == [
        (f"ticktick:{owner_id}:provider-habit-1", owner_id),
        (f"ticktick:{other_id}:provider-habit-1", other_id),
    ]


def test_sleep_only_analysis_does_not_reuse_existing_full_report(client_with_db, monkeypatch, tmp_path):
    client, store = client_with_db
    headers = _login_headers(client, "sleep_only_user")
    date = "2026-06-26"
    store.create_job("existing-full-report-job", str(tmp_path / "sleep_2026-06-26.jpg"), user_id=1, date=date)
    store.mark_done("existing-full-report-job", date, {"date": date, "sleep_score": 81, "report_status": 2}, "# full report\n\n## ⏱️ [Part 2: 时间管理报告]")
    (tmp_path / "sleep_2026-06-26.jpg").write_bytes(b"backup")
    calls = {"count": 0}

    def fake_run_analysis(*args, **kwargs):
        calls["count"] += 1

    async def noop_coro():
        return None

    def fake_to_thread(func, *args, **kwargs):
        func(*args, **kwargs)
        return noop_coro()

    class DoneTask:
        def cancel(self):
            return None

    monkeypatch.setattr(server_module, "ATTACHMENTS_DIR", str(tmp_path))
    monkeypatch.setattr(server_module, "_run_analysis", fake_run_analysis)
    monkeypatch.setattr(server_module.asyncio, "to_thread", fake_to_thread)

    def fake_create_task(coro):
        coro.close()
        return DoneTask()

    monkeypatch.setattr(server_module.asyncio, "create_task", fake_create_task)

    resp = client.post("/generate_report", headers=headers, json={"date": date, "full": False, "force": False})

    assert resp.status_code == 200
    assert resp.json().get("reused") is not True
    assert calls["count"] == 1
