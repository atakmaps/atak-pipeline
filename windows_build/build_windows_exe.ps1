$ErrorActionPreference = "Stop"

$Root = (Get-Location).Path
$BuildRoot = Join-Path $Root "windows_build"
$DistDir = Join-Path $Root "dist"
$BuildDir = Join-Path $Root "build"
$SpecPath = Join-Path $Root "ATAKPipeline.spec"
$Launcher = Join-Path $BuildRoot "windows_launcher.py"

if (-not (Test-Path $Launcher)) {
    throw "Missing launcher: $Launcher"
}

$PythonExe = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Recurse -Filter python.exe -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime |
    Select-Object -Last 1 -ExpandProperty FullName

if (-not $PythonExe) {
    throw "Could not find a real python.exe under $env:LOCALAPPDATA\Programs\Python"
}

$PythonRoot = Split-Path -Parent $PythonExe
$TclDir = Join-Path $PythonRoot "tcl\tcl8.6"
$TkDir  = Join-Path $PythonRoot "tcl\tk8.6"

if (-not (Test-Path $TclDir)) {
    throw "Missing Tcl directory: $TclDir"
}
if (-not (Test-Path $TkDir)) {
    throw "Missing Tk directory: $TkDir"
}

$DataDir = Join-Path $BuildRoot "data"
if (-not (Test-Path (Join-Path $DataDir "us_states.geojson"))) {
    throw "Missing required data file: $DataDir\us_states.geojson"
}
if (-not (Test-Path (Join-Path $DataDir "zoom_estimates_z10_z16.json"))) {
    throw "Missing required data file: $DataDir\zoom_estimates_z10_z16.json"
}

$Dupes = @(
    (Join-Path $Root "atak_downloader_finalbuild.py"),
    (Join-Path $Root "atak_imagery_sqlite_builder_finalbuild.py"),
    (Join-Path $Root "atak_dted_downloader.py")
) | Where-Object { Test-Path $_ }

if ($Dupes.Count -gt 0) {
    throw "Duplicate root runtime scripts found:`n$($Dupes -join "`n")"
}

& $PythonExe --version
& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install pyinstaller requests

$env:TCL_LIBRARY = $TclDir
$env:TK_LIBRARY  = $TkDir

Remove-Item $DistDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $BuildDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $SpecPath -Force -ErrorAction SilentlyContinue

& $PythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name ATAKPipeline `
    --paths "$BuildRoot" `
    --distpath "$DistDir" `
    --workpath "$BuildDir" `
    --hidden-import atak_downloader_finalbuild_win `
    --hidden-import atak_imagery_sqlite_builder_finalbuild_win `
    --hidden-import atak_dted_downloader_win `
    --hidden-import tkinter `
    --hidden-import tkinter.filedialog `
    --hidden-import tkinter.messagebox `
    --hidden-import tkinter.simpledialog `
    --hidden-import tkinter.ttk `
    --hidden-import _tkinter `
    --add-data "${TclDir};_tcl_data" `
    --add-data "${TkDir};_tk_data" `
    --add-data "$DataDir;scripts\data" `
    "$Launcher"

if (-not (Test-Path (Join-Path $DistDir "ATAKPipeline.exe"))) {
    throw "Build did not produce $DistDir\ATAKPipeline.exe"
}

Write-Host ""
Write-Host "Build complete:"
Write-Host (Join-Path $DistDir "ATAKPipeline.exe")
