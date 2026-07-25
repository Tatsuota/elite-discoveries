@echo off
title Elite Discoveries
cd /d "%~dp0"
echo Starting Elite Discoveries...
echo This window scans your Elite Dangerous journals and serves the app.
echo Leave it open while using the tracker. Close it (or press Ctrl+C) to stop.
echo.
python src\server.py
if errorlevel 1 (
  echo.
  echo Could not start. Make sure Python 3 is installed and on your PATH.
  pause
)
