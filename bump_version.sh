#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [ ! -f VERSION ]; then
  echo "ERROR: VERSION file not found"
  exit 1
fi

CURRENT="$(tr -d '[:space:]' < VERSION)"

if [[ ! "$CURRENT" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "ERROR: VERSION must be in MAJOR.MINOR.PATCH format"
  echo "Current VERSION: $CURRENT"
  exit 1
fi

PART="${1:-patch}"

IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT"

case "$PART" in
  major)
    MAJOR=$((MAJOR + 1))
    MINOR=0
    PATCH=0
    ;;
  minor)
    MINOR=$((MINOR + 1))
    PATCH=0
    ;;
  patch)
    PATCH=$((PATCH + 1))
    ;;
  *)
    echo "Usage: ./bump_version.sh [major|minor|patch]"
    exit 1
    ;;
esac

NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"
printf "%s\n" "$NEW_VERSION" > VERSION

echo "Bumped version:"
echo "  $CURRENT -> $NEW_VERSION"
