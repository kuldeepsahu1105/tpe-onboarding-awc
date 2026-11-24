#!/usr/bin/env bash
# Front end for awc-oci-register. Credentials remain in external files or provider CLIs.
set -euo pipefail
ACTION="${1:-}"
CONFIG="${2:-}"
TOOL="${AWC_OCI_REGISTER:-awc-oci-register}"
if [ -z "$ACTION" ] || [ -z "$CONFIG" ]; then
  echo "Usage: $0 {init|plan|verify|apply} <config.yaml>" >&2
  exit 1
fi
if ! command -v "$TOOL" >/dev/null 2>&1; then
  echo "awc-oci-register not found; install it and set AWC_OCI_REGISTER or PATH." >&2
  exit 1
fi
case "$ACTION" in
  init)
    if ! (set -o noclobber; : > "$CONFIG") 2>/dev/null; then
      echo "Cannot create $CONFIG; it may already exist." >&2
      exit 1
    fi
    exec "$TOOL" init -o "$CONFIG"
    ;;
  plan|verify)
    [ -f "$CONFIG" ] || { echo "Config not found: $CONFIG" >&2; exit 1; }
    exec "$TOOL" "$ACTION" -f "$CONFIG"
    ;;
  apply)
    [ "${APPROVE_REGISTRY_APPLY:-}" = "1" ] || {
      echo "Refusing registry apply without APPROVE_REGISTRY_APPLY=1." >&2
      exit 1
    }
    [ -f "$CONFIG" ] || { echo "Config not found: $CONFIG" >&2; exit 1; }
    "$TOOL" verify -f "$CONFIG"
    exec "$TOOL" apply -f "$CONFIG"
    ;;
  *)
    echo "Unknown registry action: $ACTION" >&2
    exit 1
    ;;
esac
