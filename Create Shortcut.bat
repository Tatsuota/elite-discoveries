@echo off
REM Put "Elite Discoveries" shortcuts on your Desktop and in the Start Menu.
REM Prefers the built app (Elite Discoveries.exe); otherwise points at the
REM source launcher (scripts\run.bat). Build the exe with scripts\build_exe.bat.

setlocal enableextensions
cd /d "%~dp0"

set "EXE=%~dp0Elite Discoveries.exe"
set "ICON=%~dp0assets\elite-discoveries.ico"
set "WORKDIR=%~dp0"

if exist "%EXE%" (
    set "TARGET=%EXE%"
) else (
    set "TARGET=%~dp0scripts\run.bat"
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$sh = New-Object -ComObject WScript.Shell;" ^
  "foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {" ^
  "  $s = $sh.CreateShortcut((Join-Path $dir 'Elite Discoveries.lnk'));" ^
  "  $s.TargetPath='%TARGET%';" ^
  "  $s.WorkingDirectory='%WORKDIR%';" ^
  "  if (Test-Path '%ICON%') { $s.IconLocation='%ICON%' }" ^
  "  $s.Description='Elite Dangerous first-discovery + Codex tracker';" ^
  "  $s.Save();" ^
  "}"

echo Created "Elite Discoveries" shortcuts on the Desktop and in the Start Menu.
echo Target: %TARGET%
pause
