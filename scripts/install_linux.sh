#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT/.venv"
LAUNCHER="$ROOT/run_atak_pipeline.sh"
GUI_LAUNCHER="$ROOT/launch_atak_pipeline_gui.sh"
APP_DIR="$HOME/.local/share/applications"
APP_FILE="$APP_DIR/atak-pipeline.desktop"
DESKTOP_FILE="$HOME/Desktop/atak-pipeline.desktop"

echo "[1/7] Using project root: $ROOT"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python3 not found. Attempting install..."

    if command -v apt >/dev/null 2>&1; then
        sudo apt update
        sudo apt install -y python3 python3-venv python3-pip python3-tk zenity
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y python3 python3-pip python3-tkinter zenity
    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -Sy --noconfirm python python-pip tk zenity
    else
        echo "Unsupported distro. Please install python3 manually."
        exit 1
    fi
fi

echo "[2/7] Creating virtual environment..."
rm -rf "$VENV_DIR"
python3 -m venv "$VENV_DIR"

echo "[3/7] Installing dependencies..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$ROOT/requirements.txt"

echo "[4/7] Creating pipeline launcher..."
cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT="$ROOT"
exec "\$ROOT/.venv/bin/python" "\$ROOT/scripts/atak_downloader_finalbuild.py"
LAUNCHER_EOF
chmod +x "$LAUNCHER"

echo "[5/7] Creating GUI launcher wrapper..."
cat > "$GUI_LAUNCHER" <<GUI_LAUNCHER_EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT="$ROOT"
cd "\$ROOT"
exec "\$ROOT/.venv/bin/python" "\$ROOT/scripts/atak_downloader_finalbuild.py"
GUI_LAUNCHER_EOF
chmod +x "$GUI_LAUNCHER"

echo "[6/7] Creating desktop launcher..."
mkdir -p "$APP_DIR"

cat > "$APP_FILE" <<DESKTOP_EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=ATAK Pipeline
Comment=Build ATAK imagery and DTED packages
Exec=$GUI_LAUNCHER
Path=$ROOT
Terminal=false
Categories=Utility;
StartupNotify=true
DESKTOP_EOF

chmod +x "$APP_FILE"

if [ -d "$HOME/Desktop" ]; then
    cp "$APP_FILE" "$DESKTOP_FILE"
    chmod +x "$DESKTOP_FILE"
fi

echo "[7/7] Done."
echo
echo "Created:"
echo "  $LAUNCHER"
echo "  $GUI_LAUNCHER"
echo "  $APP_FILE"
if [ -d "$HOME/Desktop" ]; then
    echo "  $DESKTOP_FILE"
fi
echo
echo "Launching ATAK Pipeline..."
nohup "$GUI_LAUNCHER" >/dev/null 2>&1 &
