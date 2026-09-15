@echo off
chcp 65001 >nul 2>&1
title MyTimeLogger Test Deploy Tool

if /i not "%~1"=="--inner" if not defined MTL_DEPLOY_NO_HOLD (
    cmd /k ""%~f0" --inner"
    exit /b
)

setlocal enabledelayedexpansion
set "TASK_EXIT=0"
set "SSH_ATTEMPTS=0"

:: ===========================================================
:: MyTimeLogger One-Click Test Deploy
:: Double-click to run. Auto: deps install, UI build,
:: Docker server deploy, Desktop EXE packaging.
:: ===========================================================

set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."

echo.
echo   Loading testing private config...
set "MTL_CONFIG_LOAD_OK="
for /f "usebackq delims=" %%L in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%load-private-env.ps1" -Environment testing -RequireComplete -Quiet -EmitCmd 2^>nul`) do %%L
if not defined MTL_CONFIG_LOAD_OK (
    echo.
    echo   [FAIL] Testing private config is missing or incomplete.
    echo   [INFO] Copy deploy\config.example.env to deploy\config.local.env and fill it.
    goto :failed
)
set "VITE_MTL_DEFAULT_ENVIRONMENT=testing"

echo.
echo   Running security preflight...
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%security-preflight.ps1" -Environment testing
if errorlevel 1 (
    echo.
    echo   [FAIL] Security preflight failed.
    goto :failed
)

:: -- Server config --
set "SERVER_HOST=%MTL_SERVER_HOST%"
set "SERVER_PORT=%MTL_SERVER_PORT%"
set "SERVER_USER=%MTL_SERVER_USER%"
set "REMOTE_DIR=%MTL_REMOTE_DIR%"
set "APP_PORT=%MTL_APP_PORT%"
if not defined SERVER_PORT set "SERVER_PORT=22"
set "IMAGE_NAME=mytimelogger-server"
set "CONTAINER_NAME=mytimelogger-sleep-server"
set "IMAGE_TAR=%SCRIPT_DIR%mytimelogger-server.tar"

:menu
cls
echo.
echo   ==================================================
echo   =                                                =
echo   =    MyTimeLogger - Deploy Tool                  =
echo   =                                                =
echo   =    Server: %SERVER_HOST%:%APP_PORT%                  =
echo   =    Environment: testing                         =
echo   =                                                =
echo   ==================================================
echo.
echo     [1]  Deploy ALL (Server + Desktop EXE + Android APK)
echo     [2]  Server only (Docker)
echo     [3]  Desktop EXE only
echo     [4]  Android APK (Debug)
echo     [5]  Backup test server database now (SQLite + S3)
echo     [0]  Exit
echo.
set "choice="
set /p "choice=  Select [0-5]: "
if errorlevel 1 goto :quit
if not defined choice goto :menu

if "%choice%"=="1" goto :deploy_all
if "%choice%"=="2" goto :run_server
if "%choice%"=="3" goto :run_desktop
if "%choice%"=="4" goto :run_android
if "%choice%"=="5" goto :run_server_backup
if "%choice%"=="0" goto :quit
echo   [WARN] Invalid choice, try again.
timeout /t 2 >nul
goto :menu

:: -----------------------------------------------------------
:deploy_all
echo.
echo   ==================================================
echo   Starting full deployment...
echo   ==================================================
call :do_deploy_server
if errorlevel 1 (
    echo.
    echo   [FAIL] Server deploy failed. Desktop build skipped.
    goto :failed
)
call :do_build_desktop
if errorlevel 1 (
    echo.
    echo   [FAIL] Desktop build failed.
    goto :failed
)
echo.
echo   --- [Android] Debug APK build ---
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build-android.ps1"
if errorlevel 1 (
    echo.
    echo   [FAIL] Android APK build failed.
    goto :failed
)
echo.
echo   ==================================================
echo   [OK] Full deployment completed!
echo   ==================================================
goto :finished

:: -----------------------------------------------------------
:run_server
call :do_deploy_server
if errorlevel 1 goto :failed
goto :finished

:run_desktop
call :do_build_desktop
if errorlevel 1 goto :failed
goto :finished

:run_android
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build-android.ps1"
if errorlevel 1 goto :failed
goto :finished

:run_server_backup
call :do_backup_server
if errorlevel 1 goto :failed
goto :finished

:: ===========================================================
::  SERVER DEPLOY
:: ===========================================================
:do_deploy_server
set "SSH_ATTEMPTS=0"
echo.
echo   --- [Server] Step 1/7: Checking Docker ---
docker version >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] Docker Desktop is not running. Please start it first.
    exit /b 1
)
echo   [OK] Docker is ready.

echo.
echo   --- [Server] Step 2/7: Runtime config bootstrap ---
echo   [OK] server\config.json will be created automatically when missing.

