#!/usr/bin/env bash
# Copies every chart and image listed in mirror.yaml into your internal OCI
# registry. Requires: helm, skopeo, and `helm registry login` / `skopeo login`
# for registry.partner-corp.example.com.
set -euo pipefail
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
DEST_CHARTS="oci://registry.partner-corp.example.com/neo4j/charts"

helm pull "neo4j" --repo "https://helm.neo4j.com/neo4j" --version "5.26.0" --destination "$WORK"

for f in "$WORK"/*.tgz; do [ -e "$f" ] && helm push "$f" "$DEST_CHARTS"; done

skopeo copy --all "docker://docker.io/neo4j:5.26.0-community" \
  "docker://registry.partner-corp.example.com/neo4j/neo4j:5.26.0-community"
echo "Mirroring complete."
