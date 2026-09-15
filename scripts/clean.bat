@echo off
setlocal
cd /d %~dp0
cd ..

echo ====================================
echo   MyTimeLogger Cleanup Script
echo ====================================
echo.

echo Cleaning up build and dist directories...
if exist "build" (
    echo    - Removing build/
    rmdir /s /q "build"
)
if exist "dist" (
    echo    - Removing dist/
    rmdir /s /q "dist"
)

echo.
echo Cleanup complete.
pause
