#!/usr/bin/env bash
# Build tile plan caches on a remote Linux host (e.g. your DTED VM) and rsync *.tiles.gz back.
#
# Prefer running entirely ON the server? Use scripts/tile_plan_cache_on_server.sh after git clone there;
# see scripts/data/tile_plans/README.md — this file is only for laptop → rsync up → run → rsync down.
#
# The DTED app only uses HTTP to that server (see BASE_URL in atak_dted_downloader.py). This
# script needs normal SSH + rsync access to the same (or any) machine where python3 is available.
#
# Usage:
#   TILE_PLAN_SSH=user@31.220.30.74 ./scripts/tile_plan_cache_remote_build.sh
#   TILE_PLAN_SSH=root@your.server TILE_PLAN_REMOTE_DIR=/root/atak-tile-cache ./scripts/tile_plan_cache_remote_build.sh
#   TILE_PLAN_SSH=user@host TILE_PLAN_REMOTE_DIR=/var/tmp/tile-cache ./scripts/tile_plan_cache_remote_build.sh --states Arkansas
#   ./scripts/tile_plan_cache_remote_build.sh user@host --zooms 14,15,16
#
# Stay on the laptop only for upload/download: start the build on the server in the background, then disconnect:
#   TILE_PLAN_SSH=root@host TILE_PLAN_REMOTE_DIR=/root/atak-tile-cache TILE_PLAN_DETACH=1 ./scripts/tile_plan_cache_remote_build.sh
#   # later:
#   rsync -avz root@host:/root/atak-tile-cache/scripts/data/tile_plans/v1/ ./scripts/data/tile_plans/v1/
#
# Optional env:
#   TILE_PLAN_SSH          SSH target (required if not passed as first arg)
#   TILE_PLAN_REMOTE_DIR   Absolute path on server for the build tree (default: $HOME/atak-pipeline-tile-cache-build on remote)
#   TILE_PLAN_DETACH=1     After rsync up, run python under nohup and exit (no blocking SSH, no auto rsync pull)
#
# SSH: Uses your normal OpenSSH setup — key in ssh-agent or IdentityFile in ~/.ssh/config.
# TILE_PLAN_SSH can be a Host alias (e.g. TILE_PLAN_SSH=dted-vm). For a non-default key only
# for this host, prefer a config block over passwords. rsync uses the same transport via ssh(1).

set -euo pipefail

LOCAL_SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SSH_TARGET="${TILE_PLAN_SSH:-}"
REMOTE_DIR="${TILE_PLAN_REMOTE_DIR:-}"

ARGS=()
while [[ $# -gt 0 ]]; do
  if [[ "$1" == *@* ]] && [[ -z "$SSH_TARGET" ]]; then
    SSH_TARGET="$1"
    shift
  else
    ARGS+=("$1")
    shift
  fi
done

if [[ -z "$SSH_TARGET" ]]; then
  echo "Usage: TILE_PLAN_SSH=user@host $0 [user@host] [-- build_tile_plan_cache.py args...]" >&2
  exit 1
fi

if [[ -z "$REMOTE_DIR" ]]; then
  REMOTE_HOME="$(ssh -o BatchMode=yes -o ConnectTimeout=15 "$SSH_TARGET" 'printf %s "$HOME"')"
  REMOTE_DIR="${REMOTE_HOME}/atak-pipeline-tile-cache-build"
fi

quote_remote() {
  local q=()
  local a
  for a in "$@"; do
    q+=("$(printf '%q' "$a")")
  done
  printf '%s' "${q[*]}"
}

RARGS="$(quote_remote "${ARGS[@]}")"

echo "Syncing Python + GeoJSON to ${SSH_TARGET}:${REMOTE_DIR}/scripts/ ..."
ssh "$SSH_TARGET" "mkdir -p '${REMOTE_DIR}/scripts/data/tile_plans/v1'"
rsync -avz \
  "${LOCAL_SCRIPTS}/build_tile_plan_cache.py" \
  "${LOCAL_SCRIPTS}/imagery_tile_selection.py" \
  "${SSH_TARGET}:${REMOTE_DIR}/scripts/"
rsync -avz \
  "${LOCAL_SCRIPTS}/data/us_states.geojson" \
  "${LOCAL_SCRIPTS}/data/zoom_estimates_z10_z16.json" \
  "${SSH_TARGET}:${REMOTE_DIR}/scripts/data/"

echo "Remote build (stdout/stderr from server) ..."
REMOTE_LOG="${REMOTE_DIR}/tile_plan_cache.log"

if [[ "${TILE_PLAN_DETACH:-}" == "1" ]]; then
  # shellcheck disable=SC2029
  ssh "$SSH_TARGET" "cd '${REMOTE_DIR}/scripts' && nohup python3 build_tile_plan_cache.py ${RARGS} > '${REMOTE_LOG}' 2>&1 </dev/null & echo Started PID \$! — log ${REMOTE_LOG}"
  echo ""
  echo "Detached: follow log:  ssh ${SSH_TARGET} tail -f ${REMOTE_LOG}"
  echo "When finished, pull:  rsync -avz ${SSH_TARGET}:${REMOTE_DIR}/scripts/data/tile_plans/v1/ ${LOCAL_SCRIPTS}/data/tile_plans/v1/"
  exit 0
fi

# shellcheck disable=SC2029
ssh "$SSH_TARGET" "cd '${REMOTE_DIR}/scripts' && python3 build_tile_plan_cache.py ${RARGS}"

echo "Fetching tile_plans/v1/*.tiles.gz ..."
rsync -avz \
  "${SSH_TARGET}:${REMOTE_DIR}/scripts/data/tile_plans/v1/" \
  "${LOCAL_SCRIPTS}/data/tile_plans/v1/"

echo "Done. Local caches: ${LOCAL_SCRIPTS}/data/tile_plans/v1/"
