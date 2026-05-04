#!/usr/bin/env bash
# Copy pre-built *.tiles.gz from a machine where you ran build_tile_plan_cache / tile_plan_cache_on_server.
# Keeps install_linux.sh small — full-US caches are usually shipped in release zips or an optional download.
#
# Defaults match the maintainer VM layout; override with env:
#   TILE_PLAN_FETCH_SSH=root@host TILE_PLAN_FETCH_REMOTE=/path/to/tile_plans/v1 \
#   TILE_PLAN_FETCH_PATTERN='Texas_z*.tiles.gz' ./scripts/fetch_tile_plan_caches.sh
#
# After run, files live in scripts/data/tile_plans/v1/ next to us_states.geojson.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/scripts/data/tile_plans/v1"
SSH_TARGET="${TILE_PLAN_FETCH_SSH:-root@31.220.30.74}"
REMOTE_DIR="${TILE_PLAN_FETCH_REMOTE:-/root/atak-tile-plan/scripts/data/tile_plans/v1}"
PATTERN="${TILE_PLAN_FETCH_PATTERN:-Arkansas_z*.tiles.gz}"

mkdir -p "$DEST"

echo "Fetching $SSH_TARGET:$REMOTE_DIR/$PATTERN → $DEST"
# Remote pathname wildcard is expanded by the OpenSSH scp/sftp server when supported.
scp -o BatchMode=yes -p "$SSH_TARGET:$REMOTE_DIR/$PATTERN" "$DEST/"

echo "Done. Listing:"
ls -la "$DEST"
