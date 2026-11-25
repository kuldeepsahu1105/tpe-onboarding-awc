#!/usr/bin/env bash
# Validates and publishes this engine and its Blueprint to an OCI marketplace registry
# using the awc-marketplace CLI (same flow as the StarRocks / PuppyGraph / Neo4j reference repos).
#
#   ./publish.sh              # dry run (nothing pushed)
#   ./publish.sh --push       # real push (VPN/registry login required)
#
# Env: AWC_MARKETPLACE (binary, default awc-marketplace), REGISTRY, NAMESPACE,
#      SCHEMA_VERSION (default 2 for the v1alpha10 marketplace schema)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AWC="${AWC_MARKETPLACE:-awc-marketplace}"
REGISTRY="${REGISTRY:-registry.partner-corp.example.com}"
NAMESPACE="${NAMESPACE:-neo4j}"
SCHEMA_VERSION="${SCHEMA_VERSION:-2}"
VERSION="5.26.0"
PUSH=()
if [ "${1:-}" = "--push" ]; then PUSH=(--push); fi

echo "==> Validating"
"$AWC" validate "$DIR"
"$AWC" validate --blueprint "$DIR/blueprint.yaml"

# Charts/images are mirrored by mirror.sh; skip them here so only ACE metadata is published.
SKIP=(--skip-images --skip-charts)

echo "==> Publishing engine neo4j-ace-engine $VERSION"
"$AWC" publish --version "$VERSION" --namespace "$NAMESPACE" \
  --destination-registry "$REGISTRY" --schema-version "$SCHEMA_VERSION" \
  "${SKIP[@]}" ${PUSH[@]+"${PUSH[@]}"} --force "$DIR"

echo "==> Publishing blueprint neo4j $VERSION"
"$AWC" publish --version "$VERSION" --namespace "$NAMESPACE" \
  --destination-registry "$REGISTRY" --schema-version "$SCHEMA_VERSION" \
  --blueprint "$DIR/blueprint.yaml" \
  --instance "neo4j=neo4j-ace-engine:$VERSION" \
  ${PUSH[@]+"${PUSH[@]}"} --force

if [ "${#PUSH[@]}" -gt 0 ]; then
  "$AWC" catalog fetch --registry "$REGISTRY" --namespace "$NAMESPACE"
  echo "Pushed. Partner AWC catalog sync takes ~60s."
else
  echo "Dry run complete. Re-run with --push to publish."
fi
