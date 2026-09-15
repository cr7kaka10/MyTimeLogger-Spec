# MyTimeLogger deployment settings. Load private env before dot-sourcing this file.
$PROJECT_ROOT = (Resolve-Path "$PSScriptRoot\..").Path

$required = @("MTL_SERVER_HOST", "MTL_SERVER_USER", "MTL_REMOTE_DIR", "MTL_APP_PORT")
$missing = @($required | Where-Object { [string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($_, "Process")) })
if ($missing.Count -gt 0) {
    throw "Missing private deployment settings: $($missing -join ', ')"
}

$SERVER_HOST = $env:MTL_SERVER_HOST
$SERVER_PORT = if ($env:MTL_SERVER_PORT) { [int]$env:MTL_SERVER_PORT } else { 22 }
$SERVER_USER = $env:MTL_SERVER_USER
$REMOTE_DEPLOY_DIR = $env:MTL_REMOTE_DIR
$SERVER_APP_PORT = [int]$env:MTL_APP_PORT

$DOCKER_IMAGE_NAME = "mytimelogger-server"
$DOCKER_IMAGE_TAG = "latest"
$DOCKER_CONTAINER_NAME = "mytimelogger-sleep-server"
$DESKTOP_DIR = "$PROJECT_ROOT\desktop"
$UI_DIR = "$PROJECT_ROOT\ui"
$CORE_DIR = "$PROJECT_ROOT\core"
$EXE_OUTPUT_DIR = "$DESKTOP_DIR\dist"
$DOCKER_IMAGE_TAR = "$PROJECT_ROOT\deploy\mytimelogger-server.tar.gz"

function Write-Step { param([string]$msg) Write-Host "`n▶ $msg" -ForegroundColor Cyan }
function Write-Ok { param([string]$msg) Write-Host "  ✅ $msg" -ForegroundColor Green }
function Write-Warn { param([string]$msg) Write-Host "  ⚠️  $msg" -ForegroundColor Yellow }
function Write-Err { param([string]$msg) Write-Host "  ❌ $msg" -ForegroundColor Red }
function Write-Info { param([string]$msg) Write-Host "  ℹ️  $msg" -ForegroundColor Gray }

function Exit-OnError {
    param([string]$msg)
    if ($LASTEXITCODE -ne 0) { Write-Err $msg; throw $msg }
}
