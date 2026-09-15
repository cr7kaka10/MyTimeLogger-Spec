# -*- coding: utf-8 -*-
"""
CHG-20260526-008 - 时间书数据层单元测试
验证 5 个新增数据方法在 SQLite 测试库中的基本读写逻辑。
"""
import sqlite3
import tempfile
import os
import pytest
from datetime import datetime, timedelta


# ── 构造测试用 StudyLogger（指向临时 SQLite）

def _make_test_logger():
    """
    创建指向临时 SQLite 文件的 StudyLogger 实例。
    只 mock get_db_path，让 ensure_schema 自然建内置表，
    再手动补建 categories（categories 不在 ensure_schema 管辖范围）。
    """
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = tmp.name

    from unittest.mock import patch
    from server.models.database import StudyLogger

    config = {"db_type": "sqlite", "server_mode": False}
    with patch("server.models.database.get_db_path", return_value=db_path):
        logger = StudyLogger(config)

    # categories 表由 CategoryManager 管理，ensure_schema 里没有，手动补建
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            color TEXT DEFAULT '#007AFF',
            group_name TEXT,
            is_active INTEGER DEFAULT 1
        );
        INSERT OR IGNORE INTO categories (id, name, color, group_name, is_active)
            VALUES (1, '输入', '#007AFF', '输入', 1);
        INSERT OR IGNORE INTO categories (id, name, color, group_name, is_active)
            VALUES (2, '拉屎', '#8E8E93', '生活', 1);
    """)
    conn.commit()
    conn.close()

    return logger, db_path


def _insert_session(db_path, start_str, end_str, category_id=1):
    """直接向 study_sessions 插入一条测试记录，返回 rowid。"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO study_sessions
           (start_time, end_time, net_duration_minutes, date, day_of_week,
            pause_count, pause_reasons, session_summary, category_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (start_str, end_str, 30.0, start_str[:10], "Monday",
         0, "无", "测试摘要", category_id),
    )
    conn.commit()
    rowid = cur.lastrowid
    conn.close()
    return rowid


# ── Test-1: get_sessions_by_date

def test_get_sessions_by_date_returns_correct_date():
    """只返回指定日期的 session，其他日期不出现。"""
    logger, db_path = _make_test_logger()

    _insert_session(db_path, "2026-05-26 09:00:00", "2026-05-26 09:30:00")
    _insert_session(db_path, "2026-05-25 10:00:00", "2026-05-25 10:30:00")  # 不同日期

    rows = logger.get_sessions_by_date("2026-05-26")
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-05-26"


def test_get_sessions_by_date_sorted_asc():
    """同一天多条记录按 start_time 正序返回。"""
    logger, db_path = _make_test_logger()

    _insert_session(db_path, "2026-05-26 13:00:00", "2026-05-26 13:30:00")
    _insert_session(db_path, "2026-05-26 09:00:00", "2026-05-26 09:30:00")

    rows = logger.get_sessions_by_date("2026-05-26")
    assert rows[0]["start_time"] < rows[1]["start_time"]


def test_get_sessions_by_date_includes_category_name():
    """返回的 dict 中包含 category_name 字段。"""
    logger, db_path = _make_test_logger()
    _insert_session(db_path, "2026-05-26 09:00:00", "2026-05-26 09:30:00", category_id=1)

    rows = logger.get_sessions_by_date("2026-05-26")
    assert "category_name" in rows[0]
    assert rows[0]["category_name"] == "输入"


# ── Test-2: get_available_dates

def test_get_available_dates_returns_distinct_dates():
    """只返回有记录的不重复日期，按倒序。"""
    logger, db_path = _make_test_logger()

    _insert_session(db_path, "2026-05-26 09:00:00", "2026-05-26 09:30:00")
    _insert_session(db_path, "2026-05-26 10:00:00", "2026-05-26 10:30:00")  # 同一天第2条
    _insert_session(db_path, "2026-05-25 09:00:00", "2026-05-25 09:30:00")

    dates = logger.get_available_dates()
    assert len(dates) == 2
    assert dates[0] == "2026-05-26"  # 倒序，最新在前
    assert dates[1] == "2026-05-25"


# ── Test-3: update_session

def test_update_session_modifies_summary():
    """update_session 可以修改 session_summary。"""
    logger, db_path = _make_test_logger()
    sid = _insert_session(db_path, "2026-05-26 09:00:00", "2026-05-26 09:30:00")

    ok = logger.update_session(sid, {"session_summary": "新摘要"})
    assert ok is True

    rows = logger.get_sessions_by_date("2026-05-26")
    assert rows[0]["session_summary"] == "新摘要"


def test_update_session_rejects_unknown_fields():
    """update_session 忽略不在白名单的字段，不更新，返回 False。"""
    logger, db_path = _make_test_logger()
    sid = _insert_session(db_path, "2026-05-26 09:00:00", "2026-05-26 09:30:00")

    ok = logger.update_session(sid, {"unknown_field": "hack"})
    assert ok is False


# ── Test-4: delete_session

def test_delete_session_removes_record():
    """delete_session 硬删除后记录消失。"""
    logger, db_path = _make_test_logger()
    sid = _insert_session(db_path, "2026-05-26 09:00:00", "2026-05-26 09:30:00")

    ok = logger.delete_session(sid)
    assert ok is True

    rows = logger.get_sessions_by_date("2026-05-26")
    assert len(rows) == 0


# ── Test-5: insert_session

def test_insert_session_creates_record():
    """insert_session 写入后可以通过 get_sessions_by_date 读回。"""
    logger, db_path = _make_test_logger()

    new_id = logger.insert_session({
        "start_time": "2026-05-26 14:00:00",
        "end_time": "2026-05-26 14:30:00",
        "net_duration_minutes": 30.0,
        "session_summary": "手动录入测试",
        "category_id": 1,
    })
    assert new_id >= 0

    rows = logger.get_sessions_by_date("2026-05-26")
    assert len(rows) == 1
    assert rows[0]["session_summary"] == "手动录入测试"
    assert rows[0]["date"] == "2026-05-26"


def test_insert_session_auto_extracts_date():
    """insert_session 应自动从 start_time 提取 date 字段。"""
    logger, db_path = _make_test_logger()

    new_id = logger.insert_session({
        "start_time": "2026-01-15 08:00:00",
        "end_time": "2026-01-15 09:00:00",
        "net_duration_minutes": 60.0,
    })
    rows = logger.get_sessions_by_date("2026-01-15")
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-01-15"
