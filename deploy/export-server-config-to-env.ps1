param(
    [string]$DbPath = (Join-Path (Split-Path -Parent $PSScriptRoot) "server\data\mtl_server.db"),
    [string]$OutputDir = $PSScriptRoot,
    [string[]]$Environments = @("development", "testing", "production")
)

$ErrorActionPreference = "Stop"

throw "Deprecated: server runtime config is config.json-only. Use server/config.json or /config instead of exporting .env files."

if (-not (Test-Path -LiteralPath $DbPath)) {
    throw "Server config database not found: $DbPath"
}

$envList = $Environments -join ","

@'
import json
import os
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1])
output_dir = Path(sys.argv[2])
environments = [item for item in sys.argv[3].split(",") if item]

ORDER = [
    "MTL_ENVIRONMENT", "MTL_SERVER_HOST", "MTL_SERVER_PORT", "MTL_SERVER_USER", "MTL_REMOTE_DIR",
    "MTL_APP_PORT", "MTL_SERVER_URL", "MTL_USERNAME", "MTL_AUTH_TOKEN", "SLEEP_AUTH_TOKEN",
    "SERVER_SLEEP_DB_PATH", "MYTIMELOGGER_SERVER_MODE", "SERVER_RUNTIME_OVERWRITE", "MTL_CONFIG_OVERWRITE",
    "TICKTICK_ENABLED", "TICKTICK_ACCESS_TOKEN", "TICKTICK_HOST", "TICKTICK_TIMEOUT_SECONDS",
    "TICKTICK_VERIFY_TLS", "TICKTICK_USERNAME", "TICKTICK_PASSWORD", "TICKTICK_CLIENT_ID",
    "TICKTICK_CLIENT_SECRET", "TICKTICK_SYNC_INTERVAL",
    "S3_BACKUP_ENABLED", "S3_ENDPOINT", "S3_BUCKET", "S3_REGION", "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY", "S3_SQLITE_PREFIX", "S3_REPORTS_PREFIX", "S3_INTERVAL_HOURS", "S3_RETENTION_COUNT",
    "ATIMELOGGER_ENABLED", "ATIMELOGGER_BASE_URL", "ATIMELOGGER_USERNAME", "ATIMELOGGER_PASSWORD",
    "ATIMELOGGER_TOKEN", "ATIMELOGGER_REFRESH_TOKEN", "ATIMELOGGER_DEVICE_ID",
    "ATIMELOGGER_TYPE_MAP_JSON", "ATIMELOGGER_UNMATCHED_CATEGORIES_JSON", "ATIMELOGGER_AUTH_REQUIRED",
    "TEXT_BASE_URL", "TEXT_API_KEY", "TEXT_MODEL", "VISION_BASE_URL", "VISION_API_KEY", "VISION_MODEL",
    "BACKUP_BASE_URL", "BACKUP_API_KEY", "BACKUP_MODEL",
]

DEFAULTS = {
    "MTL_SERVER_PORT": "22",
    "MTL_SERVER_USER": "root",
    "MTL_REMOTE_DIR": "/opt/mytimelogger",
    "MTL_APP_PORT": "8000",
    "SERVER_SLEEP_DB_PATH": "/app/server/data/mtl_server.db",
    "MYTIMELOGGER_SERVER_MODE": "1",
    "SERVER_RUNTIME_OVERWRITE": "0",
    "MTL_CONFIG_OVERWRITE": "0",
    "TICKTICK_HOST": "dida365.com",
    "TICKTICK_TIMEOUT_SECONDS": "15",
    "TICKTICK_VERIFY_TLS": "0",
    "TICKTICK_SYNC_INTERVAL": "300",
    "S3_BUCKET": "obss3",
    "S3_REGION": "us-east-1",
    "S3_SQLITE_PREFIX": "sqlite",
    "S3_REPORTS_PREFIX": "reports",
    "S3_INTERVAL_HOURS": "6",
    "S3_RETENTION_COUNT": "28",
    "ATIMELOGGER_BASE_URL": "https://app.atimelogger.pro",
    "ATIMELOGGER_TYPE_MAP_JSON": "{}",
    "ATIMELOGGER_UNMATCHED_CATEGORIES_JSON": "[]",
}

