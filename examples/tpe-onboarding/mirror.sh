#!/usr/bin/env bash
# Copies charts and images from mirror.yaml into the registry named at publish time.
# Same shape as examples/neo4j/mirror.sh (helm pull/push and skopeo copy).
# Refuses while REGISTRY, NAMESPACE, or the chart and image lists are still
# empty or still placeholders. Nothing is pulled or pushed on that path.
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
    *"<"*|*">"*|*placeholder*|*example.com*) return 0 ;;
  esac
  return 1
}

if is_placeholder "$REGISTRY" || is_placeholder "$NAMESPACE"; then
  echo "Refusing mirror. Registry host and repository are empty or still placeholders." >&2
  echo "Set REGISTRY and NAMESPACE when you publish. Nothing was copied." >&2
  exit 1
fi

python3 - "$PLAN" << 'PY'
import sys
try:
    import yaml
except ImportError:
    sys.stderr.write("Refusing mirror. python3 PyYAML is required to read mirror.yaml.\n")
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

problems = []
if not charts:
    problems.append("chart list is empty (no workbench chart yet)")
if not images:
    problems.append("image list is empty (no workbench image yet)")
for chart in charts:
    if not isinstance(chart, dict) or any(bad(chart.get(k)) for k in ("repository", "name", "version", "destination")):
        problems.append("a chart entry is missing a real repository, name, version, or destination")
for image in images:
    if not isinstance(image, dict) or any(bad(image.get(k)) for k in ("source", "destination")):
        problems.append("an image entry is missing a real source or destination")
if problems:
    sys.stderr.write("Refusing mirror. " + "; ".join(problems) + ".\n")
    sys.stderr.write("Nothing was copied.\n")
    sys.exit(1)
PY

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
DEST_CHARTS="oci://${REGISTRY}/${NAMESPACE}/charts"
python3 - "$PLAN" > "$WORK/plan.txt" << 'PY'
import sys, yaml
with open(sys.argv[1]) as fh:
    doc = yaml.safe_load(fh) or {}
for chart in doc.get("charts") or []:
    print("CHART\t%s\t%s\t%s" % (chart["repository"], chart["name"], chart["version"]))
for image in doc.get("images") or []:
    print("IMAGE\t%s\t%s" % (image["source"], image["destination"]))
PY

while IFS="$(printf '\t')" read -r kind a b c; do
  case "$kind" in
    CHART) helm pull "$b" --repo "$a" --version "$c" --destination "$WORK" ;;
    IMAGE)
      src="$a"
      case "$src" in
        docker://*) ;;
        *) src="docker://${src}" ;;
      esac
      skopeo copy --all "$src" "docker://${b}"
      ;;
  esac
done < "$WORK/plan.txt"

for f in "$WORK"/*.tgz; do
  [ -e "$f" ] || continue
  helm push "$f" "$DEST_CHARTS"
done

echo "Mirroring complete."
