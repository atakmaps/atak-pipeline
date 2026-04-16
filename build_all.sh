#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VERSION="$(tr -d '[:space:]' < VERSION)"
WINDOWS_COMMANDS_FILE="$ROOT/windows_rebuild_commands.ps1"

echo
echo "========================================"
echo "ATAK PIPELINE SMART REBUILD ASSISTANT"
echo "========================================"
echo "Repo root: $ROOT"
echo "Version : $VERSION"
echo

if [ ! -f "$ROOT/scripts/repo_self_check.py" ]; then
  echo "ERROR: Missing scripts/repo_self_check.py"
  exit 1
fi

echo "[1/7] Running repo self-check..."
python3 "$ROOT/scripts/repo_self_check.py"

echo
echo "[2/7] Git status..."
git status --short || true

echo
echo "[3/7] Fetching origin..."
git fetch origin

LOCAL_HEAD="$(git rev-parse HEAD)"
REMOTE_HEAD="$(git rev-parse origin/main)"

echo "Local HEAD : $LOCAL_HEAD"
echo "Origin/main: $REMOTE_HEAD"

if [ "$LOCAL_HEAD" != "$REMOTE_HEAD" ]; then
  echo
  echo "WARNING: Local repo does not match origin/main."
  echo "Push or sync before rebuilding Windows."
else
  echo
  echo "Repo is synced with origin/main."
fi

echo
echo "[4/7] Checking important files..."
required_files=(
  "run_atak_pipeline.sh"
  "install_linux.sh"
  "install_windows.cmd"
  "windows_launcher.py"
  "ATAKPipeline_Setup.iss"
  "build_installer.ps1"
  "requirements-windows-build.txt"
  "scripts/atak_downloader_finalbuild.py"
  "scripts/atak_imagery_sqlite_builder_finalbuild.py"
  "scripts/atak_dted_downloader.py"
  "build_linux_release.sh"
  "bump_version.sh"
  "prepare_release.sh"
)

missing=0
for f in "${required_files[@]}"; do
  if [ ! -f "$ROOT/$f" ]; then
    echo "MISSING: $f"
    missing=1
  fi
done

if [ "$missing" -ne 0 ]; then
  echo
  echo "ERROR: Required files are missing."
  exit 1
fi

echo "All required files are present."

echo
echo "[5/7] Checking for dangerous duplicate root-level runtime scripts..."
duplicates=0
for f in atak_downloader_finalbuild.py atak_imagery_sqlite_builder_finalbuild.py atak_dted_downloader.py; do
  if [ -f "$ROOT/$f" ]; then
    echo "DANGEROUS DUPLICATE: $f"
    duplicates=1
  fi
done

if [ "$duplicates" -ne 0 ]; then
  echo
  echo "ERROR: Remove duplicate root-level runtime scripts before rebuilding."
  exit 1
fi

echo "No dangerous duplicate root-level runtime scripts found."

echo
echo "[6/7] Building Linux release asset..."
"$ROOT/build_linux_release.sh"

echo
echo "[7/7] Writing Windows rebuild commands..."
cat > "$WINDOWS_COMMANDS_FILE" <<'POWERSHELL'
Remove-Item .\atak_downloader_finalbuild.py, .\atak_imagery_sqlite_builder_finalbuild.py, .\atak_dted_downloader.py -Force -ErrorAction SilentlyContinue

$env:TCL_LIBRARY="C:\Users\sh_co\AppData\Local\Programs\Python\Python313\tcl\tcl8.6"
$env:TK_LIBRARY="C:\Users\sh_co\AppData\Local\Programs\Python\Python313\tcl\tk8.6"

if (Test-Path .\build) { Remove-Item .\build -Recurse -Force }
if (Test-Path .\dist) { Remove-Item .\dist -Recurse -Force }
if (Test-Path .\ATAKPipeline.spec) { Remove-Item .\ATAKPipeline.spec -Force }

pyinstaller --noconfirm --clean --onefile --windowed --name ATAKPipeline `
  --paths scripts `
  --hidden-import atak_downloader_finalbuild `
  --hidden-import atak_imagery_sqlite_builder_finalbuild `
  --hidden-import atak_dted_downloader `
  --hidden-import tkinter `
  --hidden-import tkinter.filedialog `
  --hidden-import tkinter.messagebox `
  --hidden-import tkinter.simpledialog `
  --hidden-import tkinter.ttk `
  --hidden-import _tkinter `
  --add-data "C:\Users\sh_co\AppData\Local\Programs\Python\Python313\tcl\tcl8.6;_tcl_data" `
  --add-data "C:\Users\sh_co\AppData\Local\Programs\Python\Python313\tcl\tk8.6;_tk_data" `
  .\windows_launcher.py

& "C:\Users\sh_co\AppData\Local\Programs\Inno Setup 6\ISCC.exe" "C:\ATAKBuild\atak-pipeline-main\ATAKPipeline_Setup.iss"
POWERSHELL

echo "Windows rebuild commands written to:"
echo "  $WINDOWS_COMMANDS_FILE"

if command -v xclip >/dev/null 2>&1; then
  xclip -selection clipboard < "$WINDOWS_COMMANDS_FILE" && echo "Copied Windows rebuild commands to clipboard with xclip."
elif command -v xsel >/dev/null 2>&1; then
  xsel --clipboard --input < "$WINDOWS_COMMANDS_FILE" && echo "Copied Windows rebuild commands to clipboard with xsel."
else
  echo "Clipboard utility not found (xclip/xsel). Commands saved to file only."
fi

echo
echo "========================================"
echo "NEXT STEPS"
echo "========================================"
echo "1. On Windows, run the commands in:"
echo "   $WINDOWS_COMMANDS_FILE"
echo
echo "2. Expected Windows installer output:"
echo "   C:\\ATAKBuild\\atak-pipeline-main\\installer-dist\\ATAKPipelineSetup.exe"
echo
echo "3. Release assets should be:"
echo "   $ROOT/dist/atak-linux-install.zip"
echo "   ATAKPipelineSetup.exe"
echo
echo "DONE"
