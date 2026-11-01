#!/usr/bin/env bash
# Wrapper for https://github.com/agupta-git/awc-oci-register on AWC control plane.
set -euo pipefail
CONFIG="${1:-}"
AWC_OCI_REGISTER="${AWC_OCI_REGISTER:-awc-oci-register}"
if [ -z "$CONFIG" ]; then
  echo "Usage: AWC_OCI_REGISTER=/path/to/awc-oci-register $0 <oci-register.config.yaml>" >&2
  exit 1
fi
if ! command -v "$AWC_OCI_REGISTER" >/dev/null 2>&1; then
  echo "awc-oci-register not found. Clone:" >&2
  echo "  git clone https://github.com/agupta-git/awc-oci-register.git" >&2
  echo "  export AWC_OCI_REGISTER=\$PWD/awc-oci-register/awc-oci-register" >&2
  exit 1
fi
"$AWC_OCI_REGISTER" verify -f "$CONFIG"
exec "$AWC_OCI_REGISTER" apply -f "$CONFIG"
