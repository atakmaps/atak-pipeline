#!/usr/bin/env bash
# Run tile plan cache generation ON THIS MACHINE (your server / VM).
#
# Expects a normal repo layout with this file under scripts/:
#   scripts/build_tile_plan_cache.py
#   scripts/imagery_tile_selection.py
#   scripts/data/us_states.geojson
#   scripts/data/zoom_estimates_z10_z16.json
#
# From the repo root after git clone / pull on the server:
#   chmod +x scripts/tile_plan_cache_on_server.sh
#   scripts/tile_plan_cache_on_server.sh
#
# Long full-US runs (detach from SSH, keep process if session drops):
#   nohup scripts/tile_plan_cache_on_server.sh >> /var/log/tile_plan_cache.log 2>&1 &
#   tail -f /var/log/tile_plan_cache.log
#
# Filters (same as build_tile_plan_cache.py):
#   scripts/tile_plan_cache_on_server.sh --states Arkansas --zooms 16

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

for need in build_tile_plan_cache.py imagery_tile_selection.py data/us_states.geojson; do
  if [[ ! -e "$need" ]]; then
    echo "Missing $SCRIPT_DIR/$need — need full checkout; cwd is $(pwd)" >&2
    exit 1
  fi
done

exec python3 build_tile_plan_cache.py "$@"
