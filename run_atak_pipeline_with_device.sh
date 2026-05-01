#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export PATH="/usr/local/bin:/usr/bin:/bin${PATH:+:$PATH}"
if [ -d "$HOME/Android/Sdk/platform-tools" ]; then
  export PATH="$HOME/Android/Sdk/platform-tools:$PATH"
fi
if [ -f "$ROOT/deploy.env" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ROOT/deploy.env"
  set +a
fi
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/atak_adb_deploy.py"
