#!/usr/bin/env bash
# Copies charts and images from mirror.yaml / form inputs into partner OCI registry.
# Requires: helm, skopeo, registry login (helm registry login / skopeo login).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
DEST_CHARTS="oci://docker-sandbox.infra.cloudera.com/nijjwol-awc/charts"
REGISTRY="${REGISTRY:-docker-sandbox.infra.cloudera.com}"
NAMESPACE="${NAMESPACE:-nijjwol-awc}"

helm pull "neo4j" --repo "https://helm.neo4j.com/neo4j" --version "5.26.0" --destination "$WORK"
for f in "$WORK"/*.tgz; do
  [ -e "$f" ] || continue
  helm push "$f" "$DEST_CHARTS"
done

skopeo copy --all "docker://docker.io/neo4j:5.26.0-community" "docker://${REGISTRY}/${NAMESPACE}/neo4j:5.26.0-community"
echo "Mirroring complete."
