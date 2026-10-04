@echo off
setlocal
echo ========================================================
echo   StorageRelief (Python) - PyInstaller Release Packager
echo ========================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"

echo.
pause
