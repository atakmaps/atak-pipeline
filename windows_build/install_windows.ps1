$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$VenvDir = Join-Path $Root ".venv"
$LauncherCmd = Join-Path $Root "run_atak_pipeline.cmd"
$DesktopLauncher = Join-Path ([Environment]::GetFolderPath("Desktop")) "ATAK Imagery Downloader.cmd"

Write-Host "[1/5] Using project root: $Root"

$PythonCmd = Get-Command py -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    $PythonCmd = Get-Command python -ErrorAction SilentlyContinue
}

if (-not $PythonCmd) {
    throw "Python not found."
}

Write-Host "[2/5] Creating virtual environment..."
if ((Get-Command py -ErrorAction SilentlyContinue)) {
    py -3 -m venv $VenvDir
} else {
    python -m venv $VenvDir
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"

Write-Host "[3/5] Installing dependencies..."
& $VenvPython -m pip install --upgrade pip
& $VenvPip install -r (Join-Path $Root "requirements.txt")

Write-Host "[4/5] Creating launcher..."
@"
@echo off
set ROOT=%~dp0

echo === RUNNING IMAGERY DOWNLOADER ===
"%ROOT%.venv\Scripts\python.exe" "%ROOT%scripts\atak_downloader_finalbuild.py"

echo === RUNNING SQLITE BUILDER ===
"%ROOT%.venv\Scripts\python.exe" "%ROOT%scripts\atak_imagery_sqlite_builder_finalbuild.py"

echo === RUNNING DTED DOWNLOADER ===
"%ROOT%.venv\Scripts\python.exe" "%ROOT%scripts\atak_dted_downloader.py"

echo === ALL TASKS COMPLETE ===
pause
"@ | Set-Content -Path $LauncherCmd -Encoding ASCII

Copy-Item $LauncherCmd $DesktopLauncher -Force

Write-Host "[5/5] Done."
Write-Host ""
Write-Host "Launchers created:"
Write-Host "  $LauncherCmd"
Write-Host "  $DesktopLauncher"
Write-Host ""
Write-Host "Starting ATAK Imagery Downloader..."
& $LauncherCmd
