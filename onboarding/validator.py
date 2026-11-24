"""Static validation of a generated ACE bundle.

Runs entirely offline (no cluster, no OCI, no marketplace CLI needed) so it
can run in CI for every partner before anyone attempts to mirror or publish
anything. Mirrors the "fail fast" philosophy of the reference onboarding
pipelines: validate before you touch a registry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
STANDARDS_DIR = REPO_ROOT / "standards"

_PLACEHOLDER_RE = re.compile(r"<[a-zA-Z][a-zA-Z0-9_.\-/]*>")
# A line that is only a Go action (if / range / end / else) is not YAML.
_GO_ACTION_LINE = re.compile(r"^\s*\{\{-?.*?-?\}\}\s*$")
_GO_EXPR = re.compile(r"\{\{-?.*?-?\}\}")


def _yaml_with_go_neutralized(text: str) -> str:
    """Make a Go-templated manifest parseable for the kind allow-list.

    Control-flow lines are removed. Other ``{{ ... }}`` expressions become the
    plain token GO so unquoted values still parse. Angle-bracket placeholders
    are left untouched; the placeholder scan uses the original text.
    """
    lines = []
    for line in text.splitlines():
        if _GO_ACTION_LINE.match(line):
            continue
        lines.append(_GO_EXPR.sub("GO", line))
    return "\n".join(lines)


@dataclass
class Finding:
    level: str  # "error" | "warning"
    file: str
    message: str


@dataclass
class ValidationResult:
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, level: str, file: str, message: str) -> None:
        self.findings.append(Finding(level, file, message))

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [f.__dict__ for f in self.errors],
            "warnings": [f.__dict__ for f in self.warnings],
        }


def _load_yaml(path: Path) -> list[dict[str, Any]]:
    docs = [d for d in yaml.safe_load_all(path.read_text()) if d]
    return docs


def _get_path(doc: dict[str, Any], dotted: str) -> Any:
    cur: Any = doc
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _parse_cpu(value: str) -> float:
    try:
        return float(str(value).rstrip("m")) / (1000 if str(value).endswith("m") else 1)
    except ValueError:
        return 0.0


def _parse_mem_gi(value: str) -> float:
    value = str(value)
    m = re.match(r"([0-9.]+)\s*(Gi|Mi|G|M)?", value)
    if not m:
        return 0.0
    num = float(m.group(1))
    unit = (m.group(2) or "Gi").lower()
    if unit in ("mi", "m"):
        return num / 1024
    return num


def validate_bundle(bundle_dir: Path, manifest: dict[str, Any]) -> ValidationResult:
    result = ValidationResult()
    rules = yaml.safe_load((STANDARDS_DIR / "validator-rules.yaml").read_text())
    sizing = yaml.safe_load((STANDARDS_DIR / "sizing-baselines.yaml").read_text())

    template_class = manifest["engine"]["template"]
    for dep in manifest["dependencies"]["entries"]:
        if dep["type"] == "ref" and not dep.get("runtimeInstance"):
            result.add("warning", "examples/instance.yaml",
                       f"Required dependency '{dep['name']}' has no verified runtime instance binding.")
    if manifest["blueprint"].get("format", "current") == "current" and (bundle_dir / "clusterrequirements.yaml").exists():
        result.add(
            "error", "clusterrequirements.yaml",
            "Stale legacy ClusterRequirements file: remove it from this generated output before using the current format.",
        )
    required_files = rules["requiredFilesByTemplate"].get(template_class, [])
    for fname in required_files:
        if fname == "blueprint.yaml" and not manifest["blueprint"].get("needed", True):
            continue  # hidden/internal engine -- never gets a Blueprint
        if not (bundle_dir / fname).is_file():
            result.add("error", fname, "Required file is missing from the bundle.")

    for img in manifest.get("images", []):
        ref = f'{img["source"]}/{img["repository"]}:{img["tag"]}'
        if img["tag"] == "latest":
            result.add("warning", "imagecatalog.yaml", f"Image {ref} uses ':latest'; pin an exact tag.")
        if "docker-private.infra.cloudera.com" in ref:
            result.add("error", "imagecatalog.yaml", f"Image {ref} is from a private registry that partner AWC cannot pull.")

    if not (bundle_dir / "engine.yaml").is_file():
        return result  # nothing else to check meaningfully

    # --- engine.yaml structural checks ---------------------------------
    engine_docs = _load_yaml(bundle_dir / "engine.yaml")
    engine_doc = next((d for d in engine_docs if d.get("kind") == "Engine"), None)
    if engine_doc is None:
        result.add("error", "engine.yaml", "No 'kind: Engine' document found.")
    else:
        for req in rules["requiredEngineFields"]:
            if req == "spec.template":
                present = bool(_get_path(engine_doc, req))
            else:
                present = _get_path(engine_doc, req) is not None
            if not present:
                result.add("error", "engine.yaml", f"Missing required field spec path '{req}'.")

        template_text = _get_path(engine_doc, "spec.template") or ""
        try:
            template_docs = list(yaml.safe_load_all(_yaml_with_go_neutralized(template_text)))
        except yaml.YAMLError:
            template_docs = None
            result.add(
                "warning",
                "engine.yaml",
                "spec.template could not be statically parsed as YAML. "
                "Fix the manifest before publishing.",
            )
        for doc in template_docs or []:
            if not doc:
                continue
            kind = doc.get("kind")
            api_version = doc.get("apiVersion", "")
            key = f"{api_version}/{kind}"
            if key not in rules["allowedTemplateKinds"] and not str(api_version).startswith("<"):
                result.add(
                    "warning",
                    "engine.yaml",
                    f"spec.template renders '{key}', which is outside the standard allow-list; "
                    "confirm the ACE operator/RBAC supports it.",
                )

        # Placeholder detection (helm-operator scaffolds ship with <TODO> markers).
        for m in _PLACEHOLDER_RE.finditer(template_text):
            result.add(
                "warning",
                "engine.yaml",
                f"Unresolved placeholder '{m.group(0)}' in spec.template -- "
                "replace with the real operator CRD group/kind before publishing.",
            )

    # --- blueprint.yaml structural checks -------------------------------
    bp_path = bundle_dir / "blueprint.yaml"
    if bp_path.is_file():
        bp_doc = _load_yaml(bp_path)[0]
        format_ = manifest["blueprint"].get("format", "current")
        format_rules = "requiredLegacyBlueprintFields" if format_ == "legacy" else "requiredCurrentBlueprintFields"
        for req in rules["requiredBlueprintFields"] + rules[format_rules]:
            if _get_path(bp_doc, req) is None:
                result.add("error", "blueprint.yaml", f"Missing required field spec path '{req}'.")

        if format_ == "legacy":
            node_groups = _get_path(bp_doc, "spec.cluster.nodeGroups") or []
        else:
            tiers = _get_path(bp_doc, "spec.hardwareTiers") or []
            node_groups = [ng for tier in tiers for ng in tier.get("cluster", {}).get("nodeGroups", [])]
            for inst in _get_path(bp_doc, "spec.instances") or []:
                if not all(inst.get(field) for field in ("name", "engine", "minimumVersion")):
                    result.add("error", "blueprint.yaml", "Each instance needs name, engine and minimumVersion.")
        baseline = sizing.get(template_class, sizing["defaults"])
        for ng in node_groups:
            cpu = _get_path(ng, "resources.minimum.cpu")
            mem = _get_path(ng, "resources.minimum.memory")
            if cpu is not None and _parse_cpu(cpu) < _parse_cpu(baseline["minCpu"]):
                result.add(
                    "warning",
                    "blueprint.yaml",
                    f"Node group '{ng.get('id')}' minimum cpu {cpu} is below the "
                    f"{template_class} baseline of {baseline['minCpu']}.",
                )
            if mem is not None and _parse_mem_gi(mem) < _parse_mem_gi(baseline["minMemory"]):
                result.add(
                    "warning",
                    "blueprint.yaml",
                    f"Node group '{ng.get('id')}' minimum memory {mem} is below the "
                    f"{template_class} baseline of {baseline['minMemory']}.",
                )

    # --- forbidden registries + leftover placeholders in every file -----
    for path in sorted(bundle_dir.glob("*.yaml")):
        text = path.read_text()
        for host in rules["forbiddenRegistryHosts"]:
            if host in text:
                result.add("error", path.name, f"References forbidden registry host '{host}'.")
        if path.name != "engine.yaml":  # already scanned above with context
            for m in _PLACEHOLDER_RE.finditer(text):
                result.add(
                    "warning",
                    path.name,
                    f"Unresolved placeholder '{m.group(0)}' -- fill in before publishing.",
                )

    if str(manifest["publish"].get("destinationRegistry", "")).startswith("<"):
        result.add(
            "warning",
            "manifest",
            "publish.destinationRegistry is still a placeholder; set it to your real OCI registry.",
        )

    return result
