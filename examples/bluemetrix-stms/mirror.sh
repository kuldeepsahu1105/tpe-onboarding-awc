#!/usr/bin/env bash
# DRAFT. Not for a real push. STMS Helm chart and images are not published yet.
#
# Copies charts and images listed in mirror.yaml into the partner OCI registry.
# Exits non-zero while REGISTRY, NAMESPACE, or the chart/image lists are still
# placeholders. Nothing is pulled or pushed on that path.
#
#   ./mirror.sh
#
# Env: REGISTRY, NAMESPACE
# Requires when the lists are real: helm, skopeo, registry login
# (helm registry login / skopeo login).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLAN="${DIR}/mirror.yaml"
REGISTRY="${REGISTRY:-}"
NAMESPACE="${NAMESPACE:-}"

is_placeholder() {
  local v="$1"
  [ -z "$v" ] && return 0
  case "$v" in
    *"<"*|*">"*) return 0 ;;
  esac
  return 1
}

if is_placeholder "$REGISTRY" || is_placeholder "$NAMESPACE"; then
  echo "DRAFT: refusing mirror. REGISTRY and NAMESPACE are empty or still placeholders." >&2
  echo "Set REGISTRY=<your-registry> and NAMESPACE=<your-namespace> after the chart exists." >&2
  echo "STMS Helm chart and images are not published yet. Nothing was copied." >&2
  exit 1
fi

python3 - "$PLAN" <<'PY'
import sys
try:
    import yaml
except ImportError:
    sys.stderr.write("DRAFT: refusing mirror. python3 PyYAML is required to read mirror.yaml.\n")
    sys.exit(1)

path = sys.argv[1]
with open(path) as fh:
    doc = yaml.safe_load(fh) or {}
charts = doc.get("charts") or []
images = doc.get("images") or []
problems = []

def bad(value):
    if value is None:
        return True
    text = str(value).strip()
    return (not text) or ("<" in text) or (">" in text)

if not charts:
    problems.append("chart list is empty (no STMS Helm chart yet)")
if not images:
    problems.append("image list is empty (no STMS image or agent sidecar image yet)")
for index, chart in enumerate(charts):
    if not isinstance(chart, dict):
        problems.append(f"chart {index} is not a mapping")
        continue
    for key in ("repository", "name", "version", "destination"):
        if bad(chart.get(key)):
            problems.append(f"chart {index} field {key} is a placeholder")
for index, image in enumerate(images):
    if not isinstance(image, dict):
        problems.append(f"image {index} is not a mapping")
        continue
    for key in ("source", "destination"):
        if bad(image.get(key)):
            problems.append(f"image {index} field {key} is a placeholder")

if problems:
    sys.stderr.write("DRAFT: refusing mirror. STMS Helm chart and images are not published yet.\n")
    for item in problems:
        sys.stderr.write(f"  - {item}\n")
    sys.stderr.write("Fill bluemetrix-stms/mirror.yaml with the real chart and the STMS and agent sidecar images.\n")
    sys.stderr.write("Nothing was copied.\n")
    sys.exit(1)
PY

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
DEST_CHARTS="oci://${REGISTRY}/${NAMESPACE}/charts"

python3 - "$PLAN" "$WORK/charts.tsv" "$WORK/images.tsv" <<'PY'
import sys
import yaml
path, charts_out, images_out = sys.argv[1:]
with open(path) as fh:
    doc = yaml.safe_load(fh) or {}
with open(charts_out, "w") as fh:
    for chart in doc.get("charts") or []:
        fh.write("\t".join([chart["repository"], chart["name"], chart["version"], chart["destination"]]) + "\n")
with open(images_out, "w") as fh:
    for image in doc.get("images") or []:
        fh.write("\t".join([image["source"], image["destination"]]) + "\n")
PY

while IFS="$(printf '\t')" read -r repo name version destination; do
  [ -n "$repo" ] || continue
  helm pull "$name" --repo "$repo" --version "$version" --destination "$WORK"
  target="${destination:-$DEST_CHARTS}"
  for f in "$WORK"/*.tgz; do
    [ -e "$f" ] || continue
    helm push "$f" "$target"
  done
done < "$WORK/charts.tsv"

while IFS="$(printf '\t')" read -r source destination; do
  [ -n "$source" ] || continue
  skopeo copy --all "docker://${source}" "docker://${destination}"
done < "$WORK/images.tsv"

echo "Mirroring complete."
