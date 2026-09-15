@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
cd /d "%ROOT%"
set "MTL_STARTUP_RUN_ID=%RANDOM%%RANDOM%%RANDOM%"

echo [start] Checking and bootstrapping local dependencies...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\bootstrap-dev.ps1"
if errorlevel 1 goto :failed

echo [start] Checking Android development prerequisites...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start-android-dev.ps1" -PreflightOnly
if errorlevel 1 goto :failed

echo [start] Ensuring FastAPI and Vite...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start-local-process.ps1" -Name Server
if errorlevel 1 goto :failed
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start-local-process.ps1" -Name Vite
if errorlevel 1 goto :failed

echo [start] Waiting for local services...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\wait-local-readiness.ps1" -TimeoutSeconds 90
if errorlevel 1 goto :failed

echo [start] Launching Electron...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start-local-process.ps1" -Name Electron
set "ELECTRON_EXIT=%ERRORLEVEL%"

echo [start] Launching Android development client...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start-android-dev.ps1"
set "ANDROID_EXIT=%ERRORLEVEL%"
set "ANDROID_SUMMARY="
for /f "delims=" %%F in ('dir /b /a-d /o-d "%ROOT%tests\runtime\startup-logs\android-*.summary.json" 2^>nul') do if not defined ANDROID_SUMMARY set "ANDROID_SUMMARY=%ROOT%tests\runtime\startup-logs\%%F"
if defined ANDROID_SUMMARY powershell.exe -NoProfile -Command "$s=Get-Content -Raw -LiteralPath '%ANDROID_SUMMARY%' | ConvertFrom-Json; if ($s.result -eq 'success' -and $s.input_ready -eq $true) { Write-Output ('[start] Android ready: device={0}; log={1}; summary={2}' -f $s.serial,$s.log_path,'%ANDROID_SUMMARY%'); exit 0 } else { Write-Output ('[start] Android summary: {0}' -f '%ANDROID_SUMMARY%'); exit 2 }"
if "%ANDROID_EXIT%"=="0" if errorlevel 1 set "ANDROID_EXIT=2"
if not defined ANDROID_SUMMARY if "%ANDROID_EXIT%"=="0" set "ANDROID_EXIT=2"
if not "%ANDROID_EXIT%"=="0" if defined ANDROID_SUMMARY powershell.exe -NoProfile -Command "$s=Get-Content -Raw -LiteralPath '%ANDROID_SUMMARY%' | ConvertFrom-Json; Write-Output ('[start] Android failure: stage={0} category={1} reason={2}' -f $s.stage,$s.error_category,$s.error_reason)"

set "START_EXIT=0"
if not "%ELECTRON_EXIT%"=="0" set "START_EXIT=%ELECTRON_EXIT%"
if not "%ANDROID_EXIT%"=="0" set "START_EXIT=%ANDROID_EXIT%"
echo [start] Local startup summary:
echo [start] Server: ready
echo [start] Vite: ready
if "%ELECTRON_EXIT%"=="0" (echo [start] PC: ready) else (echo [start] PC: failed ^(exit %ELECTRON_EXIT%^))
if "%ANDROID_EXIT%"=="0" (echo [start] Android: ready) else (echo [start] Android: failed ^(exit %ANDROID_EXIT%^))
if defined ANDROID_SUMMARY echo [start] Android summary: %ANDROID_SUMMARY%
if not "%START_EXIT%"=="0" goto :clients_failed
echo [start] All local clients are ready.
if /I not "%MTL_START_ALL_NONINTERACTIVE%"=="1" pause
exit /b 0

:clients_failed
echo [start] One or more clients failed; successful clients remain available.
if /I not "%MTL_START_ALL_NONINTERACTIVE%"=="1" pause
exit /b %START_EXIT%

:failed
if not defined START_EXIT set "START_EXIT=%ERRORLEVEL%"
echo [start] Startup stopped. Fix the reported dependency, port, or readiness error and run start-all.bat again.
if /I not "%MTL_START_ALL_NONINTERACTIVE%"=="1" pause
exit /b %START_EXIT%
