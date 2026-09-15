# ═══════════════════════════════════════════════════════════════
# MyTimeLogger 测试环境一键部署 - 总入口
# 用法：右键 → 使用 PowerShell 运行
# ═══════════════════════════════════════════════════════════════

param(
    [ValidateSet("development", "testing", "production")]
    [string]$Environment = "testing",
    [string]$ConfigPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

. "$PSScriptRoot\load-private-env.ps1" -Environment $Environment -ConfigPath $ConfigPath -RequireComplete -Quiet
$env:VITE_MTL_DEFAULT_ENVIRONMENT = $Environment
. "$PSScriptRoot\config.ps1"

function Show-Menu {
    Clear-Host
    Write-Host ""
    Write-Host "  ╔═══════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "  ║                                               ║" -ForegroundColor Cyan
    Write-Host "  ║   MyTimeLogger 测试环境一键部署工具           ║" -ForegroundColor Cyan
    Write-Host "  ║                                               ║" -ForegroundColor Cyan
    Write-Host "  ║   服务器: $SERVER_HOST`:$SERVER_APP_PORT" -ForegroundColor Cyan -NoNewline
    # 补齐空格对齐右边框
    $padding = 47 - ("   服务器: ${SERVER_HOST}:${SERVER_APP_PORT}").Length
    Write-Host (" " * [Math]::Max($padding, 1) + "║") -ForegroundColor Cyan
    Write-Host "  ║                                               ║" -ForegroundColor Cyan
    Write-Host "  ╠═══════════════════════════════════════════════╣" -ForegroundColor Cyan
    Write-Host "  ║                                               ║" -ForegroundColor Cyan
    Write-Host "  ║   [1]  🚀 全部部署（服务端 + 桌面 EXE）      ║" -ForegroundColor White
    Write-Host "  ║                                               ║" -ForegroundColor Cyan
    Write-Host "  ║   [2]  🐳 仅部署服务端（Docker）             ║" -ForegroundColor White
    Write-Host "  ║                                               ║" -ForegroundColor Cyan
    Write-Host "  ║   [3]  💻 仅打包桌面 EXE                     ║" -ForegroundColor White
    Write-Host "  ║                                               ║" -ForegroundColor Cyan
    Write-Host "  ║   [4]  📱 打包 Android APK（开发中）         ║" -ForegroundColor DarkGray
    Write-Host "  ║                                               ║" -ForegroundColor Cyan
    Write-Host "  ║   [0]  ❌ 退出                                ║" -ForegroundColor White
    Write-Host "  ║                                               ║" -ForegroundColor Cyan
    Write-Host "  ╚═══════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Invoke-ServerDeploy {
    Write-Host ""
    Write-Host "  开始服务端部署..." -ForegroundColor Cyan
    Write-Host "  ─────────────────────────────────────────────" -ForegroundColor DarkGray
    & "$PSScriptRoot\deploy-server.ps1" -Environment $Environment -ConfigPath $ConfigPath -PrivateConfigLoaded
    if ($LASTEXITCODE -ne 0) {
        throw "服务端部署脚本返回失败代码 $LASTEXITCODE"
    }
}

function Invoke-DesktopBuild {
    Write-Host ""
    Write-Host "  开始桌面端 EXE 打包..." -ForegroundColor Cyan
    Write-Host "  ─────────────────────────────────────────────" -ForegroundColor DarkGray
    & "$PSScriptRoot\build-desktop.ps1"
    if ($LASTEXITCODE -ne 0) {
        throw "桌面端打包脚本返回失败代码 $LASTEXITCODE"
    }
}

function Invoke-AndroidBuild {
    & "$PSScriptRoot\build-android.ps1"
    if ($LASTEXITCODE -ne 0) {
        throw "Android 打包脚本返回失败代码 $LASTEXITCODE"
    }
}

# ── 记录开始时间 ──
$startTime = Get-Date

# ── 主循环 ──
do {
    Show-Menu
    $choice = Read-Host "  请选择操作"

    switch ($choice) {
        "1" {
            try {
                $startTime = Get-Date
                Write-Host ""
                Write-Host "  ══════════════════════════════════════════" -ForegroundColor Magenta
                Write-Host "  全部部署开始" -ForegroundColor Magenta
                Write-Host "  ══════════════════════════════════════════" -ForegroundColor Magenta

                # 先部署服务端
                Invoke-ServerDeploy

                # 再打包桌面端
                Invoke-DesktopBuild

                $elapsed = (Get-Date) - $startTime
                Write-Host ""
                Write-Host "  ══════════════════════════════════════════" -ForegroundColor Green
                Write-Host "  ✅ 全部部署完成！总耗时: $([math]::Round($elapsed.TotalMinutes, 1)) 分钟" -ForegroundColor Green
                Write-Host "  ══════════════════════════════════════════" -ForegroundColor Green
            } catch {
                Write-Host ""
                Write-Err "全部部署失败：$($_.Exception.Message)"
                Write-Info "窗口会保留，方便复制上方错误信息。"
            }
            Write-Host ""
            Read-Host "  按 Enter 返回菜单"
        }
        "2" {
            try {
                $startTime = Get-Date
                Invoke-ServerDeploy
                $elapsed = (Get-Date) - $startTime
                Write-Host ""
                Write-Host "  总耗时: $([math]::Round($elapsed.TotalMinutes, 1)) 分钟" -ForegroundColor Gray
            } catch {
                Write-Host ""
                Write-Err "服务端部署失败：$($_.Exception.Message)"
                Write-Info "窗口会保留，方便复制上方错误信息。"
            }
            Write-Host ""
            Read-Host "  按 Enter 返回菜单"
        }
        "3" {
            try {
                $startTime = Get-Date
                Invoke-DesktopBuild
                $elapsed = (Get-Date) - $startTime
                Write-Host ""
                Write-Host "  总耗时: $([math]::Round($elapsed.TotalMinutes, 1)) 分钟" -ForegroundColor Gray
            } catch {
                Write-Host ""
                Write-Err "桌面端打包失败：$($_.Exception.Message)"
                Write-Info "窗口会保留，方便复制上方错误信息。"
            }
            Write-Host ""
            Read-Host "  按 Enter 返回菜单"
        }
        "4" {
            Invoke-AndroidBuild
            Read-Host "  按 Enter 返回菜单"
        }
        "0" {
            Write-Host "  再见！" -ForegroundColor Cyan
        }
        default {
            Write-Host "  无效选择，请重试" -ForegroundColor Red
            Start-Sleep -Seconds 1
        }
    }
} while ($choice -ne "0")
