# -*- coding: utf-8 -*-
"""
配置模块 (config.py)
===================
管理应用程序的配置:
- DEFAULT_CONFIG: 全部配置项的默认值定义
- load_or_create_config(): 加载 config.json，缺失时自动创建并补全字段
- save_config(): 将当前配置持久化到 config.json

设计原则：
    本模块不依赖任何 UI 框架 import，保持平台无关性，
    便于未来安卓端或命令行工具复用。
    配置解析错误时抛出 ConfigParseError，由调用方（gui.py）负责展示错误对话框。
"""

import json
import logging
import base64

from .utils import resource_path


class ConfigParseError(ValueError):
    """config.json 解析失败时抛出，携带原始异常信息供调用方展示。"""
    pass

# ========== 默认配置 ==========
# 所有可配置项的默认值，首次运行时会以此生成 config.json
DEFAULT_CONFIG = {
    "study_time_min": 5 * 60,          # 单轮学习最短时长（秒）
    "study_time_max": 7 * 60,          # 单轮学习最长时长（秒）
    "short_break_duration": 10,        # 短休息时长（秒）
    "long_break_threshold": 90 * 60,   # 触发长休息的累计学习时长阈值（秒）
    "long_break_duration": 20 * 60,    # 长休息时长（秒）
    "music_folder": "assets/audio",    # 音效资源文件夹
    "sound_files": {                   # 各场景音效文件名
        "start_short_break": "start_short_break.mp3",
        "start_long_break": "start_long_break.mp3",
        "end_long_break": "end_long_break.mp3",
        "victory": "victory.mp3",
        "start_study": "start_study.mp3"
    },
    "total_study_time": 0,             # 持久化的累计学习时长（秒）
    "hotkeys": {                       # 全局快捷键
        "toggle_pause": "<alt>+c",
        "toggle_activity_panel": "<alt>+z"
    },
    "ticktick_config": {               # TickTick 日清单同步配置
        "enabled": False,
        "host": "ticktick.com",
        "client_id": "",
        "client_secret": "",
        "access_token": "",
        "username": "",
        "password": "",
        "sync_interval": 300
    },
    "ai_model_config": {               # AI 模型配置
        "vision_base_url": "https://open.bigmodel.cn/api/paas/v4",
        "vision_api_key": "",
        "vision_model": "glm-4v-flash",

        "text_base_url": "https://open.bigmodel.cn/api/paas/v4",
        "text_api_key": "",
        "text_model": "glm-4-flash"
    }
}


def obfuscate_token(token: str) -> str:
    """对 Token 进行简单的加密混淆保护隐私"""
    if not token:
        return ""
    if token.startswith("obf::"):
        return token
    try:
        # 反转字符串后做 base64 混淆
        reversed_token = token[::-1]
        obf = base64.b64encode(reversed_token.encode('utf-8')).decode('utf-8')
        return f"obf::{obf}"
    except Exception:
        return token


def deobfuscate_token(obfuscated: str) -> str:
    """对混淆后的 Token 进行还原"""
    if not obfuscated:
        return ""
    if obfuscated.startswith("obf::"):
        try:
            content = obfuscated[5:]
            decoded = base64.b64decode(content.encode('utf-8')).decode('utf-8')
            return decoded[::-1]
        except Exception:
            return obfuscated
    return obfuscated


def _save_to_db(cursor, config_dict):
    for k, v in config_dict.items():
        if isinstance(v, (dict, list)):
            val_str = json.dumps(v, ensure_ascii=False)
            val_type = 'json'
        elif isinstance(v, bool):
            val_str = 'true' if v else 'false'
            val_type = 'bool'
        elif isinstance(v, int):
            val_str = str(v)
            val_type = 'int'
        elif isinstance(v, float):
            val_str = str(v)
            val_type = 'float'
        else:
            val_str = str(v)
            val_type = 'str'

        cursor.execute(
            "INSERT OR REPLACE INTO system_config (key, value, value_type, description) VALUES (?, ?, ?, ?)",
            (k, val_str, val_type, "")
        )


