#!/usr/bin/env bash
# Wrapper: run generated mirror.sh in an engine plugin directory.
set -euo pipefail
DIR="${1:-}"
if [ -z "$DIR" ]; then
  echo "Usage: $0 <engine-plugin-dir>" >&2
  exit 1
fi
SCRIPT="$(cd "$DIR" && pwd)/mirror.sh"
if [ ! -f "$SCRIPT" ]; then
  echo "Missing: $SCRIPT (scaffold with publish/mirror in input_form)" >&2
  exit 1
fi
exec bash "$SCRIPT"
