#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT/.venv"

echo "[1/6] Using project root: $ROOT"

# Detect Python
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python3 not found. Attempting install..."

    if command -v apt >/dev/null 2>&1; then
        sudo apt update
        sudo apt install -y python3 python3-venv python3-pip
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y python3 python3-venv python3-pip
    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -Sy --noconfirm python python-pip
    else
        echo "Unsupported distro. Please install python3 manually."
        exit 1
    fi
fi

echo "[2/6] Creating virtual environment..."
python3 -m venv "$VENV_DIR"

echo "[3/6] Installing dependencies..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$ROOT/requirements.txt"

echo "[4/6] Creating launcher..."
LAUNCHER="$ROOT/run_atak_pipeline.sh"

cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/usr/bin/env bash
ROOT="$ROOT"

echo "=== RUNNING IMAGERY DOWNLOADER ==="
"\$ROOT/.venv/bin/python" "\$ROOT/scripts/atak_downloader_finalbuild.py"

echo "=== RUNNING SQLITE BUILDER ==="
"\$ROOT/.venv/bin/python" "\$ROOT/scripts/atak_imagery_sqlite_builder_finalbuild.py"

echo "=== RUNNING DTED DOWNLOADER ==="
"\$ROOT/.venv/bin/python" "\$ROOT/scripts/atak_dted_downloader.py"

echo "=== ALL TASKS COMPLETE ==="
LAUNCHER_EOF

chmod +x "$LAUNCHER"

echo "[5/6] Done."
echo
echo "Launcher created at:"
echo "  $LAUNCHER"

echo "[6/6] Starting pipeline..."
exec "$LAUNCHER"
