import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

CAPACITOR_APP_ORIGINS = ("capacitor://localhost", "https://localhost")

# 匹配 // 注释或 /* */ 注释（简单正则处理）
COMMENT_RE = re.compile(r'^\s*//.*?$|(?<=\s)//.*?$|/\*.*?\*/', re.MULTILINE | re.DOTALL)

DEFAULT_CONFIG_JSONC = """{
  // ==========================================
  // MyTimeLogger 服务端统一配置文件
  // 文件位置：server/config.json
  // 这里只保存服务端运行配置；用户外部服务密钥请在登录后的“我的配置”里填写
  // 保存后会自动重载；不要把真实密钥提交到 Git
  // ==========================================

  "runtime": {
    "environment": "development", // 当前服务环境：development/testing/production
    "port": 8000, // 直接运行 server.py 时监听端口
    "log_dir": "log", // 服务端日志目录；相对路径基于 server 目录
    "reports_dir": "/app/reports", // 容器内睡眠报告输出目录
    "huawei_health_data_dir": "/app/server_data/huawei_health_data",
    "generate_skill_config": false // 是否生成报告技能运行配置
  },

  "security": {
    "login_failure_limit": 5, // 登录失败锁定阈值
    "login_lock_seconds": 300, // 登录失败锁定时长（秒）
    "legacy_auth_token": ""
  },

  "cors": {
    "allowed_origins": [
      "http://localhost:5173",
      "http://127.0.0.1:5173",
      "http://localhost:3000",
      "http://127.0.0.1:3000",
      "capacitor://localhost",
      "https://localhost"
    ]
  }
}
"""


