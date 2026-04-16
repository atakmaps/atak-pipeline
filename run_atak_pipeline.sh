#!/usr/bin/env bash
ROOT="/home/paul/Desktop/ATAK_fresh_test/atak-pipeline-main"

echo "=== RUNNING IMAGERY DOWNLOADER ==="
"$ROOT/.venv/bin/python" "$ROOT/scripts/atak_downloader_finalbuild.py"

echo "=== RUNNING SQLITE BUILDER ==="
"$ROOT/.venv/bin/python" "$ROOT/scripts/atak_imagery_sqlite_builder_finalbuild.py"

echo "=== RUNNING DTED DOWNLOADER ==="
"$ROOT/.venv/bin/python" "$ROOT/scripts/atak_dted_downloader.py"

echo "=== ALL TASKS COMPLETE ==="
