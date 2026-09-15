# -*- coding: utf-8 -*-
"""
本地数据一键云同步迁移脚本 (migrate_to_cloud.py)
==============================================
用于将客户端本地 SQLite 数据库的历史专注会话、习惯打卡、金币流水、目标、外部奖励等数据
合并导入至云端数据库中，支持指定用户，自动重算外键映射，解决主键冲突，并实现幂等去重。
"""

import os
import sys
import sqlite3
import json
import logging
import uuid
from datetime import datetime

# 注入项目根目录以正常导入 server 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.utils.utils import resource_path


def _new_id():
    return str(uuid.uuid4())


def _now_str():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )


def get_desktop_db_path():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "desktop", "local_data", "my_time_logger.db")


def load_user_id_from_config(server_db_path, username_arg=None):
    """
    通过 config.json 或命令行用户名解析云端 user_id
    """
    config_path = resource_path("config.json")
    auth_token = None
    username = None

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                auth_token = config.get("auth_token")
                # 尝试从 ticktick 或其它配置找可能的用户名
                username = config.get("username") or config.get("ticktick_config", {}).get("username")
        except Exception as e:
            logging.warning(f"读取 config.json 失败: {e}")

    if username_arg:
        username = username_arg

    conn = sqlite3.connect(server_db_path)
    cursor = conn.cursor()
    user_id = None

    try:
        # 1. 如果有 token，优先使用 token 匹配 session
        if auth_token:
            cursor.execute(
                """
                SELECT u.id, u.username FROM users u
                JOIN sessions s ON u.id = s.user_id
                WHERE s.token = ? AND (s.expires_at IS NULL OR s.expires_at > datetime('now', 'localtime'))
                """,
                (auth_token,)
            )
            row = cursor.fetchone()
            if row:
                user_id = row[0]
                logging.info(f"成功使用配置中的 Token 匹配到云端用户: {row[1]} (ID: {user_id})")
                return user_id

        # 2. 如果没有 token 或 token 失效，但有用户名，通过用户名查找
        if username:
            cursor.execute("SELECT id, username FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()
            if row:
                user_id = row[0]
                logging.info(f"成功使用用户名匹配到云端用户: {row[1]} (ID: {user_id})")
                return user_id

        # 3. 兜底：如果数据库里只有一个用户，且没有明确指定，就直接用这一个（Legacy 模式）
        cursor.execute("SELECT id, username FROM users")
        users = cursor.fetchall()
        if len(users) == 1:
            user_id = users[0][0]
            logging.info(f"云端仅存在单个用户，自动绑定: {users[0][1]} (ID: {user_id})")
            return user_id

    finally:
        conn.close()

    return None


def migrate(local_db_path, server_db_path, user_id):
    """
    核心搬迁逻辑，带事务保护
    """
    logging.info(f"开始迁移本地数据库: {local_db_path} -> 云端数据库: {server_db_path}")

    local_conn = sqlite3.connect(local_db_path)
    local_conn.row_factory = sqlite3.Row
    local_cursor = local_conn.cursor()

    server_conn = sqlite3.connect(server_db_path)
    server_cursor = server_conn.cursor()

    try:
        # ============================================================
        # 1. 迁移分类 categories
        # ============================================================
        logging.info("--- 迁移时间分类数据 (categories) ---")
        local_cursor.execute("SELECT * FROM categories")
        local_cats = [dict(r) for r in local_cursor.fetchall()]

        local_cat_id_to_cloud_id = {}
        cat_insert_count = 0

        for cat in local_cats:
            local_id = cat["id"]
            name = cat["name"]
            group_name = cat["group_name"]
            icon = cat.get("icon") or "📖"
            color = cat.get("color") or "#5E81AC"
            created_at = cat.get("created_at") or datetime.now().isoformat()

            # 去重：同名同组分类视为同一个
            server_cursor.execute(
                "SELECT id FROM server_categories WHERE user_id = ? AND name = ?",
                (user_id, name)
            )
            row = server_cursor.fetchone()
            if row:
                cloud_id = row[0]
                local_cat_id_to_cloud_id[local_id] = cloud_id
            else:
                server_cursor.execute(
                    """
                    INSERT INTO server_categories (user_id, name, group_name, icon, color)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, name, group_name, icon, color)
                )
                cloud_id = server_cursor.lastrowid
                local_cat_id_to_cloud_id[local_id] = cloud_id
                cat_insert_count += 1

        logging.info(f"分类数据迁移完毕: 共新增 {cat_insert_count} 个分类，重用/映射 {len(local_cat_id_to_cloud_id) - cat_insert_count} 个。")

        # ============================================================
        # 2. 迁移习惯 habits
        # ============================================================
        logging.info("--- 迁移习惯配置数据 (habits) ---")
        local_cursor.execute("SELECT * FROM habits")
        local_habits = [dict(r) for r in local_cursor.fetchall()]

        local_habit_id_to_cloud_id = {}
        habit_insert_count = 0

        for h in local_habits:
            local_id = h["id"]
            title = h["title"]
            icon = h.get("icon") or "✅"
            color = h.get("color") or "#A3BE8C"
            frequency = h.get("frequency") or "daily"
            local_cat_id = h.get("category_id")
            is_active = h.get("is_active") if h.get("is_active") is not None else 1
            difficulty = h.get("difficulty") or "easy"
            created_at = h.get("created_at") or datetime.now().isoformat()

            cloud_cat_id = local_cat_id_to_cloud_id.get(local_cat_id)

            # 去重：同名习惯视为同一个
            server_cursor.execute(
                "SELECT id FROM server_habits WHERE user_id = ? AND name = ?",
                (user_id, title)
            )
            row = server_cursor.fetchone()
            if row:
                cloud_id = row[0]
                local_habit_id_to_cloud_id[local_id] = cloud_id
            else:
                cloud_id = _new_id()
                updated_at = _now_str()
                server_cursor.execute(
                    """
                    INSERT INTO server_habits
                    (id, user_id, name, icon, color, category_id, is_active, difficulty, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (cloud_id, user_id, title, icon, color, cloud_cat_id, is_active, difficulty, created_at, updated_at)
                )
                local_habit_id_to_cloud_id[local_id] = cloud_id
                habit_insert_count += 1

        logging.info(f"习惯数据迁移完毕: 共新增 {habit_insert_count} 个习惯。")

        # ============================================================
        # 3. 迁移专注于学习记录 study_sessions
        # ============================================================
        logging.info("--- 迁移专注会话数据 (study_sessions) ---")
        local_cursor.execute("SELECT * FROM study_sessions")
        local_sessions = [dict(r) for r in local_cursor.fetchall()]

        session_insert_count = 0

        for s in local_sessions:
            start_time = s["start_time"]
            end_time = s["end_time"]
            net_dur = s["net_duration_minutes"]
            date_str = s["date"]
            day_of_week = s.get("day_of_week")
            pause_count = s.get("pause_count") or 0
            pause_reasons = s.get("pause_reasons")
            summary = s.get("session_summary")
            local_cat_id = s.get("category_id")

            cloud_cat_id = local_cat_id_to_cloud_id.get(local_cat_id)

            # 去重：同一时间段已存在记录则不重复导入
            server_cursor.execute(
                "SELECT 1 FROM server_study_sessions WHERE user_id = ? AND start_time = ? AND end_time = ?",
                (user_id, start_time, end_time)
            )
            if not server_cursor.fetchone():
                updated_at = _now_str()
                server_cursor.execute(
                    """
                    INSERT INTO server_study_sessions
                    (id, user_id, start_time, end_time, net_duration_minutes, date, day_of_week, pause_count, pause_reasons, session_summary, category_id, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (_new_id(), user_id, start_time, end_time, net_dur, date_str, day_of_week, pause_count, pause_reasons, summary, cloud_cat_id, updated_at)
                )
                session_insert_count += 1

        logging.info(f"专注会话迁移完毕: 共写入 {session_insert_count} 条记录。")

        # ============================================================
        # 4. 迁移打卡明细记录 habit_checkins
        # ============================================================
        logging.info("--- 迁移打卡明细数据 (habit_checkins) ---")
        local_cursor.execute("SELECT * FROM habit_checkins")
        local_checkins = [dict(r) for r in local_cursor.fetchall()]

        checkin_insert_count = 0

        for c in local_checkins:
            local_h_id = c["habit_id"]
            checkin_date = c["checkin_date"]
            checkin_time = c.get("checkin_time")
            note = c.get("note") or ""
            status = c.get("status") if c.get("status") is not None else 1

            cloud_h_id = local_habit_id_to_cloud_id.get(local_h_id)
            if not cloud_h_id:
                continue

            # 去重：同一个习惯在同一天打卡不重复
            server_cursor.execute(
                "SELECT 1 FROM server_habit_checkins WHERE user_id = ? AND habit_id = ? AND date = ?",
                (user_id, cloud_h_id, checkin_date)
            )
            if not server_cursor.fetchone():
                created_at = checkin_time or (checkin_date + " 00:00:00")
                updated_at = _now_str()
                server_cursor.execute(
                    """
                    INSERT INTO server_habit_checkins
                    (id, user_id, habit_id, habit_name, date, created_at, checkin_date, checkin_time, status, note, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (_new_id(), user_id, cloud_h_id, None, checkin_date, created_at, checkin_date, checkin_time, status, note, updated_at)
                )
                checkin_insert_count += 1

        logging.info(f"打卡明细迁移完毕: 共写入 {checkin_insert_count} 条记录。")

        # ============================================================
        # 5. 迁移目标 challenges (goals)
        # ============================================================
        logging.info("--- 迁移目标数据 (goals) ---")
        local_cursor.execute("SELECT * FROM goals")
        local_goals = [dict(r) for r in local_cursor.fetchall()]

        goal_insert_count = 0

        for g in local_goals:
            title = g["title"]
            local_cat_id = g.get("category_id")
            metric = g["metric"]
            target_value = g["target_value"]
            period = g["period"]
            reward_coins = g.get("reward_coins") or 0.0
            reward_id = g.get("reward_id")
            operator = g.get("operator") or ">="
            is_active = g.get("is_active") if g.get("is_active") is not None else 1
            created_at = g.get("created_at") or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            penalty_coins = g.get("penalty_coins") or 0.0

            cloud_cat_id = local_cat_id_to_cloud_id.get(local_cat_id)

            # 去重：相同名称和周期的目标不重复
            server_cursor.execute(
                "SELECT 1 FROM server_goals WHERE user_id = ? AND title = ? AND period = ?",
                (user_id, title, period)
            )
            if not server_cursor.fetchone():
                updated_at = _now_str()
                server_cursor.execute(
                    """
                    INSERT INTO server_goals
                    (id, user_id, title, category_id, metric, target_value, period, reward_coins, reward_id, operator, is_active, created_at, penalty_coins, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (_new_id(), user_id, title, cloud_cat_id, metric, target_value, period, reward_coins, reward_id, operator, is_active, created_at, penalty_coins, updated_at)
                )
                goal_insert_count += 1

        logging.info(f"目标迁移完毕: 共写入 {goal_insert_count} 条记录。")

        # ============================================================
        # 6. 迁移外部奖励 (external_rewards)
        # ============================================================
        logging.info("--- 迁移外部结算奖励数据 (external_rewards) ---")
        local_cursor.execute("SELECT * FROM external_rewards")
        local_exts = [dict(r) for r in local_cursor.fetchall()]

        ext_insert_count = 0

        for ex in local_exts:
            ext_id = ex.get("ext_id") or str(ex["id"])
            item_type = ex["item_type"]
            item_name = ex["item_name"]
            coins = ex["coins"]
            status = ex.get("status") or 0
            created_at = ex.get("created_at") or datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # 去重：按 ext_id
            server_cursor.execute("SELECT 1 FROM server_external_rewards WHERE user_id = ? AND ext_id = ?", (user_id, ext_id))
            if not server_cursor.fetchone():
                updated_at = _now_str()
                server_cursor.execute(
                    """
                    INSERT INTO server_external_rewards (id, ext_id, user_id, item_type, item_name, coins, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (_new_id(), ext_id, user_id, item_type, item_name, coins, status, created_at, updated_at)
                )
                ext_insert_count += 1

        logging.info(f"外部结算奖励迁移完毕: 共写入 {ext_insert_count} 条记录。")

        # ============================================================
        # 7. 迁移金币流水记录 reward_ledger
        # ============================================================
        logging.info("--- 迁移金币收支流水数据 (reward_ledger) ---")
        local_cursor.execute("SELECT * FROM reward_ledger")
        local_ledgers = [dict(r) for r in local_cursor.fetchall()]

        ledger_insert_count = 0

        for l in local_ledgers:
            amount = l["amount"]
            source_type = l["source_type"]
            source_id = l.get("source_id")
            description = l.get("description")
            created_at = l.get("created_at") or datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # 将习惯、打卡等 source_id 转换为云端 ID
            cloud_source_id = source_id
            if source_type in ("habit_checkin", "habit_miss") and source_id:
                try:
                    cloud_source_id = local_habit_id_to_cloud_id.get(int(source_id))
                except ValueError:
                    pass

            # 去重：同一条流水不重复
            server_cursor.execute(
                """
                SELECT 1 FROM server_reward_ledger
                WHERE user_id = ? AND amount = ? AND source_type = ? AND (source_id = ? OR source_id IS NULL) AND created_at = ?
                """,
                (user_id, amount, source_type, str(cloud_source_id) if cloud_source_id else None, created_at)
            )
            if not server_cursor.fetchone():
                updated_at = _now_str()
                server_cursor.execute(
                    """
                    INSERT INTO server_reward_ledger (id, user_id, amount, source_type, source_id, description, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (_new_id(), user_id, amount, source_type, str(cloud_source_id) if cloud_source_id else None, description, created_at, updated_at)
                )
                ledger_insert_count += 1

        logging.info(f"积分/金币流水迁移完毕: 共写入 {ledger_insert_count} 条记录。")

        # ============================================================
        # 8. 提交事务
        # ============================================================
        server_conn.commit()
        logging.info("🎉 迁移事务成功提交！本地历史数据已无缝并入云端账户。")

    except Exception as e:
        server_conn.rollback()
        logging.error(f"❌ 迁移过程中发生异常，事务已回滚: {e}")
        raise e
    finally:
        local_conn.close()
        server_conn.close()


def main():
    setup_logging()

    # 解析命令行参数
    import argparse
    parser = argparse.ArgumentParser(description="一键将本地 SQLite 历史数据迁移并入云端账户")
    parser.add_argument("--user", type=str, help="云端用户名（当 config.json 中没有有效 Token 时使用）")
    parser.add_argument("--local-db", type=str, help="本地 SQLite 数据库路径")
    parser.add_argument("--server-db", type=str, help="云端 SQLite 数据库路径")
    args = parser.parse_args()

    # 路径决策
    local_db_path = args.local_db or get_desktop_db_path()
    server_db_path = args.server_db or resource_path("server/data/server_sleep_jobs.db")

    if not os.path.exists(local_db_path):
        logging.error(f"本地数据库文件不存在: {local_db_path}")
        sys.exit(1)

    if not os.path.exists(server_db_path):
        logging.error(f"云端数据库文件不存在: {server_db_path}，请先启动服务端以初始化建表")
        sys.exit(1)

    # 查找 user_id
    user_id = load_user_id_from_config(server_db_path, args.user)
    if user_id is None:
        logging.error("无法识别匹配的云端账户，请注册并使用客户端登录后再运行此脚本，或者使用 `--user <用户名>` 参数手动指定绑定账户。")
        sys.exit(1)

    # 开始迁移
    migrate(local_db_path, server_db_path, user_id)


if __name__ == "__main__":
    main()
