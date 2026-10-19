#!/usr/bin/env bash
# Wrapper: run generated publish.sh in an engine plugin directory.
set -euo pipefail
DIR="${1:-}"
PUSH="${2:-}"
if [ -z "$DIR" ]; then
  echo "Usage: $0 <engine-plugin-dir> [--push]" >&2
  exit 1
fi
SCRIPT="$(cd "$DIR" && pwd)/publish.sh"
if [ ! -f "$SCRIPT" ]; then
  echo "Missing: $SCRIPT" >&2
  echo "Generate with: make scaffold-engine FORM=... FORCE=1 (publish.enabled: true)" >&2
  exit 1
fi
if [ "$PUSH" = "--push" ]; then
  if [ "${APPROVE_PUBLISH:-}" != "1" ]; then
    echo "Refusing --push without APPROVE_PUBLISH=1 (human gate)." >&2
    echo "Example: make publish-engine DIR=neo4j PUSH=1 APPROVE_PUBLISH=1" >&2
    exit 1
  fi
  exec bash "$SCRIPT" --push
fi
exec bash "$SCRIPT"
