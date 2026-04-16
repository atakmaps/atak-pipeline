# Build Windows EXE and Installer

## 1. Refresh Windows source
Use a fresh extracted copy of the repo or pull latest changes.

## 2. Delete duplicate root-level runtime scripts
Before building on Windows, delete these if they exist at repo root:

Remove-Item .\atak_downloader_finalbuild.py, .\atak_imagery_sqlite_builder_finalbuild.py, .\atak_dted_downloader.py -Force -ErrorAction SilentlyContinue

## 3. Build the EXE
Run from the project folder in Windows PowerShell:

pyinstaller --noconfirm --clean --onefile --windowed --name ATAKPipeline --paths scripts --hidden-import atak_downloader_finalbuild --hidden-import atak_imagery_sqlite_builder_finalbuild --hidden-import atak_dted_downloader --hidden-import tkinter --hidden-import _tkinter .\windows_launcher.py

## 4. Build the installer
Use Inno Setup compiler:

C:\Users\sh_co\AppData\Local\Programs\Inno Setup 6\ISCC.exe

## 5. Output
C:\ATAKBuild\atak-pipeline-main\installer-dist\ATAKPipelineSetup.exe
