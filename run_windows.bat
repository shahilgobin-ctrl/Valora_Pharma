@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
set "projectExitCode=%ERRORLEVEL%"
if not "%projectExitCode%"=="0" (
    echo.
    echo The server stopped or could not start. Read the message above.
    pause
)
exit /b %projectExitCode%
