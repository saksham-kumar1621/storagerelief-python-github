@echo off
setlocal
echo ===================================================
echo   StorageRelief (Python Edition) - Launcher
echo ===================================================
echo.

cd /d "%~dp0"
python main.py %*

if %errorlevel% neq 0 (
    echo.
    echo Application exited with code %errorlevel%.
    pause
)