def _truthy(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on"):
        return True
    if text in ("0", "false", "no", "off", ""):
        return False
    return default


def _coerce_like(value, sample):
    if value in (None, ""):
        return value
    if isinstance(sample, bool):
        return _truthy(value, sample)
    if isinstance(sample, int) and not isinstance(sample, bool):
        try:
            return int(value)
        except (TypeError, ValueError):
            return sample
    if isinstance(sample, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return sample
    return value


class ConfigManager:
    CONFIG_SECTIONS = ("runtime", "security", "cors")

    def __init__(self, config_path: str = "config.json", legacy_path: str | None = None, env_file_path: str | None = None):
        self.config_path = Path(config_path)
        if not self.config_path.is_absolute():
            self.config_path = Path(__file__).parent / self.config_path
        self.legacy_path = Path(legacy_path) if legacy_path else None
        if self.legacy_path is not None and not self.legacy_path.is_absolute():
            self.legacy_path = Path(__file__).parent / self.legacy_path
        self.config_data = {}
        self._defaults = self.parse_jsonc(DEFAULT_CONFIG_JSONC)
        self.ensure_config_file()
        self.backfill_config_file()
        self.reload()

    def ensure_config_file(self):
        if not self.config_path.exists():
            logger.info("Creating default server config file at %s", self.config_path)
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            initial_data = {}
            if self.legacy_path is not None and self.legacy_path.exists():
                try:
                    initial_data = self.parse_jsonc(self.legacy_path.read_text(encoding="utf-8"))
                    logger.info("Migrated explicit legacy config into server/config.json")
                except Exception as exc:
                    logger.warning("Explicit legacy config migration skipped: %s", exc)
            merged = self.merge_defaults(initial_data)
            initial_text = self.render_config_text(merged) if initial_data else DEFAULT_CONFIG_JSONC
            self.config_path.write_text(initial_text, encoding="utf-8")

    def reload(self):
        try:
            raw_text = self.config_path.read_text(encoding="utf-8")
            self.config_data = self.merge_defaults(self.parse_jsonc(raw_text))
            logger.info("Server configuration reloaded successfully.")
        except Exception as e:
            logger.error(f"Failed to reload config: {e}")

    def parse_jsonc(self, text: str) -> dict:
        # 移除注释
        json_str = COMMENT_RE.sub('', text)
        return json.loads(json_str)

    def merge_defaults(self, data: dict | None) -> dict:
        merged = json.loads(json.dumps(self._defaults, ensure_ascii=False))
        for section in self.CONFIG_SECTIONS:
            values = (data or {}).get(section) or {}
            if isinstance(values, dict):
                if isinstance(merged.get(section), dict):
                    merged[section].update(values)
                else:
                    merged[section] = values
        origins = merged.setdefault("cors", {}).get("allowed_origins", [])
        if isinstance(origins, list):
            merged["cors"]["allowed_origins"] = list(dict.fromkeys([
                *(str(origin).strip() for origin in origins if str(origin).strip()),
                *CAPACITOR_APP_ORIGINS,
            ]))
        return merged

    def _apply_section_fallbacks(self, target: dict, source: dict) -> tuple[dict, bool]:
        changed = False
        for section in self.CONFIG_SECTIONS:
            source_values = (source or {}).get(section) or {}
            if not isinstance(source_values, dict):
                continue
            target_section = target.setdefault(section, {})
            default_section = self._defaults.get(section, {})
            for key, source_value in source_values.items():
                if key not in default_section or source_value in (None, ""):
                    continue
                current = target_section.get(key)
                if current in (None, "", default_section.get(key)):
                    target_section[key] = source_value
                    changed = True
        return target, changed

    def backfill_config_file(self):
        if not self.config_path.exists():
            return
        try:
            parsed = self.parse_jsonc(self.config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Server config backfill skipped because config.json is invalid: %s", exc)
            return
        merged = self.merge_defaults(parsed)
        changed = False
        if self.legacy_path is not None and self.legacy_path.exists():
            try:
                legacy_data = self.parse_jsonc(self.legacy_path.read_text(encoding="utf-8"))
                merged, legacy_changed = self._apply_section_fallbacks(merged, legacy_data)
                changed = changed or legacy_changed
            except Exception as exc:
                logger.warning("Explicit legacy config backfill skipped: %s", exc)
        if changed:
            self.config_path.write_text(self.render_config_text(merged), encoding="utf-8")
            logger.info("Backfilled missing server/config.json values from explicit legacy config without logging secrets.")

    def render_config_text(self, data: dict) -> str:
        return json.dumps(self.merge_defaults(data), ensure_ascii=False, indent=2)

    def get_raw_text(self) -> str:
        self.ensure_config_file()
        return self.config_path.read_text(encoding="utf-8")

    def legacy_service_sections(self) -> dict:
        return {key: {"present": True} for key in self.legacy_service_config_values()}

    def legacy_service_config_values(self) -> dict:
        self.ensure_config_file()
        try:
            parsed = self.parse_jsonc(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            parsed = {}
        legacy: dict[str, dict] = {}
        parsed_sources = [parsed]
        if self.legacy_path is not None and self.legacy_path.exists():
            try:
                parsed_sources.append(self.parse_jsonc(self.legacy_path.read_text(encoding="utf-8")))
            except Exception:
                pass
        for source in parsed_sources:
            for section in ("ticktick", "s3_backup", "ai_model"):
                values = source.get(section)
                if isinstance(values, dict) and any(str(value or "").strip() for value in values.values()):
                    legacy[section] = values
            security = source.get("security")
            if isinstance(security, dict) and any(security.get(key) for key in ("owner_account", "owner_user_id")):
                legacy["owner_config"] = {key: security.get(key) for key in ("owner_account", "owner_user_id")}
        return legacy

    def save_raw_text(self, text: str):
        # 先验证是否能解析
        parsed = self.parse_jsonc(text)
        merged = self.merge_defaults(parsed)
        self.config_path.write_text(self.render_config_text(merged), encoding="utf-8")
        self.config_data = merged

    def update_section(self, section: str, values: dict):
        if section not in self._defaults:
            raise ValueError(f"Unknown config section: {section}")
        data = self.merge_defaults(self.config_data)
        clean = {key: value for key, value in values.items() if key in self._defaults[section]}
        data[section].update(clean)
        self.config_path.write_text(self.render_config_text(data), encoding="utf-8")
        self.config_data = self.merge_defaults(data)

    def _get_section_value(self, section: str, key: str, default=None):
        val = self.config_data.get(section, {}).get(key)
        if val in (None, ""):
            return default
        sample = self._defaults.get(section, {}).get(key, default)
        return _coerce_like(val, sample)

    # 统一从 server/config.json 获取配置。
    def get_ticktick(self, key: str, default=None):
        return self._get_section_value("ticktick", key, default)

    def get_s3(self, key: str, default=None):
        return self._get_section_value("s3_backup", key, default)

    def get_ai(self, key: str, default=None):
        return self._get_section_value("ai_model", key, default)

    def get_runtime(self, key: str, default=None):
        return self._get_section_value("runtime", key, default)

    def get_security(self, key: str, default=None):
        return self._get_section_value("security", key, default)

    def get_cors(self, key: str, default=None):
        value = self.config_data.get("cors", {}).get(key)
        return default if value in (None, "") else value

server_config = ConfigManager("config.json")
