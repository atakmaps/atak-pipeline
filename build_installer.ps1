Set-Location $PSScriptRoot

if (-not (Test-Path ".\dist\ATAKPipeline.exe")) {
    Write-Error "Missing EXE. Build it first."
    exit 1
}

& "C:\Users\sh_co\AppData\Local\Programs\Inno Setup 6\ISCC.exe" ".\ATAKPipeline_Setup.iss"
