# -*- coding: utf-8 -*-
"""S3 compatible user report upload."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

@dataclass
class S3BackupConfig:
    enabled: bool = True
    endpoint: str = ""
    bucket: str = "obss3"
    region: str = "us-east-1"
    access_key: str = ""
    secret_key: str = ""
    reports_prefix: str = "reports"

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("secret_key",):
            data.pop(key, None)
        data["secret_configured"] = bool(self.secret_key)
        return data

    def diagnostics(self, username: str | None = None, user_id: int | str | None = None) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "configured": bool(self.endpoint and self.bucket and self.secret_key),
            "endpoint_configured": bool(self.endpoint),
            "bucket": self.bucket,
            "reports_prefix": self.account_reports_prefix(username, user_id) if username and user_id else "",
            "secret_configured": bool(self.secret_key),
            "access_key_configured": bool(self.access_key),
        }

    def reports_target(self) -> "S3Target":
        return self.target()

    def account_reports_prefix(self, username: str | None = None, user_id: int | str | None = None) -> str:
        return build_latest_s3_prefix(self, username, user_id, "reports")

    def target(self) -> "S3Target":
        return S3Target(
            endpoint=self.endpoint,
            bucket=self.bucket,
            region=self.region,
            access_key=self.access_key,
            secret_key=self.secret_key,
        )


@dataclass
class S3Target:
    endpoint: str = ""
    bucket: str = ""
    region: str = ""
    access_key: str = ""
    secret_key: str = ""


class S3ConfigStore:
    def __init__(self, path: str, config_manager=None):
        self.path = Path(path)
        self.config_manager = config_manager

    def _server_config(self):
        if self.config_manager is not None:
            return self.config_manager
        try:
            from .config_manager import server_config
        except (ImportError, ValueError):
            from config_manager import server_config
        return server_config

    def _bool_value(self, value, default=False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        text = str(value).strip().lower()
        if text in ("1", "true", "yes", "on"):
            return True
        if text in ("0", "false", "no", "off", ""):
            return False
        return default

    def _int_value(self, value, default: int) -> int:
        try:
            result = int(value)
            return result if result > 0 else default
        except (TypeError, ValueError):
            return default

    def load(self) -> S3BackupConfig:
        config = self._server_config()
        access_key = config.get_s3("access_key", config.get_s3("access_key_id", ""))
        secret_key = config.get_s3("secret_key", config.get_s3("secret_access_key", ""))
        return S3BackupConfig(
            enabled=self._bool_value(config.get_s3("enabled", True), True),
            endpoint=str(config.get_s3("endpoint", "") or ""),
            bucket=str(config.get_s3("bucket", "obss3") or "obss3"),
            region=str(config.get_s3("region", "us-east-1") or "us-east-1"),
            access_key=str(access_key or ""), secret_key=str(secret_key or ""),
        )

    def _migrate(self, raw: dict[str, Any]) -> dict[str, Any]:
        migrated = dict(raw)
        for field in ("endpoint", "bucket", "region", "access_key", "secret_key"):
            reports_key = f"reports_{field}"
            if not migrated.get(field):
                if raw.get(reports_key):
                    migrated[field] = raw[reports_key]
        if not migrated.get("reports_prefix"):
            migrated["reports_prefix"] = raw.get("reports_prefix") or "reports"
        return migrated

    def save(self, values: dict[str, Any]) -> S3BackupConfig:
        raise ValueError("S3 报告上传配置仅允许通过用户配置接口保存")


def _clean_part(value: str) -> str:
    return str(value or "").strip().strip("/")


def _safe_user_part(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip())
    return clean.strip(".-") or "user"


def build_user_backup_prefix(environment: str, username: str, user_id: int | str, backup_type: str) -> str:
    """Return the current user's S3 prefix isolated by environment and user."""
    env_part = _safe_user_part(environment or "development")
    user_part = f"{_safe_user_part(username)}-{_safe_user_part(str(user_id))}"
    type_part = _safe_user_part(backup_type)
    return _object_key(env_part, "users", user_part, type_part)


def current_s3_environment() -> str:
    import os

    return os.getenv("MYTIMELOGGER_ENVIRONMENT") or os.getenv("MTL_ENVIRONMENT") or "development"


