#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/paul/Desktop/ATAK/pipeline"
cd "$ROOT"
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/atak_downloader_finalbuild.py"
