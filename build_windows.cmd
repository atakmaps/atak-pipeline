@echo off
setlocal
cd /d "%~dp0"

if not exist .venv-build (
    py -3 -m venv .venv-build
    if errorlevel 1 goto :fail
)

call .venv-build\Scripts\activate.bat
if errorlevel 1 goto :fail

python -m pip install --upgrade pip
if errorlevel 1 goto :fail

pip install -r requirements-windows-build.txt
if errorlevel 1 goto :fail

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist ATAKPipeline.spec del /q ATAKPipeline.spec

pyinstaller --noconfirm --clean --onefile --windowed --name ATAKPipeline ^
  --paths scripts ^
  --hidden-import atak_downloader_finalbuild ^
  --hidden-import atak_imagery_sqlite_builder_finalbuild ^
  --hidden-import atak_dted_downloader ^
  --hidden-import tkinter ^
  --hidden-import tkinter.filedialog ^
  --hidden-import tkinter.messagebox ^
  --hidden-import tkinter.simpledialog ^
  --hidden-import tkinter.ttk ^
  windows_launcher.py

if errorlevel 1 goto :fail

echo.
echo ==================================================
echo BUILD COMPLETE
echo EXE:
echo %CD%\dist\ATAKPipeline.exe
echo ==================================================
exit /b 0

:fail
echo.
echo BUILD FAILED
exit /b 1
