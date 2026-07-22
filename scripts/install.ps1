# ============================================================
#  Elite Discoveries - Installer
#  Creates Desktop + Start Menu shortcuts that launch the
#  standalone desktop client (own window, own icon), runnable
#  without opening a terminal.
# ============================================================

$dir     = Split-Path -Parent $PSScriptRoot
$client  = Join-Path $dir 'src\desktop.py'
$ico     = Join-Path $dir 'assets\elite-discoveries.ico'

# --- Find pythonw.exe (no-console) ; fall back to python.exe ---
function Find-Python {
    foreach ($name in 'pythonw', 'python') {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}
$python = Find-Python
if (-not $python) {
    Write-Host "Python 3 was not found on your PATH." -ForegroundColor Red
    Write-Host "Install it from https://www.python.org/downloads/ and run this again." -ForegroundColor Red
    return
}

# Generate the icon if it's missing.
if (-not (Test-Path $ico)) {
    try { & $python (Join-Path $dir 'src\make_icon.py') | Out-Null } catch {}
}

# --- Create the shortcut(s) ---
$shell = New-Object -ComObject WScript.Shell

function New-AppShortcut($path) {
    $s = $shell.CreateShortcut($path)
    $s.TargetPath       = $python
    $s.Arguments        = '"' + $client + '"'
    $s.WorkingDirectory = $dir
    if (Test-Path $ico) { $s.IconLocation = $ico }
    $s.Description      = 'Elite Dangerous first-discovery tracker'
    $s.WindowStyle      = 1
    $s.Save()
}

$desktopLnk = Join-Path ([Environment]::GetFolderPath('Desktop'))  'Elite Discoveries.lnk'
$startLnk   = Join-Path ([Environment]::GetFolderPath('Programs')) 'Elite Discoveries.lnk'
New-AppShortcut $desktopLnk
New-AppShortcut $startLnk

Write-Host ""
Write-Host "  Elite Discoveries installed!" -ForegroundColor Green
Write-Host "  Launcher : $python"
Write-Host "  Desktop shortcut    : $desktopLnk"
Write-Host "  Start Menu shortcut : $startLnk"
Write-Host ""
Write-Host "  Double-click 'Elite Discoveries' to start. To pin it to the taskbar," -ForegroundColor Cyan
Write-Host "  open it, then right-click its taskbar icon > Pin to taskbar."
Write-Host ""