echo.
echo   --- [Server] Step 3/7: Building Docker image ---
pushd "%PROJECT_ROOT%"
docker build -t %IMAGE_NAME%:latest -f server/Dockerfile .
if errorlevel 1 (
    popd
    echo   [FAIL] Docker image build failed.
    exit /b 1
)
popd
echo   [OK] Image built successfully.

echo.
echo   --- [Server] Step 4/7: Exporting image (may take 1-2 min) ---
docker save -o "%IMAGE_TAR%" %IMAGE_NAME%:latest
if errorlevel 1 (
    echo   [FAIL] Image export failed.
    exit /b 1
)
echo   [OK] Image exported to: %IMAGE_TAR%

echo.
echo   --- [Server] Step 5/7: Packaging payload locally ---
set "PAYLOAD_TAR=%SCRIPT_DIR%deploy_payload.tar"
if exist "%PAYLOAD_TAR%" del /f /q "%PAYLOAD_TAR%" >nul 2>&1
pushd "%PROJECT_ROOT%"
tar -cf "%PAYLOAD_TAR%" -C deploy mytimelogger-server.tar remote_deploy.sh backup_and_upload_sqlite.sh
popd
if errorlevel 1 (
    echo   [FAIL] Payload packaging failed.
    exit /b 1
)
echo   [OK] Payload packaged.

echo.
echo   --- [Server] Step 6/7: Remote deploy (1 SSH connection) ---
echo   Upload and start container in ONE step.
:retry_ssh
set /a SSH_ATTEMPTS+=1 >nul
echo   [!] Please enter your SSH password for %SERVER_HOST% (attempt !SSH_ATTEMPTS!/3):
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%deploy_stream.ps1" "%PAYLOAD_TAR%" | ssh -p %SERVER_PORT% %SERVER_USER%@%SERVER_HOST% "mkdir -p %REMOTE_DIR% && cd %REMOTE_DIR% && tar -xf - && REMOTE_DIR=%REMOTE_DIR% CONTAINER_NAME=%CONTAINER_NAME% IMAGE_NAME=%IMAGE_NAME% IMAGE_TAG=latest APP_PORT=%APP_PORT% ENVIRONMENT=testing sh remote_deploy.sh"
if errorlevel 1 (
    echo.
    echo   [FAIL] SSH deploy or container startup check failed.
    if !SSH_ATTEMPTS! GEQ 3 (
        echo   [FAIL] SSH retry limit reached.
        exit /b 1
    )
    echo   [INFO] If the password was wrong, press any key and try again.
    echo   [INFO] If the container exited, check the logs printed above.
    echo   [INFO] Manual check: ssh -p %SERVER_PORT% %SERVER_USER%@%SERVER_HOST% "docker ps -a --filter name=%CONTAINER_NAME% && docker logs --tail 80 %CONTAINER_NAME%"
    echo   [?] Press any key to retry the upload/start step, or close window to abort...
    cmd /c pause >nul
    echo.
    goto :retry_ssh
)

echo.
echo   --- [Server] Step 7/8: HTTP verification ---
set "HTTP_FAILED="
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri 'http://%SERVER_HOST%:%APP_PORT%/docs' -UseBasicParsing -TimeoutSec 10; if ($r.StatusCode -eq 200) { exit 0 } else { exit 2 } } catch { exit 1 }"
if errorlevel 1 (
    echo   [FAIL] Container is running, but HTTP verification failed.
    set "HTTP_FAILED=1"
    echo   [INFO] It may still be starting, or the server firewall may block port %APP_PORT%.
    echo   [INFO] Open: http://%SERVER_HOST%:%APP_PORT%/docs
    echo   [INFO] Manual log check: ssh -p %SERVER_PORT% %SERVER_USER%@%SERVER_HOST% "docker logs --tail 80 %CONTAINER_NAME%"
    echo   [INFO] Rollback: ssh -p %SERVER_PORT% %SERVER_USER%@%SERVER_HOST% "docker ps -a --filter name=%CONTAINER_NAME% && docker logs --tail 120 %CONTAINER_NAME%"
    echo   [INFO] If you kept a previous image tag, restart it with: docker run -d --name %CONTAINER_NAME% -p %APP_PORT%:8000 mytimelogger-server:previous
) else (
    echo   [OK] HTTP verification passed: http://%SERVER_HOST%:%APP_PORT%/docs
)

echo.
echo   --- [Server] Step 8/8: Cleanup ---
if exist "%IMAGE_TAR%" del /f /q "%IMAGE_TAR%"
if exist "%PAYLOAD_TAR%" del /f /q "%PAYLOAD_TAR%"
echo   [OK] Temp files cleaned.
if defined HTTP_FAILED exit /b 1

