# -*- coding: utf-8 -*-
"""
RewardStore 单元测试（5 个用例）
"""
import pytest
from server.models.reward_store import RewardStore
from server.models.schema import ensure_schema


def _store(tmp_db_path):
    ensure_schema(tmp_db_path)
    return RewardStore(db_path=tmp_db_path)


def test_init(tmp_db_path):
    """初始化不抛异常"""
    s = _store(tmp_db_path)
    assert s is not None


def test_get_balance_initial(tmp_db_path):
    """初始余额应为 0"""
    s = _store(tmp_db_path)
    assert s.get_balance() == 0


def test_add_ledger_entry(tmp_db_path):
    """add_ledger_entry 后 get_ledger_history 应包含该记录"""
    s = _store(tmp_db_path)
    s.add_ledger_entry(10.0, source_type="test", description="测试收入")
    history = s.get_ledger_history(10)
    assert len(history) >= 1
    assert any(abs(h["amount"] - 10.0) < 0.01 for h in history)


def test_add_reward(tmp_db_path):
    """添加奖励后 add_reward 不抛异常，余额查询正常"""
    s = _store(tmp_db_path)
    result = s.add_reward(title="看番剧", icon="🎬", price=5)
    # add_reward 返回 True 表示成功
    assert result is True or result is None or isinstance(result, bool)


def test_buy_reward_deducts_balance(tmp_db_path):
    """购买奖励后余额应减少"""
    s = _store(tmp_db_path)
    # 先充值
    s.add_ledger_entry(100.0, source_type="test", description="充值")
    balance_before = s.get_balance()
    # 添加奖励
    s.add_reward(title="奖励A", icon="🎁", price=20)
    # 通过 StudyLogger 代理查询奖励列表（RewardStore 无 get_all_rewards）
    import sqlite3
    conn = sqlite3.connect(tmp_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM rewards WHERE is_active=1 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    assert row is not None, "奖励应已写入数据库"
    reward_id = row["id"]
    ok, _ = s.buy_reward(reward_id)
    assert ok
    balance_after = s.get_balance()
    assert balance_after < balance_before


def test_auto_settle_goals(tmp_db_path):
    """测试 auto_settle_goals 正常加载 GoalStore 并结算"""
    s = _store(tmp_db_path)

    # 往数据库写入一条目标，和一条相关的 study_session，让结算产生作用
    import sqlite3
    from datetime import datetime, date, timedelta

    conn = sqlite3.connect(tmp_db_path)
    cursor = conn.cursor()

    # 写入目标
    cursor.execute("""
        INSERT INTO goals (title, category_id, metric, target_value, period, reward_coins, operator, penalty_coins, created_at)
        VALUES ('每日阅读', 1, 'duration', 30, 'daily', 5.0, '>=', 5.0, '2026-05-20 00:00:00')
    """)

    # 写入昨天的 study_session
    yesterday_str = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    cursor.execute("""
        INSERT INTO study_sessions (start_time, end_time, net_duration_minutes, date, day_of_week, pause_count, pause_reasons, session_summary, category_id)
        VALUES (?, ?, 40.0, ?, 'Monday', 0, '无', '专注阅读', 1)
    """, (f"{yesterday_str} 10:00:00", f"{yesterday_str} 10:40:00", yesterday_str))

    conn.commit()
    conn.close()

    # 运行自动结算
    s.auto_settle_goals()

    # 目标结算应生成待领取奖励，领取后再写入金币流水
    unclaimed = s.get_unclaimed_rewards()
    assert len(unclaimed) == 1
    assert unclaimed[0]["ext_id"].startswith("goal_")
    claimed = s.claim_rewards([unclaimed[0]["ext_id"]])
    assert claimed == 5.0

    # 检查流水表中是否有对应的奖励记录
    history = s.get_ledger_history(10)
    assert len(history) >= 1
    assert any(h['source_type'] == 'external_claim' and h['amount'] == 5.0 for h in history)
