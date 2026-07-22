@echo off
rem Creates Desktop + Start Menu shortcuts for the standalone client.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1"
pause
