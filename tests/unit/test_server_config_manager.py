# -*- coding: utf-8 -*-
import pytest
from pathlib import Path

from server.config_manager import ConfigManager


@pytest.fixture(autouse=True)
def clear_config_env(monkeypatch):
    for env_key in (
        "TICKTICK_ACCESS_TOKEN",
        "S3_ENDPOINT",
        "TEXT_API_KEY",
        "VISION_MODEL",
        "MTL_CORS_ORIGINS",
        "MTL_LOGIN_FAILURE_LIMIT",
    ):
        monkeypatch.delenv(env_key, raising=False)


def test_config_manager_creates_chinese_jsonc_template(tmp_path):
    path = tmp_path / "config.json"
    manager = ConfigManager(str(path), legacy_path=str(tmp_path / "missing.jsonc"))

    raw = path.read_text(encoding="utf-8")
    assert "MyTimeLogger 服务端统一配置文件" in raw
    assert "用户外部服务密钥" in raw
    assert '"ticktick"' not in raw
    assert '"s3_backup"' not in raw
    assert '"ai_model"' not in raw
    assert "backup_model" not in raw
    assert '"runtime"' in raw
    assert '"security"' in raw
    assert '"cors"' in raw
    assert manager.get_security("login_failure_limit") == 5
    assert "http://127.0.0.1:5173" in manager.get_cors("allowed_origins")
    assert "capacitor://localhost" in manager.get_cors("allowed_origins")
    assert "https://localhost" in manager.get_cors("allowed_origins")


def test_config_manager_preserves_required_capacitor_origins_with_custom_allowlist(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"cors":{"allowed_origins":["https://custom.example"]}}', encoding="utf-8")

    manager = ConfigManager(str(path))

    assert manager.get_cors("allowed_origins") == [
        "https://custom.example",
        "capacitor://localhost",
        "https://localhost",
    ]
    assert "https://evil.example" not in manager.get_cors("allowed_origins")


def test_config_manager_does_not_depend_on_default_legacy_file(tmp_path):
    path = tmp_path / "config.json"
    manager = ConfigManager(str(path))

    assert path.exists()
    assert manager.legacy_path is None
    assert manager.get_ai("vision_model") is None


def test_config_manager_migrates_legacy_jsonc(tmp_path):
    legacy = tmp_path / "server_config.jsonc"
    legacy.write_text(
        """
        {
          // legacy comment
          "ticktick": {"access_token": "tick-token", "verify_tls": true},
          "s3_backup": {"endpoint": "https://s3.example", "access_key_id": "ak"},
          "ai_model": {"text_api_key": "text-key", "vision_model": "vision-x", "backup_model": "backup-x"}
        }
        """,
        encoding="utf-8",
    )

    manager = ConfigManager(str(tmp_path / "config.json"), legacy_path=str(legacy))

    assert manager.get_ticktick("access_token") is None
    assert manager.get_s3("endpoint") is None
    assert manager.get_ai("text_api_key") is None
    assert manager.legacy_service_sections()["ticktick"]["present"] is True
    assert manager.legacy_service_sections()["s3_backup"]["present"] is True
    assert manager.legacy_service_sections()["ai_model"]["present"] is True


def test_save_raw_text_reloads_config(tmp_path):
    manager = ConfigManager(str(tmp_path / "config.json"), legacy_path=str(tmp_path / "missing.jsonc"))

    manager.save_raw_text('{"ai_model": {"text_model": "glm-test"}, "runtime": {"environment": "testing"}}')

    assert manager.get_ai("text_model") is None
    assert manager.get_runtime("environment") == "testing"
    assert "backup_model" not in (tmp_path / "config.json").read_text(encoding="utf-8")


def test_invalid_jsonc_does_not_overwrite_existing_config(tmp_path):
    path = tmp_path / "config.json"
    manager = ConfigManager(str(path), legacy_path=str(tmp_path / "missing.jsonc"))
    original = path.read_text(encoding="utf-8")

    with pytest.raises(Exception):
        manager.save_raw_text('{"ticktick": ')

    assert path.read_text(encoding="utf-8") == original


def test_config_manager_ignores_existing_server_env_file(tmp_path):
    path = tmp_path / "config.json"
    env_path = tmp_path / ".env"
    path.write_text(
        """
        {
          "ticktick": {"access_token": "", "host": "dida365.com"},
          "s3_backup": {"endpoint": "", "bucket": ""},
          "ai_model": {"text_api_key": "", "vision_model": "glm-4v-flash"}
        }
        """,
        encoding="utf-8",
    )
    env_path.write_text(
        "\n".join([
            "TICKTICK_ACCESS_TOKEN=tick-from-env",
            "S3_ENDPOINT=https://s3.env.example",
            "S3_BUCKET=env-bucket",
            "TEXT_API_KEY=text-from-env",
            "VISION_MODEL=vision-from-env",
        ]),
        encoding="utf-8",
    )

    manager = ConfigManager(
        str(path),
        legacy_path=str(tmp_path / "missing.jsonc"),
        env_file_path=str(env_path),
    )

    assert manager.get_ticktick("access_token", "") == ""
    assert manager.get_s3("endpoint", "") == ""
    assert manager.get_s3("bucket", "") == ""
    assert manager.get_ai("text_api_key", "") == ""
    assert manager.get_ai("vision_model") is None
    assert "tick-from-env" not in path.read_text(encoding="utf-8")


def test_config_manager_process_env_does_not_override_manual_config(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text('{"ticktick": {"access_token": "manual-token"}}', encoding="utf-8")
    monkeypatch.setenv("TICKTICK_ACCESS_TOKEN", "env-token")

    manager = ConfigManager(
        str(path),
        legacy_path=str(tmp_path / "missing.jsonc"),
    )

    assert manager.get_ticktick("access_token") is None
    assert "env-token" not in path.read_text(encoding="utf-8")


def test_login_page_allows_config_next_redirect():
    login_html = (Path(__file__).resolve().parents[2] / "server" / "templates" / "login.html").read_text(encoding="utf-8")
    config_html = (Path(__file__).resolve().parents[2] / "server" / "templates" / "config.html").read_text(encoding="utf-8")

    assert "'/config'" in login_html
    assert "nextTarget()" in login_html
    assert "reauth=1" in config_html
    assert 'localStorage.removeItem("mtl_token")' in config_html
    assert 'localStorage.getItem("mtl_auth_token")' in config_html
    assert "无法连接服务器配置接口" in config_html
    assert "configApiUrl" in config_html
    assert 'id="accountIdentity"' in config_html
    assert "当前账号：加载中" in config_html
    assert "data?.user?.username" in config_html
    assert "validateImportSnapshot(payload)" in config_html
    assert "serviceConfigSchema" in config_html
    assert "s3Ready" in config_html


def test_server_sleep_page_preserves_upload_success_feedback():
    sleep_html = (Path(__file__).resolve().parents[2] / "server" / "templates" / "index.html").read_text(encoding="utf-8")

    assert "图片已收到，正在校验日期" in sleep_html
    assert "需要分析时，请点击“睡眠分析”或“完整分析”" in sleep_html
    assert "fetchByDate(nextDate, {keepStatus: true})" in sleep_html
    assert "if (!keepStatus) setStatus(`${date} 暂无云端睡眠数据`, '')" in sleep_html
    assert "setStatus(message, 'error')" in sleep_html