def load_or_create_config():
    """
    从本地 SQLite 数据库中加载配置，支持首次运行自愈迁移。

    特性:
    - 优先从系统数据库加载；
    - 数据库无记录时检测并迁移 config/config.json，然后重命名为 config.json.migrated 备份；
    - 自动补全缺失的配置字段（向后兼容）；
    - 兼容旧版快捷键字段名（start_resume → start, pause → toggle_pause）。

    Returns:
        dict: 完整的配置字典
    """
    import os
    import sqlite3
    from .utils import get_db_path

    db_path = get_db_path()

    # 确保数据库 Schema 是最新的
    from server.models.schema import ensure_schema
    ensure_schema(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT key, value, value_type FROM system_config")
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        ensure_schema(db_path)
        cursor.execute("SELECT key, value, value_type FROM system_config")
        rows = cursor.fetchall()

    db_config = {}
    for key, value, value_type in rows:
        try:
            if value_type == 'json':
                db_config[key] = json.loads(value)
            elif value_type == 'int':
                db_config[key] = int(value)
            elif value_type == 'float':
                db_config[key] = float(value)
            elif value_type == 'bool':
                db_config[key] = (value.lower() == 'true')
            else:
                db_config[key] = value
        except Exception as e:
            logging.error(f"反序列化配置项 {key} 失败: {e}")

    config_path = resource_path('config.json')

    if not db_config:
        # 数据库中没有配置，尝试从 config.json 迁移
        if os.path.exists(config_path):
            logging.info("数据库配置为空，但检测到本地 config.json，正在执行向数据库的迁移...")
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                _save_to_db(cursor, user_config)
                conn.commit()

                # 迁移完成后重命名备份
                try:
                    os.rename(config_path, config_path + ".migrated")
                    logging.info(f"配置文件已成功备份为: {config_path}.migrated")
                except Exception as file_e:
                    logging.error(f"备份 config.json 失败: {file_e}")
                db_config = user_config
            except Exception as migrate_e:
                logging.error(f"从 JSON 迁移配置失败: {migrate_e}")
                _save_to_db(cursor, DEFAULT_CONFIG)
                conn.commit()
                db_config = DEFAULT_CONFIG
        else:
            # 初始化默认配置
            logging.info("初始化默认配置到数据库...")
            _save_to_db(cursor, DEFAULT_CONFIG)
            conn.commit()
            db_config = DEFAULT_CONFIG

    conn.close()

    updated = False

    # 去混淆 AI API Key
    ai_cfg = db_config.setdefault("ai_model_config", {})
    for k in ["text_api_key", "vision_api_key"]:
        if k in ai_cfg and ai_cfg[k]:
            ai_cfg[k] = deobfuscate_token(ai_cfg[k])

    # 兼容旧版快捷键字段名
    if "hotkeys" in db_config:
        hk = db_config["hotkeys"]
        if "start_resume" in hk and "start" not in hk:
            hk["start"] = hk.pop("start_resume")
            updated = True
        if "pause" in hk and "toggle_pause" not in hk:
            hk["toggle_pause"] = hk.pop("pause")
            updated = True
        for k, v in DEFAULT_CONFIG["hotkeys"].items():
            if k not in hk:
                hk[k] = v
                updated = True

    # 补全缺失的顶层字段
    for key, value in DEFAULT_CONFIG.items():
        if key not in db_config:
            db_config[key] = value
            updated = True
        elif isinstance(value, dict) and isinstance(db_config.get(key), dict):
            for sub_k, sub_v in value.items():
                user_has_keys = [k for k in db_config[key].keys()]
                if sub_k not in user_has_keys:
                    db_config[key][sub_k] = sub_v
                    updated = True

    if updated:
        logging.info("数据库配置已更新关键字段。")
        save_config(db_config)

    return db_config


def save_config(config_data):
    """
    将配置字典持久化写入 SQLite 数据库。

    Args:
        config_data: 要保存的配置字典
    """
    import sqlite3
    import copy
    from .utils import get_db_path

    db_path = get_db_path()
    try:
        data_to_save = copy.deepcopy(config_data)
        # 混淆 AI API Key
        ai_cfg = data_to_save.setdefault("ai_model_config", {})
        for k in ["text_api_key", "vision_api_key"]:
            if k in ai_cfg and ai_cfg[k]:
                ai_cfg[k] = obfuscate_token(ai_cfg[k])

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        _save_to_db(cursor, data_to_save)
        conn.commit()
        conn.close()
        logging.info("配置已成功保存到数据库中。")
    except Exception as e:
        logging.error(f"保存配置到数据库失败: {e}")
