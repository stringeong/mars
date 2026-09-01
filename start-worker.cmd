@echo off
setlocal
chcp 65001 >nul

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-worker-windows.ps1" %*
set "MARS_EXIT_CODE=%ERRORLEVEL%"

if not "%MARS_NO_PAUSE%"=="1" (
    echo.
    pause
)
exit /b %MARS_EXIT_CODE%
