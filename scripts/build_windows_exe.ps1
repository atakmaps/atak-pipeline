$ErrorActionPreference = "Stop"

$Root = (Get-Location).Path
$DistDir = Join-Path $Root "dist"
$BuildDir = Join-Path $Root "build"
$SpecDir = Join-Path $BuildDir "spec"
$ScriptsDir = Join-Path $Root "scripts"
$Launcher = Join-Path $ScriptsDir "windows_pipeline_app.py"

$PythonExe = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Recurse -Filter python.exe -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime |
    Select-Object -Last 1 -ExpandProperty FullName

if (-not $PythonExe) {
    throw "Could not find a real python.exe under $env:LOCALAPPDATA\Programs\Python"
}

& $PythonExe --version
& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install pyinstaller requests

Remove-Item $DistDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $BuildDir -Recurse -Force -ErrorAction SilentlyContinue

New-Item -ItemType Directory -Force -Path $DistDir | Out-Null
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
New-Item -ItemType Directory -Force -Path $SpecDir | Out-Null

& $PythonExe -m PyInstaller `
    --noconfirm `
    --onefile `
    --windowed `
    --name ATAKPipeline `
    --distpath "$DistDir" `
    --workpath "$BuildDir" `
    --specpath "$SpecDir" `
    --add-data "${ScriptsDir};scripts" `
    "$Launcher"

if (-not (Test-Path (Join-Path $DistDir "ATAKPipeline.exe"))) {
    throw "Build did not produce $DistDir\ATAKPipeline.exe"
}

Write-Host ""
Write-Host "Build complete:"
Write-Host (Join-Path $DistDir "ATAKPipeline.exe")
