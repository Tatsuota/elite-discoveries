@echo off
rem ============================================================
rem  Elite Discoveries - Standalone Desktop Client
rem  Starts the local server and opens the app in its own
rem  window. Close the window to stop everything.
rem ============================================================
cd /d "%~dp0"

rem Prefer pythonw (no console window); fall back to python.
where pythonw >nul 2>&1 && (
    start "" pythonw "%~dp0src\desktop.py"
    exit /b
)
where python >nul 2>&1 && (
    start "" python "%~dp0src\desktop.py"
    exit /b
)

echo Python 3 was not found on your PATH.
echo Install it from https://www.python.org/downloads/ and try again.
pause
