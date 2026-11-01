#!/usr/bin/env bash
# Internal wrapper. The public command is ./awc at the repo root.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
exec "$REPO/awc" "$@"
