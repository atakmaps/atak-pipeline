#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT/.venv"
LAUNCHER="$ROOT/run_atak_pipeline.sh"
DEVICE_LAUNCHER="$ROOT/run_atak_pipeline_with_device.sh"
DESKTOP_FILE_NAME="ATAK Pipeline.desktop"
DESKTOP_FILE_NAME_DEVICE="ATAK Pipeline (device setup).desktop"
APP_NAME="ATAK Pipeline"
APP_NAME_DEVICE="ATAK Pipeline (device setup)"

echo "[1/7] Using project root: $ROOT"

deb_installed() {
    local pkg="$1"
    local st
    st="$(dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null || true)"
    [[ "$st" == *"ok installed"* ]]
}

rpm_installed() {
    rpm -q "$1" &>/dev/null
}

pacman_installed() {
    pacman -Qi "$1" &>/dev/null
}

echo "[2/7] Checking required system packages..."

if command -v apt >/dev/null 2>&1; then
    if ! command -v python3 >/dev/null 2>&1; then
        echo "  Installing python3 (required to continue)..."
        sudo apt-get update -qq
        sudo apt-get install -y python3
    fi

    PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    apt_pkgs=(python3 python3-pip python3-tk zenity adb "python${PY_VER}-venv")
    apt_missing=()
    for pkg in "${apt_pkgs[@]}"; do
        if ! deb_installed "$pkg"; then
            apt_missing+=("$pkg")
        fi
    done

    if [ ${#apt_missing[@]} -gt 0 ]; then
        echo "  Installing: ${apt_missing[*]}"
        sudo apt-get update -qq
        sudo apt-get install -y "${apt_missing[@]}"
    else
        echo "  All apt packages already present; skipping."
    fi

elif command -v dnf >/dev/null 2>&1; then
    dnf_pkgs=(python3 python3-pip python3-virtualenv python3-tkinter zenity android-tools)
    dnf_missing=()
    for pkg in "${dnf_pkgs[@]}"; do
        if ! rpm_installed "$pkg"; then
            dnf_missing+=("$pkg")
        fi
    done

    if [ ${#dnf_missing[@]} -gt 0 ]; then
        echo "  Installing: ${dnf_missing[*]}"
        sudo dnf install -y "${dnf_missing[@]}"
    else
        echo "  All dnf packages already present; skipping."
    fi

elif command -v pacman >/dev/null 2>&1; then
    pac_pkgs=(python python-pip python-virtualenv tk zenity android-tools)
    pac_missing=()
    for pkg in "${pac_pkgs[@]}"; do
        if ! pacman_installed "$pkg"; then
            pac_missing+=("$pkg")
        fi
    done

    if [ ${#pac_missing[@]} -gt 0 ]; then
        echo "  Installing: ${pac_missing[*]}"
        sudo pacman -Sy --noconfirm "${pac_missing[@]}"
    else
        echo "  All pacman packages already present; skipping."
    fi

else
    echo "Unsupported distro."
    echo "Please install these manually, then run this installer again:"
    echo "  python3 / pip / venv / tkinter / zenity / adb (Android platform tools)"
    exit 1
fi

venv_python="$VENV_DIR/bin/python"
venv_created=0

echo "[3/7] Virtual environment..."

if [ -x "$venv_python" ]; then
    if "$venv_python" -c "import geopandas, shapely, rasterio, numpy, requests" &>/dev/null; then
        echo "  Reusing existing .venv (imports OK)."
    else
        echo "  Existing .venv is incomplete; recreating..."
        rm -rf "$VENV_DIR"
        python3 -m venv "$VENV_DIR"
        venv_created=1
    fi
else
    echo "  Creating new .venv..."
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
    venv_created=1
fi

echo "[4/7] Python dependencies (requirements.txt)..."
if [ "$venv_created" -eq 1 ]; then
    "$VENV_DIR/bin/python" -m pip install --upgrade pip
    "$VENV_DIR/bin/pip" install -r "$ROOT/requirements.txt"
else
    if ! "$venv_python" -m pip check &>/dev/null; then
        echo "  pip check reported issues; syncing requirements.txt..."
        "$VENV_DIR/bin/pip" install -r "$ROOT/requirements.txt"
    else
        echo "  Already satisfied; skipping pip."
    fi
fi

if [ ! -f "$ROOT/deploy.env" ] && [ -f "$ROOT/deploy.env.example" ]; then
    cp "$ROOT/deploy.env.example" "$ROOT/deploy.env"
fi

echo "[5/7] Creating runtime launchers..."
cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT="$ROOT"
cd "\$ROOT"
exec "\$ROOT/.venv/bin/python" "\$ROOT/scripts/atak_downloader_finalbuild.py"
LAUNCHER_EOF

chmod +x "$LAUNCHER"

cat > "$DEVICE_LAUNCHER" <<DEVICE_LAUNCHER_EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT="$ROOT"
cd "\$ROOT"
export PATH="/usr/local/bin:/usr/bin:/bin\${PATH:+:\$PATH}"
if [ -d "\$HOME/Android/Sdk/platform-tools" ]; then
  export PATH="\$HOME/Android/Sdk/platform-tools:\$PATH"
fi
if [ -f "\$ROOT/deploy.env" ]; then
  set -a
  # shellcheck disable=SC1090
  . "\$ROOT/deploy.env"
  set +a
fi
exec "\$ROOT/.venv/bin/python" "\$ROOT/scripts/atak_adb_deploy.py"
DEVICE_LAUNCHER_EOF

chmod +x "$DEVICE_LAUNCHER"

write_desktop_shortcut() {
    local file_name="$1"
    local name="$2"
    local comment="$3"
    local exec_cmd="$4"

    local content="[Desktop Entry]
Version=1.0
Type=Application
Name=$name
Comment=$comment
Exec=$exec_cmd
Terminal=false
Categories=Utility;
StartupNotify=true
"
    mkdir -p "$HOME/.local/share/applications"
    printf '%s\n' "$content" > "$HOME/.local/share/applications/$file_name"
    chmod +x "$HOME/.local/share/applications/$file_name"

    if [ -d "$HOME/Desktop" ]; then
        printf '%s\n' "$content" > "$HOME/Desktop/$file_name"
        chmod +x "$HOME/Desktop/$file_name"
    fi
}

echo "[6/7] Creating desktop launchers..."
write_desktop_shortcut "$DESKTOP_FILE_NAME" "$APP_NAME" "Download maps and build packages for ATAK" \
    "/bin/bash -lc 'cd \"$ROOT\" && nohup ./run_atak_pipeline.sh >/tmp/atak_pipeline_launcher.log 2>&1 &'"
write_desktop_shortcut "$DESKTOP_FILE_NAME_DEVICE" "$APP_NAME_DEVICE" "Install ATAK and plugin on Android, then run the map pipeline" \
    "/bin/bash -lc 'cd \"$ROOT\" && nohup ./run_atak_pipeline_with_device.sh >/tmp/atak_pipeline_device_launcher.log 2>&1 &'"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
fi

echo "[7/7] Installation complete."
echo "Desktop launchers: \"$DESKTOP_FILE_NAME\" (maps) and \"$DESKTOP_FILE_NAME_DEVICE\" (device setup)."

if command -v zenity >/dev/null 2>&1; then
    zenity --info \
        --title="ATAK Pipeline" \
        --text="Installation complete. Nothing was started automatically.\n\nThe first time, open:\n\n• ATAK Pipeline (device setup)\n  — USB install of ATAK and your plugin, then the map tools.\n\nLater, for more imagery on a device that already has ATAK:\n\n• ATAK Pipeline\n  — download maps and build packages only." \
        --width=480 >/dev/null 2>&1 || true
fi
