#!/usr/bin/env bash
# Delegate wizard / Web UI / MCP to tpe-onboarding-awc (awc_onboarding/).
#
# Clone the extended toolkit and point AWC_ONBOARDING_REPO at awc_onboarding/:
#
#   git clone -b kuldeepsahu1105-awc-engine-onboarding-toolkit \
#     https://github.com/kuldeepsahu1105/tpe-onboarding-awc.git ~/tpe-onboarding-awc
#   export AWC_ONBOARDING_REPO=~/tpe-onboarding-awc/awc_onboarding
#
# Then from ace-engines repo root:
#   make onboarding-wizard
#   make onboarding-mcp-config   # paste into Cursor MCP settings
#
set -euo pipefail

AWC_ONBOARDING_REPO="${AWC_ONBOARDING_REPO:-}"

resolve_repo() {
  if [ -n "$AWC_ONBOARDING_REPO" ] && [ -x "$AWC_ONBOARDING_REPO/awc" ]; then
    printf '%s\n' "$AWC_ONBOARDING_REPO"
    return 0
  fi
  for candidate in \
    "${AWC_ONBOARDING_REPO:-}" \
    "${HOME}/tpe-onboarding-awc/awc_onboarding" \
    "${HOME}/src/tpe-onboarding-awc/awc_onboarding"; do
    if [ -n "$candidate" ] && [ -x "$candidate/awc" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

ROOT="$(resolve_repo)" || {
  cat >&2 <<'EOF'
AWC extended onboarding toolkit not found.

Set AWC_ONBOARDING_REPO to the awc_onboarding/ directory from:
  https://github.com/kuldeepsahu1105/tpe-onboarding-awc
  branch: kuldeepsahu1105-awc-engine-onboarding-toolkit

Example:
  export AWC_ONBOARDING_REPO=$HOME/tpe-onboarding-awc/awc_onboarding
  make onboarding-wizard
EOF
  exit 1
}

if [ $# -eq 0 ]; then
  set -- help
fi

exec "$ROOT/awc" "$@"