echo.
echo   ==================================================
echo   [OK] Server deployed!
echo   Address:  http://%SERVER_HOST%:%APP_PORT%
echo   API Docs: http://%SERVER_HOST%:%APP_PORT%/docs
echo   Logs:     ssh -p %SERVER_PORT% %SERVER_USER%@%SERVER_HOST% "docker logs --tail 80 %CONTAINER_NAME%"
echo   ==================================================
exit /b 0

:: ===========================================================
::  TEST SERVER DATABASE BACKUP
:: ===========================================================
:do_backup_server
echo.
echo   --- [Backup] Creating SQLite snapshot and uploading to S3 ---
ssh -p %SERVER_PORT% %SERVER_USER%@%SERVER_HOST% "REMOTE_DIR=%REMOTE_DIR% CONTAINER_NAME=%CONTAINER_NAME% BACKUP_RUN_SOURCE=manual %REMOTE_DIR%/backup_and_upload_sqlite.sh"
if errorlevel 1 (
    echo   [FAIL] Backup or S3 upload failed. Local snapshot is retained on the server.
    echo   [INFO] Check: ssh -p %SERVER_PORT% %SERVER_USER%@%SERVER_HOST% "tail -n 80 %REMOTE_DIR%/log/sqlite-backup.log"
    exit /b 1
)
echo   [OK] SQLite backup and S3 upload verified.
exit /b 0

:: ===========================================================
::  DESKTOP EXE BUILD
:: ===========================================================
:do_build_desktop
echo.
echo   --- [Desktop] Step 1/5: Checking Node.js ---
node --version >nul 2>&1
if errorlevel 1 (
    echo   [FAIL] Node.js is not installed.
    exit /b 1
)
echo   [OK] Node.js ready.

echo.
echo   --- [Desktop] Step 2/5: Installing core deps ---
pushd "%PROJECT_ROOT%\core"
call npm install --prefer-offline >nul 2>&1
if errorlevel 1 (
    popd
    echo   [FAIL] core npm install failed.
    exit /b 1
)
popd
echo   [OK] core deps installed.

echo.
echo   --- [Desktop] Step 3/5: Building UI ---
pushd "%PROJECT_ROOT%\ui"
call npm install --prefer-offline >nul 2>&1
call npm run build
if errorlevel 1 (
    popd
    echo   [FAIL] UI build failed.
    exit /b 1
)
popd
echo   [OK] UI built -> ui/dist/

echo.
echo   --- [Desktop] Step 4/5: Installing desktop deps ---
pushd "%PROJECT_ROOT%\desktop"
call npm install --prefer-offline >nul 2>&1
if errorlevel 1 (
    popd
    echo   [FAIL] desktop npm install failed.
    exit /b 1
)
popd
echo   [OK] Desktop deps installed.

echo.
echo   --- [Desktop] Step 5/5: Packaging EXE (may take a while on first run) ---
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%check-wincodesign.ps1"
if errorlevel 1 (
    echo   [FAIL] Desktop packaging preflight failed.
    exit /b 1
)
pushd "%PROJECT_ROOT%\desktop"
call npx electron-builder --win --config
if errorlevel 1 (
    popd
    echo   [FAIL] electron-builder packaging failed.
    exit /b 1
)
popd
echo   [OK] EXE packaged.

:: Find and copy EXE to desktop
echo.
echo   Copying EXE to Desktop...
set "FOUND_EXE="
for /f "delims=" %%f in ('dir /b /o-d /a-d "%PROJECT_ROOT%\desktop\dist\MyTimeLogger-*-portable.exe" 2^>nul') do (
    if not defined FOUND_EXE set "FOUND_EXE=%%f"
)
if not defined FOUND_EXE (
    echo   [FAIL] No portable EXE found in desktop\dist. Check build output.
    exit /b 1
)
copy /y "%PROJECT_ROOT%\desktop\dist\%FOUND_EXE%" "%USERPROFILE%\Desktop\%FOUND_EXE%" >nul
echo   [OK] Copied to Desktop: %FOUND_EXE%

echo.
echo   ==================================================
echo   [OK] Desktop EXE build completed!
echo   Output: %PROJECT_ROOT%\desktop\dist
echo   ==================================================
exit /b 0

:: -----------------------------------------------------------
:failed
set "TASK_EXIT=1"
goto :finished

:finished
echo.
echo   --------------------------------------------------
if "!TASK_EXIT!"=="0" (
    echo   [OK] Task finished. Review the deployment status above.
) else (
    echo   [FAIL] Task failed. Review the deployment status above.
)
echo   Press any key to return to menu, or close this window when finished.
echo   --------------------------------------------------
cmd /c pause >nul
if "!TASK_EXIT!"=="0" goto :menu
endlocal
exit /b 1

:quit
echo   Bye!
endlocal
exit /b 0
