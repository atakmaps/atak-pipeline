#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/atak_downloader_finalbuild.py"
