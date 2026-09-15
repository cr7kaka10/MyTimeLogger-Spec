# ═══════════════════════════════════════════════════════════════
# MyTimeLogger 桌面端打包脚本
# 流程：UI 构建 → Electron Builder → Portable EXE
# ═══════════════════════════════════════════════════════════════
param(
    [switch]$SkipUiBuild,    # 跳过 UI 构建（已有 ui/dist 时）
    [switch]$NoCopyDesktop   # 不复制到桌面
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# 加载共享配置
. "$PSScriptRoot\config.ps1"

Write-Host ""
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Magenta
Write-Host "  MyTimeLogger 桌面端 EXE 打包" -ForegroundColor Magenta
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Magenta

# ── 第1步：检查 Node.js 环境 ──
Write-Step "检查 Node.js 环境..."
try {
    $nodeVersion = node --version 2>&1
    Write-Ok "Node.js $nodeVersion"
    $npmVersion = npm --version 2>&1
    Write-Ok "npm $npmVersion"
} catch {
    Write-Err "Node.js 未安装，请先安装 Node.js (https://nodejs.org/)"
    exit 1
}

# ── 第2步：安装 core 依赖 ──
Write-Step "安装 core 依赖..."
Push-Location $CORE_DIR
try {
    npm install --prefer-offline 2>&1 | Out-Null
    Exit-OnError "core npm install 失败"
    Write-Ok "core 依赖安装完成"
} finally {
    Pop-Location
}

# ── 第3步：构建 UI ──
if (-not $SkipUiBuild) {
    Write-Step "构建 UI（npm run build）..."
    Push-Location $UI_DIR
    try {
        npm install --prefer-offline 2>&1 | Out-Null
        Exit-OnError "UI npm install 失败"

        npm run build 2>&1
        Exit-OnError "UI 构建失败"
        Write-Ok "UI 构建完成 → ui/dist/"
    } finally {
        Pop-Location
    }
} else {
    Write-Warn "跳过 UI 构建（使用 -SkipUiBuild）"
    if (-not (Test-Path "$UI_DIR\dist\index.html")) {
        Write-Err "ui/dist/index.html 不存在，请先构建 UI 或去掉 -SkipUiBuild"
        exit 1
    }
}

# ── 第4步：安装 Desktop 依赖 ──
Write-Step "安装 Desktop 依赖（含 electron-builder）..."
Push-Location $DESKTOP_DIR
try {
    npm install --prefer-offline 2>&1
    Exit-OnError "Desktop npm install 失败"
    Write-Ok "Desktop 依赖安装完成"
} catch {
    Write-Err "Desktop 依赖安装失败: $_"
    exit 1
} finally {
    Pop-Location
}

# ── 第5步：执行 electron-builder 打包 ──
Write-Step "检查 winCodeSign 缓存与符号链接权限..."
& "$PSScriptRoot\check-wincodesign.ps1"
Exit-OnError "winCodeSign 预检失败"

Write-Step "执行 electron-builder 打包..."
Push-Location $DESKTOP_DIR
try {
    npx electron-builder --win --config 2>&1
    Exit-OnError "electron-builder 打包失败"
    Write-Ok "EXE 打包完成"
} finally {
    Pop-Location
}

# ── 第6步：查找生成的 EXE ──
Write-Step "查找生成的 EXE 文件..."
$exeFiles = Get-ChildItem -Path $EXE_OUTPUT_DIR -Filter "*.exe" -Recurse -ErrorAction SilentlyContinue
if ($exeFiles.Count -eq 0) {
    Write-Err "未找到生成的 EXE 文件"
    exit 1
}

$mainExe = $exeFiles | Sort-Object Length -Descending | Select-Object -First 1
Write-Ok "EXE 路径: $($mainExe.FullName)"
$exeSize = [math]::Round($mainExe.Length / 1MB, 1)
Write-Ok "文件大小: $exeSize MB"

# ── 第7步：复制到桌面 ──
if (-not $NoCopyDesktop) {
    $desktopPath = [Environment]::GetFolderPath("Desktop")
    $destPath = Join-Path $desktopPath $mainExe.Name
    Copy-Item -Path $mainExe.FullName -Destination $destPath -Force
    Write-Ok "已复制到桌面: $destPath"
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  ✅ 桌面端 EXE 打包完成！" -ForegroundColor Green
Write-Host "  📁 输出目录: $EXE_OUTPUT_DIR" -ForegroundColor Green
Write-Host "  📦 文件: $($mainExe.Name) ($exeSize MB)" -ForegroundColor Green
if (-not $NoCopyDesktop) {
Write-Host "  🖥️  桌面: $destPath" -ForegroundColor Green
}
Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Green
