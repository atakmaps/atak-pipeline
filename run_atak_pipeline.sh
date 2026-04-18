#!/usr/bin/env bash
ROOT="/home/paul/Desktop/ATAK/pipeline"

echo "=== RUNNING ATAK PIPELINE ==="
"$ROOT/.venv/bin/python" "$ROOT/scripts/atak_downloader_finalbuild.py"
