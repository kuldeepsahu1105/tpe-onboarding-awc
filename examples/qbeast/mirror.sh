#!/usr/bin/env bash
# Copies every chart and image in mirror.yaml from the Qbeast registry into your
# OCI registry, multi-arch images included.
#
#   DEST_REGISTRY=registry.example.com DEST_NAMESPACE=awc-marketplace ./mirror.sh
#
# Requires helm, skopeo and yq (mikefarah, v4), and a login to both registries.
# For the Qbeast registry the password is the registry license key Qbeast gave
# you; the username is not checked:
#
#   KEY=/path/to/qbeast-registry.license
#   tr -d '\n' < "$KEY" | helm registry login registry.example.invalid -u license --password-stdin
#   tr -d '\n' < "$KEY" | crane auth login registry.example.invalid -u license --password-stdin
#
# (skopeo also reads the Docker credentials crane writes, ~/.docker/config.json.)
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${DEST_REGISTRY:?set DEST_REGISTRY, e.g. registry.example.com}"
: "${DEST_NAMESPACE:?set DEST_NAMESPACE, e.g. awc-marketplace}"
export DEST_REGISTRY DEST_NAMESPACE
WORK="$(mktemp -d)"
archives=()
cleanup() {
  if [ "${#archives[@]}" -gt 0 ]; then rm -f -- "${archives[@]}"; fi
  rmdir "$WORK"
}
trap cleanup EXIT

expand() { yq "$1" "$DIR/mirror.yaml" | sed "s|\${DEST_REGISTRY}|$DEST_REGISTRY|g; s|\${DEST_NAMESPACE}|$DEST_NAMESPACE|g"; }

charts="$(expand '.charts[] | [.source, .name, .version, .destination] | @tsv')"
images="$(expand '.images[] | [.source, .destination] | @tsv')"
[ -n "$charts" ] && [ -n "$images" ] || { echo "Mirror plan must include charts and images." >&2; exit 1; }

while IFS=$'\t' read -r source name version destination; do
  echo "==> chart $name $version -> $destination"
  archives+=("$WORK/$name-$version.tgz")
  helm pull "$source" --version "$version" --destination "$WORK"
  helm push "$WORK/$name-$version.tgz" "$destination"
done <<< "$charts"

while IFS=$'\t' read -r source destination; do
  echo "==> image $source -> $destination"
  skopeo copy --all "docker://$source" "docker://$destination"
done <<< "$images"

echo "Mirroring complete. Publish with: REGISTRY=$DEST_REGISTRY NAMESPACE=$DEST_NAMESPACE ./publish.sh --push"
