@echo off
REM Put an "Elite Discoveries" shortcut on your Desktop.
REM Prefers the built app (Elite Discoveries.exe); otherwise points at
REM the source launcher (scripts\run.bat). Build with scripts\build_exe.bat
REM for the .exe.

setlocal enableextensions
cd /d "%~dp0"

set "EXE=%~dp0Elite Discoveries.exe"
set "ICON=%~dp0assets\elite-discoveries.ico"
set "TARGET="
set "WORKDIR=%~dp0"

if exist "%EXE%" (
    set "TARGET=%EXE%"
    set "WORKDIR=%~dp0"
) else (
    set "TARGET=%~dp0scripts\run.bat"
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d=[Environment]::GetFolderPath('Desktop');" ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Elite Discoveries.lnk'));" ^
  "$s.TargetPath='%TARGET%';" ^
  "$s.WorkingDirectory='%WORKDIR%';" ^
  "if (Test-Path '%ICON%') { $s.IconLocation='%ICON%' }" ^
  "$s.Description='Elite Dangerous first-discovery + Codex tracker';" ^
  "$s.Save()"

echo Created Desktop shortcut: "Elite Discoveries"  ->  %TARGET%
pause