def build_latest_s3_prefix(
    config: S3BackupConfig,
    username: str | None,
    user_id: int | str | None,
    backup_type: str,
) -> str:
    """Return the user-scoped prefix for every new S3 write."""
    if not username or user_id in (None, ""):
        raise ValueError("S3 备份需要当前用户路径上下文")
    return build_user_backup_prefix(current_s3_environment(), username, user_id, backup_type)


def _object_key(*parts: str) -> str:
    clean = [_clean_part(part) for part in parts]
    return "/".join(part for part in clean if part)


def _safe_error(exc: Exception) -> str:
    message = str(exc)
    return message[:500]


def _normalize_endpoint(endpoint: str) -> str:
    value = endpoint.strip().rstrip("/")
    if value and not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return value


class S3Client:
    def __init__(self, target: S3Target):
        if not target.endpoint.strip():
            raise ValueError("S3 endpoint is required")
        if not target.bucket.strip():
            raise ValueError("S3 bucket is required")
        self.target = target
        self.endpoint = _normalize_endpoint(target.endpoint)
        self.client = self._create_client()

    def _create_client(self):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError("boto3 is required for S3 compatible backup") from exc
        return boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            region_name=self.target.region or "us-east-1",
            aws_access_key_id=self.target.access_key or None,
            aws_secret_access_key=self.target.secret_key or None,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )

    def upload_bytes(self, key: str, data: bytes):
        self.client.put_object(Bucket=self.target.bucket, Key=_clean_part(key), Body=data)

    def delete(self, key: str):
        try:
            self.client.delete_object(Bucket=self.target.bucket, Key=_clean_part(key))
        except Exception as exc:
            code = getattr(getattr(exc, "response", {}), "get", lambda *_: {})("Error", {}).get("Code")
            if code not in {"404", "NoSuchKey", "NotFound"}:
                raise

    def list_keys(self, prefix: str) -> list[str]:
        clean_prefix = _clean_part(prefix)
        if clean_prefix:
            clean_prefix = f"{clean_prefix}/"
        keys: list[str] = []
        token = None
        while True:
            kwargs: dict[str, Any] = {"Bucket": self.target.bucket, "Prefix": clean_prefix}
            if token:
                kwargs["ContinuationToken"] = token
            response = self.client.list_objects_v2(**kwargs)
            keys.extend(item["Key"] for item in response.get("Contents", []))
            if not response.get("IsTruncated"):
                return sorted(keys)
            token = response.get("NextContinuationToken")

    def test(self, prefix: str) -> str:
        test_key = _object_key(prefix, "_mytimelogger_s3_test.txt")
        self.upload_bytes(test_key, b"ok")
        self.delete(test_key)
        return f"{self.target.bucket}/{_clean_part(prefix)}".rstrip("/")


class S3BackupService:
    def __init__(
        self,
        config_path: str,
        config_loader: Callable[[], S3BackupConfig] | None = None,
    ):
        self.store = S3ConfigStore(config_path)
        self._config_loader = config_loader
        self.state_path = Path(config_path).with_name("s3_backup_state.json")
        self.state = self._load_state()

    def _load_state(self) -> dict[str, Any]:
        default = {
            "report_last_success": None,
            "report_last_remote_path": None,
            "report_error": None,
        }
        if not self.state_path.exists():
            return default
        return {**default, **json.loads(self.state_path.read_text(encoding="utf-8"))}

    def _save_state(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_config(self) -> S3BackupConfig:
        return self._config_loader() if self._config_loader is not None else self.store.load()

    def upload_report(self, report_path: str, username: str | None = None, user_id: int | str | None = None):
        config = self._load_config()
        self.upload_report_with_config(config, report_path, username=username, user_id=user_id)

    def upload_report_with_config(self, config: S3BackupConfig, report_path: str, username: str | None = None, user_id: int | str | None = None):
        if not config.enabled or not report_path or not Path(report_path).exists():
            return
        try:
            remote = _object_key(config.account_reports_prefix(username, user_id), Path(report_path).name)
            S3Client(config.reports_target()).upload_bytes(remote, Path(report_path).read_bytes())
            Path(report_path).unlink(missing_ok=True)
            self.state.update(
                report_last_success=datetime.now().isoformat(timespec="seconds"),
                report_last_remote_path=remote,
                report_error=None,
            )
        except Exception as exc:
            self.state["report_error"] = _safe_error(exc)
        self._save_state()


WebDavBackupConfig = S3BackupConfig
WebDavTarget = S3Target
WebDavConfigStore = S3ConfigStore
WebDavClient = S3Client
WebDavBackupService = S3BackupService
