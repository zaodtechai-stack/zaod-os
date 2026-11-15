#!/usr/bin/env bash
# Thin wrapper so the Lite mode logic stays in one testable Python module.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TOOL="${ZAOD_LITE_MODE_TOOL:-$REPO_ROOT/desktop/tools/lite_mode.py}"

if [[ ! -f "$TOOL" ]]; then
  printf 'lite-mode: tool not found at %s\n' "$TOOL" >&2
  exit 1
fi

exec python3 "$TOOL" "$@"
