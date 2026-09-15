# -*- coding: utf-8 -*-
"""
工具模块 (utils.py)
==================
提供全局辅助函数:
- resource_path(): 资源路径解析，适配开发环境与 PyInstaller 打包
- setup_logging(): 日志系统初始化（控制台 + 按日轮转文件）
"""

import os
import sys
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime


def resource_path(relative_path):
    """
    获取资源绝对路径，适配开发环境和 PyInstaller 单文件/文件夹打包模式。

    分类规则:
    - 用户数据（配置/数据库/报表）→ 可执行文件同级目录（可写、持久化）
    - 内置资源（音频/图标）→ PyInstaller 临时解压目录（只读）

    Args:
        relative_path: 相对路径字符串，如 'config.json' 或 'study_music/start.mp3'

    Returns:
        拼接后的绝对路径
    """
    # 路径映射重定向
    if relative_path == 'config.json':
        relative_path = os.path.join('config', 'config.json')
    elif relative_path.startswith('study_music'):
        relative_path = relative_path.replace('study_music', os.path.join('assets', 'audio'))

    # 用户可写/持久化的数据文件列表
    user_data_files = [
        'config.json', 'study_log.db', 'study_log.json',
        'statistics.html', 'study_log.csv'
    ]

    if relative_path in user_data_files or relative_path.endswith('.db') or relative_path.endswith('.json') or relative_path.startswith('config'):
        # 用户数据：始终使用可执行文件所在的真实目录
        try:
            if getattr(sys, 'frozen', False):
                base_path = os.path.dirname(sys.executable)
            else:
                # 改进：不依赖 CWD，而是根据 utils.py 的位置推导根目录
                # utils.py 位于 [root]/app/utils/utils.py
                utils_dir = os.path.dirname(os.path.abspath(__file__))
                base_path = os.path.dirname(os.path.dirname(utils_dir))
        except Exception:
            base_path = os.path.abspath(".")

        # 确保父目录存在（如 config/ 文件夹）
        full_path = os.path.join(base_path, relative_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
    else:
        # 只读资源：优先使用 PyInstaller 的临时解压目录
        try:
            if getattr(sys, 'frozen', False):
                base_path = sys._MEIPASS
            else:
                utils_dir = os.path.dirname(os.path.abspath(__file__))
                base_path = os.path.dirname(os.path.dirname(utils_dir))
        except Exception:
            base_path = os.path.abspath(".")
        full_path = os.path.join(base_path, relative_path)

    return full_path


def get_db_path() -> str:
    """
    返回服务端兼容 SQLite 数据库的绝对路径，并确保 server/data/ 目录存在。

    统一的数据库路径入口，供 StudyLogger、CategoryManager、HabitStore 等共同使用，
    避免各模块各自拼接路径导致不一致。

    Returns:
        服务端 SQLite 数据库文件的绝对路径（server/data/my_time_logger.db）
    """
    path = resource_path("server/data/my_time_logger.db")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def setup_logging():
    """
    初始化日志系统。

    - 控制台输出 + 文件输出（按天轮转，保留 30 天）
    - 日志目录为程序运行目录下的 log/ 子目录
    - 防止重复添加 Handler
    """
    base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    log_dir = os.path.join(base_dir, "log")

    try:
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        log_file = os.path.join(log_dir, f"{datetime.now().strftime('%Y-%m-%d')}.log")

        logger = logging.getLogger()
        logger.setLevel(logging.INFO)

        # 防止重复添加 Handler
        if not logger.handlers:
            # 终端处理器
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            logger.addHandler(console_handler)

            # 文件处理器 (按天轮转，保留最近 30 天)
            file_handler = TimedRotatingFileHandler(
                log_file, when="midnight", interval=1, backupCount=30, encoding='utf-8'
            )
            file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            logger.addHandler(file_handler)

        logging.info("MyTimeLogger 日志系统初始化完成。")
    except Exception as e:
        print(f"日志初始化失败: {e}")


def to_min(val):
    """将各种格式的时间字符串或数值转换为分钟数"""
    import re
    if val is None or val == "":
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).lower()
    h_match = re.search(r"(\d+)\s*(?:h|小时|时)", s)
    m_match = re.search(r"(\d+)\s*(?:m|分钟|分)", s)
    total = 0
    if h_match:
        total += int(h_match.group(1)) * 60
    if m_match:
        total += int(m_match.group(1))
    if total > 0:
        return total
    try:
        clean_s = re.sub(r"[^\d.]", "", s)
        if not clean_s:
            return 0
        return int(float(clean_s))
    except Exception:
        return 0


def clean_num(val):
    """从模型输出提取数值"""
    import re
    if val is None or val == "":
        return 0
    if isinstance(val, (int, float)):
        return val
    try:
        clean_s = re.sub(r"[^\d.]", "", str(val))
        if not clean_s:
            return 0
        num = float(clean_s)
        return int(num) if num == int(num) else num
    except Exception:
        return 0


def clean_url(url):
    """自动处理用户填写的 URL，确保其符合 OpenAI SDK 要求（不含 /chat/completions）"""
    if not url or not isinstance(url, str):
        return ""
    url = url.strip().rstrip("/")
    if url.endswith("/chat/completions"):
        url = url[:-len("/chat/completions")].rstrip("/")
    return url


# ======================== 多端同步工具 ========================

def mark_pending_sync(db_path: str, table: str, record_id=None, config: dict = None,
                      where_col: str = "id", where_val=None):
    """
    标记记录为待同步：更新 pushed_at = NULL 并可选择更新 updated_at。

    Args:
        db_path: SQLite 数据库路径
        table: 表名（不带 server_ 前缀）
        record_id: 记录的主键 ID（当 where_col="id" 时使用）
        config: 全局配置字典，用于检查 server_mode
        where_col: WHERE 条件的列名，默认 "id"
        where_val: WHERE 条件的值，默认等于 record_id
    """
    import sqlite3
    from datetime import datetime
    now_ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    key_val = where_val if where_val is not None else record_id
    if key_val is None:
        return

    try:
        conn = sqlite3.connect(db_path)
        conn.execute(
            f"UPDATE {table} SET updated_at = ?, pushed_at = NULL WHERE {where_col} = ?",
            (now_ts, key_val)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # 表可能尚不存在

    # 入队 SyncWorker
    if config and config.get("server_mode"):
        try:
            from server.utils.sync_worker import get_sync_worker
            worker = get_sync_worker()
            if worker:
                worker.enqueue(table, key_val)
        except ImportError:
            pass
