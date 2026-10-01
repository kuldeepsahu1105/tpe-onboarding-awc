"""Blueprint composer: build ONE Blueprint for a data/big-data application.

A Blueprint is the Marketplace-facing app (e.g. "DataSpark"). It lists the
engine instances that make up the app and how they are wired together. Each
engine is described with the same slim ``input.yaml`` used for a single
engine; the composer generates every engine's bundle (without its own
Blueprint) and then emits a single ``blueprint.yaml`` for the whole app.

Blueprint input file::

    blueprint:
      name: dataspark
      owner: "DataSpark, Inc."
      displayName: "DataSpark"
      description: "..."
      outcome: "End-to-end analytics"
      version: "1.0.0"
      kubernetesVersion: ">= 1.28.0"      # optional
    engines:
      - input: dataspark-db.input.yaml      # onboard + include this engine
      - input: dataspark-auth.input.yaml
      - input: dataspark-api.input.yaml
      - existing:                           # engine already on the cluster
          engine: keycloak-ace-engine
          instance: keycloak-prod
          version: "24.0"

Wiring: every non-``auto`` dependency of an included engine is wired in the
Blueprint. If the dependency targets another engine in this Blueprint, the
instance name is resolved automatically. ``auto`` dependencies are private to
the engine and never appear in a Blueprint.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from . import questions as q
from .generator import render_bundle
from .manifest import normalize
from .validator import validate_bundle

API_VERSION = "ecosystem.awc.cloudera.com/v1alpha9"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def compose_blueprint(spec_path: Path, out_root: Path) -> dict[str, Any]:
    spec = _load_yaml(spec_path)
    bp = spec.get("blueprint") or {}
    for key in ("name", "owner", "displayName"):
        if not bp.get(key):
            raise ValueError(f"blueprint.{key} is required")
    components = spec.get("engines") or []
    if not components:
        raise ValueError("'engines' must list at least one engine")

    out_dir = out_root / bp["name"]
    version = str(bp.get("version", "1.0.0"))
    instances: list[dict] = []
    node_groups: list[dict] = []
    manifests: list[dict] = []
    reports: dict[str, Any] = {}
    storage_default, storage_min = 0, 0

    def _gi(v: str) -> int:
        return int("".join(c for c in str(v) if c.isdigit()) or 0)

    for comp in components:
        if "existing" in comp:
            ex = comp["existing"]
            instances.append(
                {
                    "name": ex["instance"],
                    "engine": ex["engine"],
                    "version": str(ex.get("version", version)),
                    "_deps": [],
                }
            )
            continue
        input_path = (spec_path.parent / comp["input"]).resolve()
        answers = _load_yaml(input_path)
        q.set_answer(answers, "blueprint.needed", False)
        q.fill_defaults(answers)
        missing = q.next_question(answers)
        if missing:
            raise ValueError(f"{input_path.name}: still need '{missing.id}' ({missing.prompt})")
        manifest = normalize(answers)
        engine_dir = out_dir / "engines" / manifest["partner"]["id"]
        render_bundle(manifest, engine_dir)
        reports[manifest["partner"]["id"]] = validate_bundle(engine_dir, manifest).as_dict()
        manifests.append(manifest)

        c = manifest["cluster"]
        storage_default = max(storage_default, _gi(c["diskDefault"]))
        storage_min = max(storage_min, _gi(c["diskMinimum"]))
        node_groups.append(
            {
                "id": manifest["blueprint"]["nodeGroupId"],
                "category": "worker",
                "displayName": manifest["blueprint"]["nodeGroupDisplayName"],
                "nodeCount": {"default": c["workerCountDefault"], "minimum": c["workerCountMinimum"]},
                "resources": {
                    "minimum": {"cpu": str(c["minCpu"]), "memory": str(c["minMemory"]), "hasGPU": bool(c["hasGPU"])},
                    "recommended": {
                        "cpu": str(c["recommendedCpu"]),
                        "memory": str(c["recommendedMemory"]),
                        "hasGPU": bool(c["hasGPU"]),
                    },
                },
                "storage": {"disk": {"default": str(c["diskDefault"]), "minimum": str(c["diskMinimum"])}},
            }
        )
        instances.append(
            {
                "name": manifest["blueprint"]["instanceName"],
                "engine": manifest["engine"]["name"],
                "version": str(manifest["engine"]["version"]),
                "_deps": [d for d in manifest["dependencies"]["entries"] if d["type"] != "auto"],
            }
        )

    by_engine = {i["engine"]: i["name"] for i in instances}
    out_instances = []
    for inst in instances:
        entry = {"name": inst["name"], "engine": inst["engine"]}
        deps = [
            {"name": d["name"], "instance": by_engine.get(d["engine"], d["instance"])}
            for d in inst["_deps"]
        ]
        if deps:
            entry["dependencies"] = deps
        out_instances.append(entry)

    blueprint = {
        "apiVersion": API_VERSION,
        "kind": "Blueprint",
        "metadata": {"name": bp["name"]},
        "spec": {
            "owner": bp["owner"],
            "displayName": bp["displayName"],
            "description": bp.get("description", f"{bp['displayName']} on Cloudera Anywhere Cloud."),
            **({"outcome": bp["outcome"]} if bp.get("outcome") else {}),
            "versionMatrix": [
                {
                    "displayVersion": version,
                    "instances": [{"name": i["name"], "version": i["version"]} for i in instances],
                }
            ],
            "instances": out_instances,
            "cluster": {
                "kubernetesVersion": bp.get("kubernetesVersion", ">= 1.28.0"),
                "networkStorage": {
                    "default": f"{storage_default or 100}Gi",
                    "minimum": f"{storage_min or 50}Gi",
                    "hint": f"Shared storage for {bp['displayName']}",
                },
                "nodeGroups": node_groups,
            },
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "blueprint.yaml").write_text(yaml.safe_dump(blueprint, sort_keys=False))
    _write_publish_script(out_dir, bp, version, instances, manifests)
    ok = all(r["ok"] for r in reports.values())
    return {"out_dir": str(out_dir), "engines": sorted(reports), "validation": reports, "ok": ok}


def _write_publish_script(out_dir: Path, bp: dict, version: str, instances: list, manifests: list) -> None:
    pub = manifests[0]["publish"] if manifests else {}
    engines = [(m["partner"]["id"], m["engine"]["name"], str(m["engine"]["version"])) for m in manifests]
    inst_args = " ".join(f'--instance "{i["name"]}={i["engine"]}:{i["version"]}"' for i in instances)
    lines = [
        "#!/usr/bin/env bash",
        "# Publishes every engine, then the single Blueprint, with awc-marketplace.",
        "#   ./publish.sh          dry run     ./publish.sh --push   real push",
        "# Run each engines/<id>/mirror.sh first to copy charts and images.",
        "set -euo pipefail",
        'DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
        'AWC="${AWC_MARKETPLACE:-awc-marketplace}"',
        f'REGISTRY="${{REGISTRY:-{pub.get("destinationRegistry", "<registry>")}}}"',
        f'NAMESPACE="${{NAMESPACE:-{pub.get("namespace", "<namespace>")}}}"',
        'SCHEMA_VERSION="${SCHEMA_VERSION:-1}"',
        "PUSH=(); if [ \"${1:-}\" = \"--push\" ]; then PUSH=(--push); fi",
    ]
    for pid, _name, ver in engines:
        lines += [
            f'echo "==> Engine {pid}"',
            f'"$AWC" validate "$DIR/engines/{pid}"',
            f'"$AWC" publish --version "{ver}" --namespace "$NAMESPACE" --destination-registry "$REGISTRY" '
            f'--schema-version "$SCHEMA_VERSION" --skip-images --skip-charts ${{PUSH[@]+\"${{PUSH[@]}}\"}} --force "$DIR/engines/{pid}"',
        ]
    lines += [
        'echo "==> Blueprint ' + bp["name"] + '"',
        '"$AWC" validate --blueprint "$DIR/blueprint.yaml"',
        f'"$AWC" publish --version "{version}" --namespace "$NAMESPACE" --destination-registry "$REGISTRY" '
        f'--schema-version "$SCHEMA_VERSION" --blueprint "$DIR/blueprint.yaml" {inst_args} ${{PUSH[@]+\"${{PUSH[@]}}\"}} --force',
    ]
    path = out_dir / "publish.sh"
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o755)
