# -*- coding: utf-8 -*-
"""
HabitStore 单元测试（5 个用例）
"""
import pytest
from datetime import date
from server.models.habit_store import HabitStore


def _store(tmp_db_path):
    """HabitStore 需要先用 ensure_schema 建表，再调用 _migrate_habits_table"""
    from server.models.schema import ensure_schema
    ensure_schema(tmp_db_path)
    s = HabitStore(db_path=tmp_db_path)
    s._migrate_habits_table()
    return s


def test_init(tmp_db_path):
    """初始化不抛异常，_migrate_habits_table 幂等"""
    s = _store(tmp_db_path)
    s._migrate_habits_table()  # 再次调用应无副作用


def test_add_habit(tmp_db_path):
    """添加习惯后 get_all_habits 应包含它"""
    s = _store(tmp_db_path)
    s.add_habit("早起", icon="🌅", color="#A3BE8C", difficulty="easy")
    habits = s.get_all_habits()
    names = [h["title"] for h in habits]
    assert "早起" in names


def test_checkin(tmp_db_path):
    """打卡后 get_today_checkins 应包含该习惯 ID 作为键"""
    s = _store(tmp_db_path)
    habit_id = s.add_habit("运动", icon="🏃", color="#5E81AC", difficulty="medium")
    today = date.today().strftime("%Y-%m-%d")
    s.toggle_checkin(habit_id, today)
    checkins = s.get_today_checkins(today)
    # get_today_checkins 返回 {habit_id: status} 字典
    assert isinstance(checkins, dict)
    assert habit_id in checkins


def test_get_today_checkins(tmp_db_path):
    """get_today_checkins 应返回字典"""
    s = _store(tmp_db_path)
    today = date.today().strftime("%Y-%m-%d")
    result = s.get_today_checkins(today)
    assert isinstance(result, dict)


def test_streak(tmp_db_path):
    """打卡后连续天数应 >= 1"""
    s = _store(tmp_db_path)
    habit_id = s.add_habit("阅读", icon="📚", color="#EBCB8B", difficulty="easy")
    today = date.today().strftime("%Y-%m-%d")
    s.toggle_checkin(habit_id, today)
    streak = s.get_habit_streak(habit_id)
    assert streak >= 1


def test_makeup_discount(tmp_db_path):
    """历史日期补卡应该打 5 折，且描述中带 [MM-DD] 格式"""
    from datetime import datetime, timedelta
    s = _store(tmp_db_path)
    # 添加一个 medium 难度的习惯，基础积分 10.0
    habit_id = s.add_habit("冥想", icon="🧘", color="#EBCB8B", difficulty="medium")

    # 模拟昨天的补卡
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_lbl = (datetime.now() - timedelta(days=1)).strftime("%m-%d")

    # 打卡昨天
    status, streak, coins = s.toggle_checkin(habit_id, yesterday)
    # 客户端 medium 难度基础积分 2.5 + streak 0.5 = 3.0，打折后是 1.5
    assert coins == 1.5

    # 检查流水表 reward_ledger
    conn = s._connect()
    cursor = conn.cursor()
    cursor.execute("SELECT amount, description FROM reward_ledger WHERE source_type='habit_checkin' AND source_id=?", (habit_id,))
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == 1.5
    assert f"习惯补卡[{yesterday_lbl}]" in row[1]
    conn.close()
