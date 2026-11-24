#!/usr/bin/env bash
# Validates and publishes the Qbeast engine and its Blueprint to an OCI
# marketplace registry with the awc-marketplace CLI.
#
#   REGISTRY=registry.example.com NAMESPACE=awc-marketplace ./publish.sh          # dry run
#   REGISTRY=registry.example.com NAMESPACE=awc-marketplace ./publish.sh --push   # real push
#
# The engine publish copies the images and charts of imagecatalog.yaml and
# chartcatalog.yaml from the Qbeast registry into REGISTRY/NAMESPACE (skipping
# what mirror.sh already copied) and repoints the published catalogs at them.
# It needs a login to both registries (see mirror.sh for the Qbeast one).
#
# Env: AWC_MARKETPLACE (binary, default awc-marketplace), REGISTRY, NAMESPACE.
# Schema version 2: the manifests are v1alpha10, which schema version 1 rejects.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AWC="${AWC_MARKETPLACE:-awc-marketplace}"
: "${REGISTRY:?set REGISTRY, the marketplace registry host}"
: "${NAMESPACE:?set NAMESPACE, the marketplace namespace}"
SCHEMA_VERSION=2
ENGINE="$(yq '.metadata.name' "$DIR/engine.yaml")"
# v1alpha10 engines carry no version: the engine is published under the
# Blueprint instance's minimumVersion, which the Blueprint publish requires.
VERSION="$(ENGINE="$ENGINE" yq '.spec.instances[] | select(.engine == strenv(ENGINE)) | .minimumVersion' "$DIR/blueprint.yaml")"
INSTANCE="$(ENGINE="$ENGINE" yq '.spec.instances[] | select(.engine == strenv(ENGINE)) | .name' "$DIR/blueprint.yaml")"
PUSH=()
if [ "${1:-}" = "--push" ]; then PUSH=(--push); fi

echo "==> Linting"
"$AWC" lint --schema-version "$SCHEMA_VERSION" "$DIR"
"$AWC" lint --schema-version "$SCHEMA_VERSION" --blueprint "$DIR/blueprint.yaml"

echo "==> Publishing engine $ENGINE $VERSION"
"$AWC" publish --version "$VERSION" --namespace "$NAMESPACE" \
  --destination-registry "$REGISTRY" --schema-version "$SCHEMA_VERSION" \
  ${PUSH[@]+"${PUSH[@]}"} --force "$DIR"

echo "==> Publishing blueprint $(yq '.metadata.name' "$DIR/blueprint.yaml") $VERSION"
"$AWC" publish --version "$VERSION" --namespace "$NAMESPACE" \
  --destination-registry "$REGISTRY" --schema-version "$SCHEMA_VERSION" \
  --blueprint "$DIR/blueprint.yaml" \
  --instance "$INSTANCE=$ENGINE:$VERSION" \
  ${PUSH[@]+"${PUSH[@]}"} --force

if [ "${#PUSH[@]}" -gt 0 ]; then
  "$AWC" catalog fetch --registry "$REGISTRY" --namespace "$NAMESPACE"
  echo "Pushed. The Console picks the new version up at its next catalog sync."
else
  echo "Dry run complete. Re-run with --push to publish."
fi
