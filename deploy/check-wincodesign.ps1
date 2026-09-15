Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$cacheRoot = if ($env:MTL_WINCODESIGN_CACHE) {
    $env:MTL_WINCODESIGN_CACHE
} else {
    Join-Path $env:LOCALAPPDATA "electron-builder\Cache\winCodeSign"
}
$archiveName = "winCodeSign-2.6.0.7z"

function Write-InfoLine { param([string]$Text) Write-Host "  [INFO] $Text" }
function Write-OkLine { param([string]$Text) Write-Host "  [OK] $Text" -ForegroundColor Green }
function Write-WarnLine { param([string]$Text) Write-Host "  [WARN] $Text" -ForegroundColor Yellow }
function Write-FailLine { param([string]$Text) Write-Host "  [FAIL] $Text" -ForegroundColor Red }

function Test-SymlinkPrivilege {
    $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("mtl-symlink-check-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tempDir | Out-Null
    $target = Join-Path $tempDir "target.txt"
    $link = Join-Path $tempDir "link.txt"
    try {
        Set-Content -LiteralPath $target -Value "ok" -Encoding ASCII
        New-Item -ItemType SymbolicLink -Path $link -Target $target -ErrorAction Stop | Out-Null
        return $true
    } catch {
        return $false
    } finally {
        Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Get-UsableWinCodeSignCache {
    if (-not (Test-Path -LiteralPath $cacheRoot)) {
        return @()
    }

    Get-ChildItem -LiteralPath $cacheRoot -Directory -ErrorAction SilentlyContinue | Where-Object {
        (Test-Path -LiteralPath (Join-Path $_.FullName "rcedit-x64.exe")) -and
        (Test-Path -LiteralPath (Join-Path $_.FullName "windows-10\x64\signtool.exe")) -and
        (Test-Path -LiteralPath (Join-Path $_.FullName "darwin\10.12\lib\libcrypto.dylib")) -and
        (Test-Path -LiteralPath (Join-Path $_.FullName "darwin\10.12\lib\libssl.dylib"))
    }
}

Write-Host ""
Write-Host "  --- [Desktop] Preflight: winCodeSign cache and symlink permission ---"
Write-InfoLine "Cache path: $cacheRoot"
Write-InfoLine "Archive: $archiveName"

$canCreateSymlink = Test-SymlinkPrivilege
$usableCaches = @(Get-UsableWinCodeSignCache)
if ($usableCaches.Count -gt 0) {
    $latest = $usableCaches | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Write-OkLine "winCodeSign 缓存可用: $($latest.FullName)"
} elseif (-not (Test-Path -LiteralPath $cacheRoot)) {
    Write-FailLine "winCodeSign 缓存缺失。"
} else {
    Write-FailLine "winCodeSign 缓存不完整。"
}

if ($canCreateSymlink) {
    Write-OkLine "符号链接权限可用。"
} else {
    Write-FailLine "当前 Windows 会话没有符号链接权限。"
    Write-InfoLine "请用管理员权限运行 deploy.bat，或开启 Windows 开发者模式后重新打开终端。"
    Write-InfoLine "重复下载 $archiveName 不能解决权限问题；electron-builder 解压时仍会失败。"
    exit 1
}

if ($usableCaches.Count -eq 0) {
    Write-InfoLine "electron-builder 只有在缓存完整时才会复用；缓存缺失/不完整会触发重新下载 $archiveName。"
    Write-InfoLine "请先在具备符号链接权限且可访问 GitHub 的环境运行一次桌面打包，或手动预置完整缓存。"
    Write-InfoLine "缓存目录准备好后，重新运行 deploy.bat。"
    exit 1
}

exit 0
