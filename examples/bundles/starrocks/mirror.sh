#!/usr/bin/env bash
# Copies every chart and image listed in mirror.yaml into your internal OCI
# registry. Requires: helm, skopeo, and `helm registry login` / `skopeo login`
# for registry.partner-corp.example.com.
set -euo pipefail
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
DEST_CHARTS="oci://registry.partner-corp.example.com/starrocks/charts"

helm pull "kube-starrocks" --repo "https://starrocks.github.io/starrocks-kubernetes-operator" --version "1.11.4" --destination "$WORK"

for f in "$WORK"/*.tgz; do [ -e "$f" ] && helm push "$f" "$DEST_CHARTS"; done

skopeo copy --all "docker://docker.io/starrocks/operator:v1.11.4" \
  "docker://registry.partner-corp.example.com/starrocks/starrocks/operator:v1.11.4"
skopeo copy --all "docker://docker.io/starrocks/fe-ubuntu:3.4.3" \
  "docker://registry.partner-corp.example.com/starrocks/starrocks/fe-ubuntu:3.4.3"
skopeo copy --all "docker://docker.io/starrocks/be-ubuntu:3.4.3" \
  "docker://registry.partner-corp.example.com/starrocks/starrocks/be-ubuntu:3.4.3"
echo "Mirroring complete."
