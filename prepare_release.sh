#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VERSION="$(tr -d '[:space:]' < VERSION)"
RELEASE_TAG="v${VERSION}"
OUTDIR="$ROOT/dist"
WINDOWS_COMMANDS_FILE="$ROOT/windows_rebuild_commands.ps1"
RELEASE_NOTES_FILE="$ROOT/release_notes_v${VERSION}.md"

echo
echo "========================================"
echo "PREPARE ATAK RELEASE"
echo "========================================"
echo "Version: $VERSION"
echo "Tag    : $RELEASE_TAG"
echo

if [ ! -x "$ROOT/scripts/repo_self_check.py" ]; then
  echo "ERROR: scripts/repo_self_check.py is missing or not executable"
  exit 1
fi

echo "[1/5] Running repo self-check..."
python3 "$ROOT/scripts/repo_self_check.py"

echo
echo "[2/5] Checking git sync..."
git fetch origin
LOCAL_HEAD="$(git rev-parse HEAD)"
REMOTE_HEAD="$(git rev-parse origin/main)"

echo "Local HEAD : $LOCAL_HEAD"
echo "Origin/main: $REMOTE_HEAD"

if [ "$LOCAL_HEAD" != "$REMOTE_HEAD" ]; then
  echo
  echo "WARNING: Local repo does not match origin/main."
  echo "Push or sync before releasing."
fi

echo
echo "[3/5] Building Linux release asset..."
"$ROOT/build_linux_release.sh"

echo
echo "[4/5] Writing Windows rebuild commands..."
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
echo "[5/5] Writing release notes template..."
cat > "$RELEASE_NOTES_FILE" <<EOF2
# ATAK Pipeline ${RELEASE_TAG}

Release title:
ATAK Pipeline ${RELEASE_TAG}

## Assets
- atak-linux-install.zip
- ATAKPipelineSetup.exe

## Notes
- Linux pipeline updated and tested
- Windows EXE rebuilt from current source
- Windows installer rebuilt from current EXE
EOF2

echo "Release notes template written to:"
echo "  $RELEASE_NOTES_FILE"

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
echo "   $OUTDIR/atak-linux-install.zip"
echo "   ATAKPipelineSetup.exe"
echo
echo "DONE"
