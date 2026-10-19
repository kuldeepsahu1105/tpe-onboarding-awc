#!/usr/bin/env bash
# Validates and publishes this engine bundle to partner OCI via awc-marketplace CLI.
#
#   ./publish.sh           # dry run
#   ./publish.sh --push    # push (registry/VPN login required)
#
# Env: AWC_MARKETPLACE, REGISTRY, NAMESPACE, SCHEMA_VERSION, VERSION
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AWC="${AWC_MARKETPLACE:-awc-marketplace}"
REGISTRY="${REGISTRY:-docker-sandbox.infra.cloudera.com}"
NAMESPACE="${NAMESPACE:-nijjwol-awc}"
SCHEMA_VERSION="${SCHEMA_VERSION:-1}"
VERSION="${VERSION:-5.26.0}"
PUSH=()
if [ "${1:-}" = "--push" ]; then PUSH=(--push); fi

echo "==> Validating"
"$AWC" validate "$DIR"
"$AWC" validate --blueprint "$DIR/blueprint.yaml"

SKIP=(--skip-images --skip-charts)

echo "==> Publishing engine neo4j-engine $VERSION"
"$AWC" publish --version "$VERSION" --namespace "$NAMESPACE" \
  --destination-registry "$REGISTRY" --schema-version "$SCHEMA_VERSION" \
  "${SKIP[@]}" ${PUSH[@]+"${PUSH[@]}"} --force "$DIR"

echo "==> Publishing blueprint neo4j-blueprint $VERSION"
"$AWC" publish --version "$VERSION" --namespace "$NAMESPACE" \
  --destination-registry "$REGISTRY" --schema-version "$SCHEMA_VERSION" \
  --blueprint "$DIR/blueprint.yaml" \
  --instance "neo4j=neo4j-engine:$VERSION" \
  ${PUSH[@]+"${PUSH[@]}"} --force

if [ "${#PUSH[@]}" -gt 0 ]; then
  "$AWC" catalog fetch --registry "$REGISTRY" --namespace "$NAMESPACE"
  echo "Pushed. Partner AWC catalog sync takes ~60s."
else
  echo "Dry run complete. Re-run with --push to publish."
fi
