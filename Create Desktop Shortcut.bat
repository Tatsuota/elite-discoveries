@echo off
REM Put an "Elite Discoveries" launcher on your Desktop pointing at the built exe.
REM Run build_exe.bat first if Elite Discoveries.exe doesn't exist yet.

setlocal enableextensions
cd /d "%~dp0"

set "EXE=%~dp0Elite Discoveries.exe"
set "ICON=%~dp0assets\elite-discoveries.ico"

if not exist "%EXE%" (
    echo Could not find "%EXE%".
    echo Run build_exe.bat first to build the standalone app.
    pause
    goto :eof
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d=[Environment]::GetFolderPath('Desktop');" ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Elite Discoveries.lnk'));" ^
  "$s.TargetPath='%EXE%';" ^
  "$s.WorkingDirectory='%~dp0';" ^
  "$s.IconLocation='%ICON%';" ^
  "$s.Description='Elite Dangerous first-discovery + Codex tracker';" ^
  "$s.Save()"

echo Created Desktop shortcut: "Elite Discoveries"
pause
