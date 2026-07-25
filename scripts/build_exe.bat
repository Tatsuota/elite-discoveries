@echo off
REM Build a standalone, windowed "Elite Discoveries.exe" (no console window).
REM Output: Elite Discoveries.exe  (double-click to run; no Python needed)

setlocal enableextensions
cd /d "%~dp0.."

REM --- Find a real Python to bootstrap the build virtual environment ---
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY (where python >nul 2>nul && set "PY=python")
if not defined PY goto :nopython

if not exist ".venv\Scripts\python.exe" (
    echo Creating build virtual environment...
    %PY% -m venv .venv || goto :error
)

echo Installing build tools (PyInstaller)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install pyinstaller >nul || goto :error

echo Installing optional native-window backend (pywebview)...
".venv\Scripts\python.exe" -m pip install pywebview >nul || echo   (pywebview install failed - built app will fall back to a Chromium app-mode window)

echo Building standalone executable...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --windowed ^
    --name "Elite Discoveries" ^
    --icon "assets\elite-discoveries.ico" ^
    --add-data "src\web;web" ^
    --distpath "." ^
    src\desktop.py || goto :error

echo.
echo Done. Your standalone app is: Elite Discoveries.exe
echo (Double-click it - no Python needed, no console window.)
pause
goto :eof

:nopython
echo.
echo Could not find Python. Install Python 3.10+ from
echo https://www.python.org/downloads/ (tick "Add python.exe to PATH"), then retry.
pause
goto :eof

:error
echo.
echo Build failed. See the messages above.
pause
