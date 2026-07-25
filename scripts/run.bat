@echo off
REM Run Elite Discoveries from source (no build). Opens its own window.
REM Creates a local virtual environment on first run.

setlocal enableextensions
cd /d "%~dp0.."

if exist ".venv\Scripts\pythonw.exe" goto :run

set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY goto :nopython

echo First run: creating virtual environment and installing dependencies...
%PY% -m venv .venv || goto :error
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r scripts\requirements.txt || goto :error

:run
start "" ".venv\Scripts\pythonw.exe" "src\desktop.py"
goto :eof

:nopython
echo Could not find Python. Install Python 3.10+ from https://www.python.org/downloads/ and retry.
pause
goto :eof

:error
echo.
echo Setup failed. See the messages above.
pause
