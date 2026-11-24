#!/usr/bin/env bash
# Validates and publishes this engine bundle via awc-marketplace.
# Same shape as examples/neo4j/publish.sh.
#
#   ./publish.sh           # dry run, only after names are real
#   ./publish.sh --push    # push; also requires APPROVE_PUBLISH=1
#
# While mirror.yaml or REGISTRY/NAMESPACE/VERSION are still placeholders,
# both the dry run and --push exit non-zero and do not call awc-marketplace.
#
# Env: AWC_MARKETPLACE, REGISTRY, NAMESPACE, SCHEMA_VERSION, VERSION, APPROVE_PUBLISH
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLAN="${DIR}/mirror.yaml"
AWC="${AWC_MARKETPLACE:-awc-marketplace}"
REGISTRY="${REGISTRY:-}"
NAMESPACE="${NAMESPACE:-}"
SCHEMA_VERSION="${SCHEMA_VERSION:-1}"
VERSION="${VERSION:-}"
PUSH=()
if [ "${1:-}" = "--push" ]; then PUSH=(--push); fi

is_placeholder() {
  local v="$1"
  [ -z "$v" ] && return 0
  case "$v" in
    *"<"*|*">"*|*placeholder*|*example.com*) return 0 ;;
  esac
  return 1
}

lists_are_ready() {
  python3 - "$PLAN" << 'PY'
import sys
try:
    import yaml
except ImportError:
    sys.stderr.write("python3 PyYAML is required to read mirror.yaml.\n")
    sys.exit(1)
with open(sys.argv[1]) as fh:
    doc = yaml.safe_load(fh) or {}
charts = doc.get("charts") or []
images = doc.get("images") or []

def bad(value):
    if value is None:
        return True
    text = str(value).strip()
    return (not text) or ("<" in text) or (">" in text) or ("placeholder" in text) or ("example.com" in text)

blocked = not charts or not images
for chart in charts:
    if not isinstance(chart, dict) or any(bad(chart.get(k)) for k in ("repository", "name", "version", "destination")):
        blocked = True
for image in images:
    if not isinstance(image, dict) or any(bad(image.get(k)) for k in ("source", "destination")):
        blocked = True
sys.exit(1 if blocked else 0)
PY
}

if is_placeholder "$REGISTRY" || is_placeholder "$NAMESPACE" || is_placeholder "$VERSION" || ! lists_are_ready; then
  echo "Refusing publish. The workbench chart and image are not published yet." >&2
  echo "Set REGISTRY, NAMESPACE, and VERSION, and list the chart and image in mirror.yaml." >&2
  echo "Nothing was sent." >&2
  exit 1
fi

if [ "${#PUSH[@]}" -gt 0 ] && [ "${APPROVE_PUBLISH:-}" != "1" ]; then
  echo "Refusing --push without APPROVE_PUBLISH=1." >&2
  exit 1
fi

echo "==> Validating"
"$AWC" validate "$DIR"
"$AWC" validate --blueprint "$DIR/blueprint.yaml"

SKIP=(--skip-images --skip-charts)

echo "==> Publishing engine tpe-onboarding-engine $VERSION"
"$AWC" publish --version "$VERSION" --namespace "$NAMESPACE" \
  --destination-registry "$REGISTRY" --schema-version "$SCHEMA_VERSION" \
  "${SKIP[@]}" ${PUSH[@]+"${PUSH[@]}"} --force "$DIR"

echo "==> Publishing blueprint tpe-onboarding-blueprint $VERSION"
"$AWC" publish --version "$VERSION" --namespace "$NAMESPACE" \
  --destination-registry "$REGISTRY" --schema-version "$SCHEMA_VERSION" \
  --blueprint "$DIR/blueprint.yaml" \
  --instance "tpe-onboarding=tpe-onboarding-engine:$VERSION" \
  ${PUSH[@]+"${PUSH[@]}"} --force

if [ "${#PUSH[@]}" -gt 0 ]; then
  "$AWC" catalog fetch --registry "$REGISTRY" --namespace "$NAMESPACE"
  echo "Pushed. Partner AWC catalog sync takes ~60s."
else
  echo "Dry run complete. Re-run with --push to publish."
fi