def parse_env(path):
    values = dict(DEFAULTS)
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            item = line.strip()
            if not item or item.startswith("#") or "=" not in item:
                continue
            key, value = item.split("=", 1)
            values[key.strip()] = value
    return values

def write_env(path, values):
    keys = list(ORDER)
    for key in values:
        if key not in keys:
            keys.append(key)
    lines = ["# Generated from local MyTimeLogger config. Do not commit."]
    for key in keys:
        value = str(values.get(key, ""))
        value = value.replace("\r", "").replace("\n", "\\n")
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def as_json(value, fallback):
    if not value:
        return fallback
    try:
        data = json.loads(value)
        return data if isinstance(data, type(fallback)) else fallback
    except Exception:
        return fallback

def scalar(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
try:
    user = conn.execute("SELECT id, username FROM users ORDER BY id LIMIT 1").fetchone()
    user_id = int(user["id"]) if user else 1
    rows = conn.execute(
        "SELECT key, value FROM server_system_config WHERE user_id=?",
        (user_id,),
    ).fetchall()
    settings = {row["key"]: row["value"] for row in rows}
finally:
    conn.close()

ticktick = as_json(settings.get("ticktick_config"), {})
atimelogger = as_json(settings.get("atimelogger_config"), {})
ai = as_json(settings.get("ai_model_config"), {})

for environment in environments:
    path = output_dir / f"config.{environment}.local.env"
    values = parse_env(path)
    values["MTL_ENVIRONMENT"] = environment

    server_url = settings.get(f"env_{environment}_server_url") or values.get("MTL_SERVER_URL", "")
    username = settings.get(f"env_{environment}_username") or values.get("MTL_USERNAME", "")
    auth_token = settings.get(f"env_{environment}_auth_token") or values.get("MTL_AUTH_TOKEN", "")
    values["MTL_SERVER_URL"] = server_url
    values["MTL_USERNAME"] = username
    values["MTL_AUTH_TOKEN"] = auth_token
    values["SLEEP_AUTH_TOKEN"] = values.get("SLEEP_AUTH_TOKEN") or auth_token

    if server_url.startswith("http://") or server_url.startswith("https://"):
        host_part = server_url.split("://", 1)[1].split("/", 1)[0]
        if ":" in host_part:
            host, port = host_part.rsplit(":", 1)
            values["MTL_SERVER_HOST"] = values.get("MTL_SERVER_HOST") or host
            values["MTL_APP_PORT"] = values.get("MTL_APP_PORT") or port
        else:
            values["MTL_SERVER_HOST"] = values.get("MTL_SERVER_HOST") or host_part

    values["TICKTICK_ENABLED"] = scalar(ticktick.get("enabled", bool(ticktick.get("access_token"))))
    values["TICKTICK_ACCESS_TOKEN"] = scalar(ticktick.get("access_token") or ticktick.get("token") or values.get("TICKTICK_ACCESS_TOKEN"))
    values["TICKTICK_HOST"] = scalar(ticktick.get("host") or values.get("TICKTICK_HOST") or "dida365.com")
    values["TICKTICK_TIMEOUT_SECONDS"] = scalar(ticktick.get("timeout_seconds") or values.get("TICKTICK_TIMEOUT_SECONDS") or "15")
    values["TICKTICK_VERIFY_TLS"] = scalar(ticktick.get("verify_tls", values.get("TICKTICK_VERIFY_TLS") or "0"))
    values["TICKTICK_USERNAME"] = scalar(ticktick.get("username") or values.get("TICKTICK_USERNAME"))
    values["TICKTICK_PASSWORD"] = scalar(ticktick.get("password") or values.get("TICKTICK_PASSWORD"))
    values["TICKTICK_CLIENT_ID"] = scalar(ticktick.get("client_id") or values.get("TICKTICK_CLIENT_ID"))
    values["TICKTICK_CLIENT_SECRET"] = scalar(ticktick.get("client_secret") or values.get("TICKTICK_CLIENT_SECRET"))
    values["TICKTICK_SYNC_INTERVAL"] = scalar(ticktick.get("sync_interval") or values.get("TICKTICK_SYNC_INTERVAL") or "300")

    s3 = as_json(settings.get(f"env_{environment}_webdav_backup_draft"), {})
    if s3:
        values["S3_BACKUP_ENABLED"] = scalar(s3.get("enabled", values.get("S3_BACKUP_ENABLED")))
        values["S3_ENDPOINT"] = scalar(s3.get("endpoint") or s3.get("reports_endpoint") or s3.get("sqlite_endpoint") or values.get("S3_ENDPOINT"))
        values["S3_BUCKET"] = scalar(s3.get("bucket") or s3.get("reports_bucket") or s3.get("sqlite_bucket") or values.get("S3_BUCKET"))
        values["S3_REGION"] = scalar(s3.get("region") or s3.get("reports_region") or s3.get("sqlite_region") or values.get("S3_REGION"))
        values["S3_ACCESS_KEY_ID"] = scalar(s3.get("access_key") or s3.get("reports_access_key") or s3.get("sqlite_access_key") or values.get("S3_ACCESS_KEY_ID"))
        values["S3_SECRET_ACCESS_KEY"] = scalar(s3.get("secret_key") or s3.get("reports_secret_key") or s3.get("sqlite_secret_key") or values.get("S3_SECRET_ACCESS_KEY"))
        values["S3_SQLITE_PREFIX"] = scalar(s3.get("sqlite_prefix") or s3.get("database_prefix") or values.get("S3_SQLITE_PREFIX"))
        values["S3_REPORTS_PREFIX"] = scalar(s3.get("reports_prefix") or values.get("S3_REPORTS_PREFIX"))
        values["S3_INTERVAL_HOURS"] = scalar(s3.get("interval_hours") or values.get("S3_INTERVAL_HOURS"))
        values["S3_RETENTION_COUNT"] = scalar(s3.get("retention_count") or values.get("S3_RETENTION_COUNT"))

    values["ATIMELOGGER_ENABLED"] = scalar(atimelogger.get("enabled", values.get("ATIMELOGGER_ENABLED")))
    values["ATIMELOGGER_USERNAME"] = scalar(atimelogger.get("username") or values.get("ATIMELOGGER_USERNAME"))
    values["ATIMELOGGER_PASSWORD"] = scalar(atimelogger.get("password") or values.get("ATIMELOGGER_PASSWORD"))
    values["ATIMELOGGER_TOKEN"] = scalar(atimelogger.get("token") or values.get("ATIMELOGGER_TOKEN"))
    values["ATIMELOGGER_REFRESH_TOKEN"] = scalar(atimelogger.get("refresh_token") or values.get("ATIMELOGGER_REFRESH_TOKEN"))
    values["ATIMELOGGER_DEVICE_ID"] = scalar(atimelogger.get("device_id") or values.get("ATIMELOGGER_DEVICE_ID"))
    values["ATIMELOGGER_TYPE_MAP_JSON"] = scalar(atimelogger.get("type_map") or values.get("ATIMELOGGER_TYPE_MAP_JSON") or {})
    values["ATIMELOGGER_UNMATCHED_CATEGORIES_JSON"] = scalar(atimelogger.get("unmatched_categories") or values.get("ATIMELOGGER_UNMATCHED_CATEGORIES_JSON") or [])
    values["ATIMELOGGER_AUTH_REQUIRED"] = scalar(atimelogger.get("auth_required", values.get("ATIMELOGGER_AUTH_REQUIRED") or "0"))

    values["TEXT_BASE_URL"] = scalar(ai.get("text_base_url") or values.get("TEXT_BASE_URL"))
    values["TEXT_API_KEY"] = scalar(ai.get("text_api_key") or values.get("TEXT_API_KEY"))
    values["TEXT_MODEL"] = scalar(ai.get("text_model") or values.get("TEXT_MODEL"))
    values["VISION_BASE_URL"] = scalar(ai.get("vision_base_url") or values.get("VISION_BASE_URL"))
    values["VISION_API_KEY"] = scalar(ai.get("vision_api_key") or values.get("VISION_API_KEY"))
    values["VISION_MODEL"] = scalar(ai.get("vision_model") or values.get("VISION_MODEL"))

    write_env(path, values)
    print(f"Updated {path}")
'@ | python - $DbPath $OutputDir $envList
