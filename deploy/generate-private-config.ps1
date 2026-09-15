param(
    [string]$SourceJson = "C:\Users\Server\Downloads\mytimelogger_config.json",
    [string]$OutputDir = $PSScriptRoot
)

$ErrorActionPreference = "Stop"

throw "Deprecated: server runtime config is config.json-only. Use server/config.json or /config instead of generating .env files."

function Write-EnvFile([string]$path, $values) {
    $lines = @("# Generated from local MyTimeLogger config. Do not commit.")
    foreach ($key in $values.Keys) {
        $value = [string]$values[$key]
        $value = $value -replace "`r", "" -replace "`n", "\n"
        $lines += "$key=$value"
    }
    Set-Content -LiteralPath $path -Value $lines -Encoding UTF8
}

function Parse-JsonSetting($settings, [string]$key) {
    $raw = [string]$settings.$key
    if ([string]::IsNullOrWhiteSpace($raw)) { return @{} }
    try { return ($raw | ConvertFrom-Json) } catch { return @{} }
}

function First-Value($object, [string[]]$names, [string]$default = "") {
    foreach ($name in $names) {
        if ($null -ne $object -and $object.PSObject.Properties.Name -contains $name) {
            $value = $object.$name
            if ($null -ne $value -and -not [string]::IsNullOrWhiteSpace([string]$value)) {
                return [string]$value
            }
        }
    }
    return $default
}

if (-not (Test-Path -LiteralPath $SourceJson)) {
    throw "Source config JSON not found: $SourceJson"
}

$config = Get-Content -LiteralPath $SourceJson -Raw -Encoding UTF8 | ConvertFrom-Json
$settings = $config.settings
$profiles = $config.environmentProfiles

foreach ($environment in @("development", "testing", "production")) {
    $profile = $profiles.$environment
    $s3 = Parse-JsonSetting $settings "env_$($environment)_webdav_backup_draft"
    $ticktick = Parse-JsonSetting $settings "ticktick_config"
    $isDev = $environment -eq "development"
    $serverUrl = [string]($profile.serverUrl)
    $serverHostName = ""
    $port = "8000"
    if ($serverUrl -match '^https?://([^:/]+)(?::(\d+))?') {
        $serverHostName = $Matches[1]
        if ($Matches[2]) { $port = $Matches[2] }
    }
    $values = [ordered]@{
        MTL_ENVIRONMENT = $environment
        MTL_SERVER_HOST = $serverHostName
        MTL_SERVER_PORT = "22"
        MTL_SERVER_USER = "root"
        MTL_REMOTE_DIR = "/opt/mytimelogger"
        MTL_APP_PORT = $port
        MTL_SERVER_URL = $serverUrl
        MTL_USERNAME = [string]($profile.username)
        MTL_AUTH_TOKEN = [string]($profile.authToken)
        SLEEP_AUTH_TOKEN = [string]($profile.authToken)
        SERVER_SLEEP_DB_PATH = "/app/server/data/mtl_server.db"
        MYTIMELOGGER_SERVER_MODE = "1"
        SERVER_RUNTIME_OVERWRITE = "0"
        MTL_CONFIG_OVERWRITE = "0"
        TICKTICK_ENABLED = First-Value $ticktick @("enabled") "0"
        TICKTICK_ACCESS_TOKEN = First-Value $settings @("ticktick_access_token", "ticktick_token", "dida_access_token", "dida365_access_token")
        TICKTICK_HOST = First-Value $ticktick @("host") "dida365.com"
        TICKTICK_TIMEOUT_SECONDS = First-Value $ticktick @("timeout_seconds") "15"
        TICKTICK_VERIFY_TLS = First-Value $ticktick @("verify_tls") "0"
        TICKTICK_USERNAME = First-Value $ticktick @("username")
        TICKTICK_PASSWORD = First-Value $ticktick @("password")
        TICKTICK_CLIENT_ID = First-Value $ticktick @("client_id")
        TICKTICK_CLIENT_SECRET = First-Value $ticktick @("client_secret")
        TICKTICK_SYNC_INTERVAL = First-Value $ticktick @("sync_interval") "300"
        S3_BACKUP_ENABLED = ([string]($s3.enabled)).ToLowerInvariant()
        S3_ENDPOINT = First-Value $s3 @("endpoint", "reports_endpoint", "sqlite_endpoint")
        S3_BUCKET = First-Value $s3 @("bucket", "reports_bucket", "sqlite_bucket") "obss3"
        S3_REGION = First-Value $s3 @("region", "reports_region", "sqlite_region") "us-east-1"
        S3_ACCESS_KEY_ID = First-Value $s3 @("access_key", "reports_access_key", "sqlite_access_key")
        S3_SECRET_ACCESS_KEY = First-Value $s3 @("secret_key", "reports_secret_key", "sqlite_secret_key")
        S3_SQLITE_PREFIX = First-Value $s3 @("sqlite_prefix", "database_prefix") "sqlite"
        S3_REPORTS_PREFIX = First-Value $s3 @("reports_prefix") "reports"
        S3_INTERVAL_HOURS = First-Value $s3 @("interval_hours") "6"
        S3_RETENTION_COUNT = First-Value $s3 @("retention_count") "28"
        ATIMELOGGER_ENABLED = [string]($settings.atimelogger_enabled)
        ATIMELOGGER_BASE_URL = "https://app.atimelogger.pro"
        ATIMELOGGER_USERNAME = [string]($settings.atimelogger_username)
        ATIMELOGGER_PASSWORD = [string]($settings.atimelogger_password)
        ATIMELOGGER_TOKEN = [string]($settings.atimelogger_token)
        ATIMELOGGER_REFRESH_TOKEN = [string]($settings.atimelogger_refresh_token)
        ATIMELOGGER_DEVICE_ID = [string]($settings.atimelogger_device_id)
        ATIMELOGGER_TYPE_MAP_JSON = [string]($settings.atimelogger_type_map)
        ATIMELOGGER_UNMATCHED_CATEGORIES_JSON = [string]($settings.atimelogger_unmatched_categories)
        ATIMELOGGER_AUTH_REQUIRED = [string]($settings.atimelogger_auth_required)
        TEXT_BASE_URL = [string]($settings.ai_text_endpoint)
        TEXT_API_KEY = [string]($settings.ai_text_api_key)
        TEXT_MODEL = [string]($settings.ai_text_model)
        VISION_BASE_URL = [string]($settings.ai_vision_endpoint)
        VISION_API_KEY = [string]($settings.ai_vision_api_key)
        VISION_MODEL = [string]($settings.ai_vision_model)
        BACKUP_BASE_URL = ""
        BACKUP_API_KEY = ""
        BACKUP_MODEL = ""
    }
    if (-not $values.TICKTICK_ACCESS_TOKEN) {
        $values.TICKTICK_ACCESS_TOKEN = First-Value $ticktick @("access_token", "token")
    }
    if ($isDev -and -not $values.MTL_SERVER_URL) {
        $values.MTL_SERVER_URL = "http://127.0.0.1:8000"
        $values.MTL_SERVER_HOST = "127.0.0.1"
        $values.MTL_APP_PORT = "8000"
    }
    $path = Join-Path $OutputDir "config.$environment.local.env"
    Write-EnvFile $path $values
    Write-Host "Generated $path"
}
