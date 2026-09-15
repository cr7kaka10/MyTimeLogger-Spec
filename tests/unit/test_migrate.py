# -*- coding: utf-8 -*-
import os
import sqlite3
import pytest
from scripts.migrate_to_cloud import migrate
from server.models.schema import ensure_schema
from server.store import ServerSleepStore


@pytest.fixture
def temp_dbs(tmp_path):
    local_db = str(tmp_path / "local.db")
    server_db = str(tmp_path / "server.db")

    # 1. 初始化本地 Schema 和表
    ensure_schema(local_db)
    from server.models.category_manager import CategoryManager
    from server.models.habit_store import HabitStore
    from server.models.reward_store import RewardStore
    from server.models.goal_store import GoalStore
    CategoryManager(local_db)
    HabitStore(local_db)
    RewardStore(local_db)
    GoalStore(local_db)

    # 2. 初始化云端 Schema
    server_store = ServerSleepStore(server_db)
    # ServerSleepStore 会在初始化时自动建表并升级版本

    yield local_db, server_db


def test_migration_logic(temp_dbs):
    local_db, server_db = temp_dbs
    user_id = 42

    # 1. 制造本地数据
    local_conn = sqlite3.connect(local_db)
    local_cursor = local_conn.cursor()
    local_cursor.execute("DELETE FROM categories")
    local_cursor.execute("DELETE FROM habits")
    local_cursor.execute("DELETE FROM habit_checkins")
    local_cursor.execute("DELETE FROM reward_ledger")

    # 本地分类
    local_cursor.execute(
        "INSERT INTO categories (id, name, group_name, icon, color, sort_order, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (1, "编程", "输入", "💻", "#5E81AC", 0, "2026-05-26 12:00:00")
    )
    # 本地专注记录
    local_cursor.execute(
        "INSERT INTO study_sessions (start_time, end_time, net_duration_minutes, date, category_id) VALUES (?, ?, ?, ?, ?)",
        ("2026-05-26 14:00:00", "2026-05-26 15:00:00", 60.0, "2026-05-26", 1)
    )
    # 本地习惯
    local_cursor.execute(
        "INSERT INTO habits (id, title, icon, difficulty, category_id) VALUES (?, ?, ?, ?, ?)",
        (1, "写代码", "⌨️", "medium", 1)
    )
    # 本打卡记录
    local_cursor.execute(
        "INSERT INTO habit_checkins (habit_id, checkin_date, status) VALUES (?, ?, ?)",
        (1, "2026-05-26", 1)
    )
    # 本地流水
    local_cursor.execute(
        "INSERT INTO reward_ledger (amount, source_type, source_id, description) VALUES (?, ?, ?, ?)",
        (5.0, "habit_checkin", "1", "习惯打卡: 写代码")
    )

    local_conn.commit()
    local_conn.close()

    # 2. 制造云端数据库初始数据，预置一个分类制造主键占用，使得自增 ID 会发生冲突和重算
    server_conn = sqlite3.connect(server_db)
    server_cursor = server_conn.cursor()
    # 占用 ID = 1
    server_cursor.execute(
        "INSERT INTO server_categories (id, user_id, name, group_name, icon, color) VALUES (?, ?, ?, ?, ?, ?)",
        (1, user_id, "生活", "健康", "🍏", "green")
    )
    server_conn.commit()
    server_conn.close()

    # 3. 运行迁移脚本
    migrate(local_db, server_db, user_id)

    # 4. 验证迁移结果
    server_conn = sqlite3.connect(server_db)
    server_conn.row_factory = sqlite3.Row
    server_cursor = server_conn.cursor()

    # 4a. 验证分类已被正确插入，且本地的 ID 1 编程因为主键占用重算为了 ID 2
    server_cursor.execute("SELECT * FROM server_categories WHERE user_id = ? ORDER BY id ASC", (user_id,))
    cats = [dict(r) for r in server_cursor.fetchall()]
    assert len(cats) == 2
    assert cats[0]["name"] == "生活"
    assert cats[0]["id"] == 1
    assert cats[1]["name"] == "编程"
    assert cats[1]["id"] == 2  # 重算为了 ID 2

    # 4b. 验证专注会话已正确插入，且 category_id 已经被正确地重算更新为 2
    server_cursor.execute("SELECT * FROM server_study_sessions WHERE user_id = ?", (user_id,))
    sessions = [dict(r) for r in server_cursor.fetchall()]
    assert len(sessions) == 1
    assert sessions[0]["net_duration_minutes"] == 60.0
    assert sessions[0]["category_id"] == 2  # 重算映射成功！

    # 4c. 验证习惯和打卡
    server_cursor.execute("SELECT * FROM server_habits WHERE user_id = ?", (user_id,))
    habits = [dict(r) for r in server_cursor.fetchall()]
    assert len(habits) == 1
    assert habits[0]["name"] == "写代码"
    new_habit_id = habits[0]["id"]

    server_cursor.execute("SELECT * FROM server_habit_checkins WHERE user_id = ?", (user_id,))
    checkins = [dict(r) for r in server_cursor.fetchall()]
    assert len(checkins) == 1
    assert checkins[0]["habit_id"] == new_habit_id
    assert checkins[0]["date"] == "2026-05-26"

    # 4d. 验证金币流水，source_id 也要跟着变成云端的 new_habit_id
    server_cursor.execute("SELECT * FROM server_reward_ledger WHERE user_id = ?", (user_id,))
    ledger = [dict(r) for r in server_cursor.fetchall()]
    assert len(ledger) == 1
    assert ledger[0]["amount"] == 5.0
    assert ledger[0]["source_id"] == str(new_habit_id)

    server_conn.close()
