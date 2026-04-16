#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

VERSION="$(tr -d '[:space:]' < VERSION)"
OUTDIR="$ROOT/dist"
ASSET_NAME="atak-linux-install.zip"
TMPDIR="$(mktemp -d)"

mkdir -p "$OUTDIR"
trap 'rm -rf "$TMPDIR"' EXIT

echo "Building Linux release zip..."
echo "Version: $VERSION"

mkdir -p "$TMPDIR/atak-pipeline"

copy_if_exists() {
  local src="$1"
  local dest="$2"
  if [ -e "$src" ]; then
    mkdir -p "$(dirname "$dest")"
    cp -R "$src" "$dest"
  fi
}

copy_if_exists "$ROOT/README.md" "$TMPDIR/atak-pipeline/README.md"
copy_if_exists "$ROOT/VERSION" "$TMPDIR/atak-pipeline/VERSION"
copy_if_exists "$ROOT/install_linux.sh" "$TMPDIR/atak-pipeline/install_linux.sh"
copy_if_exists "$ROOT/run_atak_pipeline.sh" "$TMPDIR/atak-pipeline/run_atak_pipeline.sh"
copy_if_exists "$ROOT/requirements.txt" "$TMPDIR/atak-pipeline/requirements.txt"
copy_if_exists "$ROOT/docs" "$TMPDIR/atak-pipeline/docs"
copy_if_exists "$ROOT/scripts" "$TMPDIR/atak-pipeline/scripts"

chmod +x "$TMPDIR/atak-pipeline/install_linux.sh" || true
chmod +x "$TMPDIR/atak-pipeline/run_atak_pipeline.sh" || true
chmod +x "$TMPDIR/atak-pipeline/scripts/"*.py 2>/dev/null || true

rm -f "$OUTDIR/$ASSET_NAME"
(
  cd "$TMPDIR"
  zip -r "$OUTDIR/$ASSET_NAME" atak-pipeline >/dev/null
)

echo
echo "Linux release asset created:"
echo "  $OUTDIR/$ASSET_NAME"
