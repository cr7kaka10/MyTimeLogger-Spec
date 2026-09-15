@echo off
setlocal
cd /d %~dp0
cd ..

echo ====================================
echo   MyTimeLogger Build Script
echo ====================================
echo.

echo [1/2] Cleaning old build files (build, dist)...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

echo [2/2] Starting PyInstaller build...
python -m PyInstaller --noconfirm scripts\my_time_logger.spec

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo.
echo ====================================
echo   SUCCESS!
echo   Binary: .\dist\MyTimeLogger.exe
echo ====================================
pause
