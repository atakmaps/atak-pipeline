#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT/.venv"
LAUNCHER="$ROOT/run_atak_pipeline.sh"
DESKTOP_FILE_NAME="ATAK Pipeline.desktop"
APP_NAME="ATAK Pipeline"

echo "[1/8] Using project root: $ROOT"

install_apt() {
    sudo apt update
    sudo apt install -y "$@"
}

install_dnf() {
    sudo dnf install -y "$@"
}

install_pacman() {
    sudo pacman -Sy --noconfirm "$@"
}

echo "[2/8] Installing required system packages..."

if command -v apt >/dev/null 2>&1; then
    if ! command -v python3 >/dev/null 2>&1; then
        install_apt python3
    fi

    PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

    install_apt \
        python3 \
        python3-pip \
        python3-tk \
        zenity \
        "python${PY_VER}-venv"

elif command -v dnf >/dev/null 2>&1; then
    install_dnf \
        python3 \
        python3-pip \
        python3-virtualenv \
        python3-tkinter \
        zenity

elif command -v pacman >/dev/null 2>&1; then
    install_pacman \
        python \
        python-pip \
        python-virtualenv \
        tk \
        zenity

else
    echo "Unsupported distro."
    echo "Please install these manually, then run this installer again:"
    echo "  python3 / pip / venv / tkinter / zenity"
    exit 1
fi

echo "[3/8] Creating virtual environment..."
rm -rf "$VENV_DIR"
python3 -m venv "$VENV_DIR"

echo "[4/8] Installing Python dependencies..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$ROOT/requirements.txt"

echo "[5/8] Creating runtime launcher..."
cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT="$ROOT"
cd "\$ROOT"
exec "\$ROOT/.venv/bin/python" "\$ROOT/scripts/atak_downloader_finalbuild.py"
LAUNCHER_EOF

chmod +x "$LAUNCHER"

echo "[6/8] Creating desktop launcher..."
DESKTOP_CONTENT="[Desktop Entry]
Version=1.0
Type=Application
Name=$APP_NAME
Comment=Launch ATAK Pipeline
Exec=/bin/bash -lc 'cd \"$ROOT\" && nohup ./run_atak_pipeline.sh >/tmp/atak_pipeline_launcher.log 2>&1 &'
Terminal=false
Categories=Utility;
StartupNotify=true
"

mkdir -p "$HOME/.local/share/applications"
printf '%s\n' "$DESKTOP_CONTENT" > "$HOME/.local/share/applications/$DESKTOP_FILE_NAME"
chmod +x "$HOME/.local/share/applications/$DESKTOP_FILE_NAME"

if [ -d "$HOME/Desktop" ]; then
    printf '%s\n' "$DESKTOP_CONTENT" > "$HOME/Desktop/$DESKTOP_FILE_NAME"
    chmod +x "$HOME/Desktop/$DESKTOP_FILE_NAME"
fi

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
fi

echo "[7/8] Installation complete."
echo "A desktop launcher named ATAK Pipeline has been created."

echo "[8/8] Starting pipeline..."
nohup "$LAUNCHER" >/dev/null 2>&1 &

if command -v zenity >/dev/null 2>&1; then
    zenity --info \
        --title="ATAK Pipeline" \
        --text="Installation complete.\n\nA desktop launcher named ATAK Pipeline has been created." \
        --width=420 >/dev/null 2>&1 || true
fi
