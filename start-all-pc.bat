@echo off
setlocal EnableExtensions
set "ROOT=%~dp0" & cd /d "%~dp0"
set "MTL_STARTUP_RUN_ID=%RANDOM%%RANDOM%%RANDOM%"
echo [start-pc] Checking and bootstrapping local dependencies...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\bootstrap-dev.ps1"
if errorlevel 1 goto :failed
echo [start-pc] Ensuring FastAPI and Vite...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start-local-process.ps1" -Name Server
if errorlevel 1 goto :failed
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start-local-process.ps1" -Name Vite
if errorlevel 1 goto :failed
echo [start-pc] Waiting for local services...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\wait-local-readiness.ps1" -TimeoutSeconds 90
if errorlevel 1 goto :failed
echo [start-pc] Launching Electron...
set "MTL_ELECTRON_USER_DATA_DIR=%ROOT%tests\runtime\electron-user-data"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start-local-process.ps1" -Name Electron
set "ELECTRON_EXIT=%ERRORLEVEL%"
echo [start-pc] Launching WSA Android...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start-wsa-dev.ps1"
set "ANDROID_EXIT=%ERRORLEVEL%"
set "ANDROID_SUMMARY="
for /f "delims=" %%F in ('dir /b /a-d /o-d "%ROOT%tests\runtime\startup-logs\wsa-*.summary.json" 2^>nul') do if not defined ANDROID_SUMMARY set "ANDROID_SUMMARY=%ROOT%tests\runtime\startup-logs\%%F"
if defined ANDROID_SUMMARY powershell.exe -NoProfile -Command "$s=Get-Content -Raw -LiteralPath '%ANDROID_SUMMARY%'|ConvertFrom-Json;if($s.result-eq'success'-and$s.input_ready-eq$true){exit 0};exit 2"
if "%ANDROID_EXIT%"=="0" if errorlevel 1 set "ANDROID_EXIT=2"
if not defined ANDROID_SUMMARY if "%ANDROID_EXIT%"=="0" set "ANDROID_EXIT=2"
if not "%ANDROID_EXIT%"=="0" if defined ANDROID_SUMMARY powershell.exe -NoProfile -Command "$s=Get-Content -Raw -LiteralPath '%ANDROID_SUMMARY%'|ConvertFrom-Json;Write-Output('[start-pc] Android failure: stage={0} category={1} reason={2}'-f$s.stage,$s.error_category,$s.error_reason)"
set "START_EXIT=0"
if not "%ELECTRON_EXIT%"=="0" set "START_EXIT=%ELECTRON_EXIT%"
if not "%ANDROID_EXIT%"=="0" set "START_EXIT=%ANDROID_EXIT%"
echo [start-pc] Local startup summary:
echo [start-pc] Server: ready
echo [start-pc] Vite: ready
if "%ELECTRON_EXIT%"=="0" (echo [start-pc] PC: ready) else (echo [start-pc] PC: failed ^(exit %ELECTRON_EXIT%^))
if "%ANDROID_EXIT%"=="0" (echo [start-pc] Android: ready) else (echo [start-pc] Android: failed ^(exit %ANDROID_EXIT%^))
if defined ANDROID_SUMMARY echo [start-pc] Android summary: %ANDROID_SUMMARY%
if not "%START_EXIT%"=="0" goto :clients_failed
echo [start-pc] Server, PC, and WSA Android are ready.
if /I not "%MTL_START_ALL_NONINTERACTIVE%"=="1" pause
exit /b 0
:clients_failed
echo [start-pc] One or more clients failed; successful clients remain available.
if /I not "%MTL_START_ALL_NONINTERACTIVE%"=="1" pause
exit /b %START_EXIT%
:failed
set "START_EXIT=%ERRORLEVEL%"
echo [start-pc] Startup stopped before client launch.
if /I not "%MTL_START_ALL_NONINTERACTIVE%"=="1" pause
exit /b %START_EXIT%
