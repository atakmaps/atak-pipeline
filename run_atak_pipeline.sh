#!/usr/bin/env bash
set -euo pipefail
ROOT="/home/paul/Documents/ATAK/pipeline"
cd "$ROOT"
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/atak_downloader_finalbuild.py"
