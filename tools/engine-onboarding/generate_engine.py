#!/usr/bin/env python3
"""
Generate an ace-engines plugin directory from input_form.yaml.

CLI and UI can share the same form document: UI collects fields, writes YAML,
then invokes this script (or calls the same Python module).

Requires: PyYAML (stdlib fallback not used).
Optional validation: pip install jsonschema pyyaml
"""

from __future__ import annotations

import argparse
import stat
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML is required: pip install pyyaml") from exc

ACE_API = "ecosystem.awc.cloudera.com/v1alpha10"
AUTH_API = "security.awc.cloudera.com/v1alpha1"

RBAC_RULES: dict[str, list[dict[str, Any]]] = {
    "helm-basic": [
        {
            "apiGroups": ["source.toolkit.fluxcd.io"],
            "resources": ["helmrepositories"],
            "verbs": ["create", "delete", "get", "list", "patch", "update", "watch"],
        },
        {
            "apiGroups": ["helm.toolkit.fluxcd.io"],
            "resources": ["helmreleases"],
            "verbs": ["create", "delete", "get", "list", "patch", "update", "watch"],
        },
    ],
    "helm-auth": [
        {
            "apiGroups": [""],
            "resources": ["secrets"],
            "verbs": ["create", "delete", "get", "list", "patch", "update", "watch"],
        },
        {
            "apiGroups": ["security.awc.cloudera.com"],
            "resources": ["authconfigs"],
            "verbs": ["create", "delete", "get", "list", "patch", "update", "watch"],
        },
        {
            "apiGroups": ["source.toolkit.fluxcd.io"],
            "resources": ["helmrepositories"],
            "verbs": ["create", "delete", "get", "list", "patch", "update", "watch"],
        },
        {
            "apiGroups": ["helm.toolkit.fluxcd.io"],
            "resources": ["helmreleases"],
            "verbs": ["create", "delete", "get", "list", "patch", "update", "watch"],
        },
    ],
}


def load_form(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected mapping at top level")
    if data.get("version") != "v1":
        raise ValueError(f"{path}: unsupported version {data.get('version')!r}, want v1")
    for key in ("directory", "engine", "imageCatalog", "chartCatalog", "helm"):
        if key not in data:
            raise ValueError(f"{path}: missing required key {key!r}")
    return data


def validate_optional_schema(form: dict[str, Any], schema_path: Path | None) -> None:
    if schema_path is None or not schema_path.is_file():
        return
    try:
        import jsonschema
    except ImportError:
        print("warning: jsonschema not installed; skipping schema validation", file=sys.stderr)
        return
    with schema_path.open(encoding="utf-8") as handle:
        schema = yaml.safe_load(handle)
    jsonschema.validate(form, schema)


def _indent_block(text: str, spaces: int) -> str:
    pad = " " * spaces
    lines = text.rstrip("\n").split("\n")
    return "\n".join(pad + line if line else "" for line in lines)


def build_engine_template(form: dict[str, Any]) -> str | None:
    if form.get("template"):
        return str(form["template"]).rstrip() + "\n"

    features = form.get("features") or {}
    creds = features.get("generatedCredentials") or {}
    auth = features.get("authConfig") or {}
    parts: list[str] = []

    if creds.get("enabled"):
        username = creds.get("username", "admin")
        suffix = creds.get("secretSuffix", "-auth")
        pwd_len = int(creds.get("passwordLength", 24))
        parts.append(
            f"""{{- $password := randAlphaNum .Metadata.Name {pwd_len} }}
apiVersion: v1
kind: Secret
metadata:
  name: {{{{ .Metadata.Name }}}}{suffix}
  labels:
    ace.cloudera.com/provides: credentials
data:
  username: {{{{ b64enc "{username}" }}}}
  password: {{{{ b64enc $password }}}}"""
        )
        extra = creds.get("extraB64EncData") or {}
        for key, expr in extra.items():
            parts[-1] += f"\n  {key}: {{{{ b64enc {expr} }}}}"
        parts[-1] += "\ntype: Opaque"

    if auth.get("enabled"):
        config_key = auth.get("configKey", "istioEnabled")
        if parts:
            parts.append("---")
        parts.append(
            f"""apiVersion: {AUTH_API}
kind: AuthConfig
metadata:
  name: default
spec:
  meshMode: Ambient
  enableAWCAuth: {{{{ .Config.{config_key} }}}}"""
        )

    if not parts:
        return None
    return "\n".join(parts) + "\n"


def normalize_dependency_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Normalize a dependencies.entries[] item for Engine.spec.dependencies."""
    dep: dict[str, Any] = {
        "name": entry["name"],
        "engine": entry["engine"],
        "type": entry.get("type", "ref"),
    }
    if entry.get("version") is not None:
        dep["version"] = str(entry["version"])
    if entry.get("minimumVersion") is not None:
        dep["minimumVersion"] = entry["minimumVersion"]
    if entry.get("config"):
        dep["config"] = entry["config"]
    return dep


def resolve_engine_dependencies(form: dict[str, Any]) -> list[dict[str, Any]] | None:
    """
    Engine dependencies from form.dependencies.entries (preferred) or engine.dependencies.
    Matches polaris/hms/cde patterns: auto | ref | optional.
    """
    deps_block = form.get("dependencies") or {}
    entries = deps_block.get("entries")
    if entries:
        return [normalize_dependency_entry(e) for e in entries]
    engine_deps = form.get("engine", {}).get("dependencies")
    if engine_deps:
        return engine_deps
    return None


def dependency_blueprint_instance(dep: dict[str, Any]) -> dict[str, Any] | None:
    """Blueprint lists ref/optional deps; auto deps stay private to the engine (Polaris/HMS)."""
    dep_type = dep.get("type", "ref")
    if dep_type == "auto":
        return None
    inst: dict[str, Any] = {
        "name": dep["name"],
        "engine": dep["engine"],
    }
    if dep.get("minimumVersion") is not None:
        inst["minimumVersion"] = str(dep["minimumVersion"])
    elif dep.get("version") is not None:
        inst["minimumVersion"] = str(dep["version"])
    else:
        inst["minimumVersion"] = "0.0.0"
    return inst


def build_blueprint_instances(form: dict[str, Any]) -> list[dict[str, Any]]:
    bp = form.get("blueprint") or {}
    if bp.get("instances"):
        return list(bp["instances"])

    engine = form["engine"]
    instance_name = bp.get("instanceName") or form["directory"]
    version = str(bp.get("minimumVersion", "0.0.0"))

    instances: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(inst: dict[str, Any] | None) -> None:
        if not inst:
            return
        key = inst["name"]
        if key in seen:
            return
        seen.add(key)
        instances.append(inst)

    for ex in bp.get("existingEngines") or []:
        add(
            {
                "name": ex["name"],
                "engine": ex["engine"],
                "minimumVersion": str(ex.get("minimumVersion", ex.get("version", "0.0.0"))),
            }
        )

    for extra in bp.get("additionalInstances") or []:
        add(
            {
                "name": extra["name"],
                "engine": extra["engine"],
                "minimumVersion": str(extra.get("minimumVersion", extra.get("version", "0.0.0"))),
            }
        )

    for dep in resolve_engine_dependencies(form) or []:
        add(dependency_blueprint_instance(dep))

    add(
        {
            "name": instance_name,
            "engine": engine["name"],
            "minimumVersion": version,
        }
    )
    return instances


def render_engine_yaml(form: dict[str, Any]) -> str:
    engine = form["engine"]
    helm = form["helm"]
    install_retries = helm.get("installRetries", 3)
    upgrade_retries = helm.get("upgradeRetries", 3)
    template_body = build_engine_template(form)
    engine_deps = resolve_engine_dependencies(form)

    doc: dict[str, Any] = {
        "apiVersion": ACE_API,
        "kind": "Engine",
        "metadata": {"name": engine["name"]},
        "spec": {
            "displayName": engine["displayName"],
            "description": engine["description"].strip()
            if isinstance(engine["description"], str)
            else engine["description"],
        },
    }
    if engine.get("operator"):
        doc["spec"]["operator"] = engine["operator"]
    if engine_deps:
        doc["spec"]["dependencies"] = engine_deps
    if form.get("provides"):
        doc["spec"]["provides"] = form["provides"]
    if template_body:
        doc["spec"]["template"] = template_body.rstrip("\n") + "\n"
    if form.get("configSchema"):
        doc["spec"]["configSchema"] = form["configSchema"]
    if form.get("healthChecks"):
        doc["spec"]["healthChecks"] = form["healthChecks"]
    doc["spec"]["imageCatalog"] = form["imageCatalog"]["name"]
    doc["spec"]["chartCatalog"] = form["chartCatalog"]["name"]
    doc["spec"]["releases"] = [
        {
            "chartID": helm["chartID"],
            "values": helm["values"].rstrip("\n") + "\n",
            "install": {"remediation": {"retries": install_retries}},
            "upgrade": {"remediation": {"retries": upgrade_retries}},
        }
    ]

    return yaml.dump(doc, sort_keys=False, default_flow_style=False, width=1000)


def render_image_catalog(form: dict[str, Any]) -> str:
    ic = form["imageCatalog"]
    doc = {
        "apiVersion": ACE_API,
        "kind": "ImageCatalog",
        "metadata": {"name": ic["name"]},
        "spec": {"images": ic["images"]},
    }
    return yaml.dump(doc, sort_keys=False, default_flow_style=False)


def render_chart_catalog(form: dict[str, Any]) -> str:
    cc = form["chartCatalog"]
    doc = {
        "apiVersion": ACE_API,
        "kind": "ChartCatalog",
        "metadata": {"name": cc["name"]},
        "spec": {"charts": cc["charts"]},
    }
    return yaml.dump(doc, sort_keys=False, default_flow_style=False)


def render_capabilities(form: dict[str, Any]) -> str | None:
    caps = form.get("capabilities") or []
    if not caps:
        return None
    chunks: list[str] = []
    for cap in caps:
        meta = cap.get("metadata") or {}
        name = meta.get("name")
        if not name:
            raise ValueError("capabilities[] entry missing metadata.name")
        doc = {
            "apiVersion": ACE_API,
            "kind": "Capability",
            "metadata": {"name": name},
            "spec": cap.get("spec", {}),
        }
        chunks.append("---\n" + yaml.dump(doc, sort_keys=False, default_flow_style=False))
    return "".join(chunks).lstrip("---\n")


def render_role(form: dict[str, Any]) -> str | None:
    rbac = form.get("rbac") or {}
    preset = rbac.get("preset", "helm-auth")
    if preset == "none":
        return None

    directory = form["directory"]
    role_name = rbac.get("clusterRoleName") or f"{directory}-engine-role"
    binding_name = f"{role_name}-binding"
    rules = RBAC_RULES.get(preset)
    if rules is None:
        raise ValueError(f"unknown rbac preset {preset!r}")

    binding = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRoleBinding",
        "metadata": {"name": binding_name},
        "roleRef": {
            "apiGroup": "rbac.authorization.k8s.io",
            "kind": "ClusterRole",
            "name": role_name,
        },
        "subjects": [
            {
                "kind": "ServiceAccount",
                "name": "ace-operator-controller-manager",
                "namespace": "ace-operator-system",
            }
        ],
    }
    role = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "ClusterRole",
        "metadata": {"name": role_name},
        "rules": rules,
    }
    return (
        "---\n"
        + yaml.dump(binding, sort_keys=False, default_flow_style=False)
        + "---\n"
        + yaml.dump(role, sort_keys=False, default_flow_style=False)
    )


def render_blueprint(form: dict[str, Any]) -> str | None:
    bp = form.get("blueprint") or {}
    if not bp.get("enabled", True):
        return None

    engine = form["engine"]
    ht = bp.get("hardwareTier") or {}
    name = bp.get("name") or f"{form['directory']}-blueprint"

    doc: dict[str, Any] = {
        "apiVersion": ACE_API,
        "kind": "Blueprint",
        "metadata": {"name": name},
        "spec": {
            "owner": bp.get("owner", "Cloudera"),
            "description": (bp.get("description") or engine["description"]).strip(),
            "outcome": bp.get("outcome") or engine["displayName"],
            "instances": build_blueprint_instances(form),
            "hardwareTiers": [
                {
                    "name": "default",
                    "cluster": {
                        "kubernetesVersion": bp.get("kubernetesVersion", ">= 1.28.0"),
                        "nodeGroups": [
                            {
                                "id": ht.get("nodeGroupId", f"{form['directory']}-nodes"),
                                "category": "worker",
                                "displayName": ht.get("displayName", f"{engine['displayName']} Nodes"),
                                "description": ht.get(
                                    "description",
                                    f"Nodes for {engine['displayName']}.",
                                ),
                                "nodeCount": {
                                    "default": ht.get("nodeCountDefault", 1),
                                    "minimum": ht.get("nodeCountMinimum", 1),
                                    "hint": ht.get(
                                        "nodeCountHint",
                                        "Use 1 for development.",
                                    ),
                                },
                                "resources": {
                                    "minimum": {
                                        "cpu": ht.get("cpuMinimum", "2"),
                                        "memory": ht.get("memoryMinimum", "4Gi"),
                                        "hasGPU": False,
                                    },
                                    "recommended": {
                                        "cpu": ht.get("cpuRecommended", "4"),
                                        "memory": ht.get("memoryRecommended", "8Gi"),
                                        "hasGPU": False,
                                    },
                                    "hint": ht.get(
                                        "resourcesHint",
                                        "Scale based on workload requirements.",
                                    ),
                                },
                                "storage": {
                                    "disk": {
                                        "default": ht.get("diskDefault", "50Gi"),
                                        "minimum": ht.get("diskMinimum", "20Gi"),
                                        "hint": ht.get(
                                            "diskHint",
                                            "Root disk for OS and container images.",
                                        ),
                                    }
                                },
                            }
                        ],
                    },
                }
            ],
            "ui": {
                "displayName": bp.get("uiDisplayName") or engine["displayName"],
            },
        },
    }
    return yaml.dump(doc, sort_keys=False, default_flow_style=False, width=1000)


def _marketplace_version(form: dict[str, Any]) -> str:
    pub = form.get("publish") or {}
    if pub.get("version"):
        return str(pub["version"])
    bp = form.get("blueprint") or {}
    if bp.get("minimumVersion"):
        return str(bp["minimumVersion"])
    return "1.0.0"


def _blueprint_enabled(form: dict[str, Any]) -> bool:
    bp = form.get("blueprint") or {}
    return bp.get("enabled", True) and render_blueprint(form) is not None


def _blueprint_metadata(form: dict[str, Any]) -> tuple[str, str]:
    bp = form.get("blueprint") or {}
    name = bp.get("name") or f"{form['directory']}-blueprint"
    instance = bp.get("instanceName") or form["directory"]
    return name, instance


def render_mirror_yaml(form: dict[str, Any]) -> str | None:
    mirror = form.get("mirror") or {}
    pub = form.get("publish") or {}
    if mirror.get("skip"):
        return "# Mirroring skipped (mirror.skip: true).\n"
    if not mirror.get("chart") and not mirror.get("images"):
        return None

    registry = pub.get("destinationRegistry") or "REGISTRY.example.com"
    namespace = pub.get("namespace") or form["directory"]
    lines = [
        "# Mirror plan — consumed by mirror.sh (helm + skopeo).",
        "# Not an ACE CRD.",
        "",
    ]
    chart = mirror.get("chart")
    if chart:
        lines.extend(
            [
                "charts:",
                f'  - repository: "{chart.get("repoUrl", "")}"',
                f'    name: "{chart.get("name", "")}"',
                f'    version: "{chart.get("version", "")}"',
                f'    destination: "oci://{registry}/{namespace}/charts"',
                "",
            ]
        )
    else:
        lines.extend(["charts: []", ""])

    lines.append("images:")
    for img in mirror.get("images") or []:
        src = img.get("source")
        if not src:
            repo = img.get("repository", "")
            tag = img.get("tag", "")
            src = f"{img.get('registry', 'docker.io')}/{repo}:{tag}".replace("//", "/")
        dest_repo = img.get("repository") or img.get("destRepository") or "image"
        dest_tag = img.get("tag") or "latest"
        dest = f"{registry}/{namespace}/{dest_repo}:{dest_tag}"
        lines.append(f'  - source: "{src}"')
        lines.append(f'    destination: "{dest}"')
    lines.append("")
    return "\n".join(lines)


def render_mirror_sh(form: dict[str, Any]) -> str | None:
    mirror = form.get("mirror") or {}
    pub = form.get("publish") or {}
    if mirror.get("skip"):
        return (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'echo "mirror.skip is true — nothing to mirror."\n'
        )
    chart = mirror.get("chart")
    images = mirror.get("images") or []
    if not chart and not images:
        return None

    registry = pub.get("destinationRegistry") or "${REGISTRY:?set REGISTRY}"
    namespace = pub.get("namespace") or form["directory"]
    dest_charts = f"oci://{registry}/{namespace}/charts"

    lines = [
        "#!/usr/bin/env bash",
        "# Copies charts and images from mirror.yaml / form inputs into partner OCI registry.",
        "# Requires: helm, skopeo, registry login (helm registry login / skopeo login).",
        "set -euo pipefail",
        'DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
        'WORK="$(mktemp -d)"; trap \'rm -rf "$WORK"\' EXIT',
        f'DEST_CHARTS="{dest_charts}"',
        f'REGISTRY="${{REGISTRY:-{registry}}}"',
        f'NAMESPACE="${{NAMESPACE:-{namespace}}}"',
        "",
    ]

    if chart:
        repo_url = chart.get("repoUrl", "")
        name = chart.get("name", "")
        version = chart.get("version", "")
        if repo_url.startswith("oci://"):
            lines.append(f'helm pull "{repo_url}/{name}" --version "{version}" --destination "$WORK"')
        else:
            lines.append(
                f'helm pull "{name}" --repo "{repo_url}" --version "{version}" --destination "$WORK"'
            )
        lines.extend(
            [
                'for f in "$WORK"/*.tgz; do',
                '  [ -e "$f" ] || continue',
                '  helm push "$f" "$DEST_CHARTS"',
                "done",
                "",
            ]
        )

    for img in images:
        src = img.get("source")
        if not src:
            reg = img.get("registry", "docker.io")
            repo = img.get("repository", "")
            tag = img.get("tag", "")
            src = f"{reg}/{repo}:{tag}"
        dest_repo = img.get("repository") or "image"
        dest_tag = img.get("tag") or "latest"
        lines.append(
            f'skopeo copy --all "docker://{src}" '
            f'"docker://${{REGISTRY}}/${{NAMESPACE}}/{dest_repo}:{dest_tag}"'
        )

    lines.extend(['echo "Mirroring complete."', ""])
    return "\n".join(lines)


def render_publish_sh(form: dict[str, Any]) -> str | None:
    pub = form.get("publish") or {}
    if not pub.get("enabled"):
        return None

    engine_name = form["engine"]["name"]
    version = _marketplace_version(form)
    registry = pub.get("destinationRegistry") or "registry.partner-corp.example.com"
    namespace = pub.get("namespace") or form["directory"]
    schema_version = int(pub.get("schemaVersion", 1))
    skip_meta = pub.get("skipImagesAndChartsOnPublish", True)
    bp_enabled = _blueprint_enabled(form)
    bp_name, bp_instance = _blueprint_metadata(form)

    skip_args = "--skip-images --skip-charts" if skip_meta else ""

    lines = [
        "#!/usr/bin/env bash",
        "# Validates and publishes this engine bundle to partner OCI via awc-marketplace CLI.",
        "#",
        "#   ./publish.sh           # dry run",
        "#   ./publish.sh --push    # push (registry/VPN login required)",
        "#",
        "# Env: AWC_MARKETPLACE, REGISTRY, NAMESPACE, SCHEMA_VERSION, VERSION",
        "set -euo pipefail",
        'DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
        'AWC="${AWC_MARKETPLACE:-awc-marketplace}"',
        f'REGISTRY="${{REGISTRY:-{registry}}}"',
        f'NAMESPACE="${{NAMESPACE:-{namespace}}}"',
        f'SCHEMA_VERSION="${{SCHEMA_VERSION:-{schema_version}}}"',
        f'VERSION="${{VERSION:-{version}}}"',
        "PUSH=()",
        'if [ "${1:-}" = "--push" ]; then PUSH=(--push); fi',
        "",
        'echo "==> Validating"',
        '"$AWC" validate "$DIR"',
    ]
    if bp_enabled:
        lines.append('"$AWC" validate --blueprint "$DIR/blueprint.yaml"')

    if skip_meta:
        lines.extend(["", f"SKIP=({skip_args})", ""])
    else:
        lines.extend(["", "SKIP=()", ""])

    lines.extend(
        [
            f'echo "==> Publishing engine {engine_name} $VERSION"',
            '"$AWC" publish --version "$VERSION" --namespace "$NAMESPACE" \\',
            '  --destination-registry "$REGISTRY" --schema-version "$SCHEMA_VERSION" \\',
            '  "${SKIP[@]}" ${PUSH[@]+"${PUSH[@]}"} --force "$DIR"',
        ]
    )

    if bp_enabled:
        lines.extend(
            [
                "",
                f'echo "==> Publishing blueprint {bp_name} $VERSION"',
                '"$AWC" publish --version "$VERSION" --namespace "$NAMESPACE" \\',
                '  --destination-registry "$REGISTRY" --schema-version "$SCHEMA_VERSION" \\',
                f'  --blueprint "$DIR/blueprint.yaml" \\',
                f'  --instance "{bp_instance}={engine_name}:$VERSION" \\',
                '  ${PUSH[@]+"${PUSH[@]}"} --force',
            ]
        )

    lines.extend(
        [
            "",
            'if [ "${#PUSH[@]}" -gt 0 ]; then',
            '  "$AWC" catalog fetch --registry "$REGISTRY" --namespace "$NAMESPACE"',
            '  echo "Pushed. Partner AWC catalog sync takes ~60s."',
            "else",
            '  echo "Dry run complete. Re-run with --push to publish."',
            "fi",
            "",
        ]
    )
    return "\n".join(lines)


def render_oci_register_config(form: dict[str, Any]) -> str | None:
    oci = form.get("ociRegister") or {}
    if not oci.get("enabled"):
        return None

    doc: dict[str, Any] = {
        "registryHost": oci.get("registryHost", "REGISTRY.example.com"),
        "marketplacePrefix": oci.get(
            "marketplacePrefix", f"{form['directory']}/marketplace"
        ),
    }
    auth = oci.get("auth") or {"kind": "basic", "username": "user", "passwordFile": "/path/to/secret"}
    doc["auth"] = auth

    header = (
        "# Example awc-oci-register config (apply on AWC *control plane* cluster).\n"
        "# https://github.com/agupta-git/awc-oci-register\n"
        "#\n"
        "#   awc-oci-register verify -f oci-register.config.yaml\n"
        "#   awc-oci-register apply  -f oci-register.config.yaml\n"
        "#\n"
        "# Until CCF-95 lands, this registers pull creds + MARKETPLACE_REGISTRIES.\n"
        "---\n"
    )
    return header + yaml.dump(doc, sort_keys=False, default_flow_style=False)


def render_example_instance(form: dict[str, Any]) -> str:
    ex = form.get("exampleInstance") or {}
    name = ex.get("name") or form["directory"]
    doc: dict[str, Any] = {
        "apiVersion": ACE_API,
        "kind": "EngineInstance",
        "metadata": {"name": name},
        "spec": {"engine": form["engine"]["name"]},
    }
    if ex.get("config"):
        doc["spec"]["config"] = ex["config"]
    return yaml.dump(doc, sort_keys=False, default_flow_style=False)


def render_readme(form: dict[str, Any]) -> str | None:
    readme_cfg = form.get("readme") or {}
    if readme_cfg.get("enabled") is False:
        return None
    engine = form["engine"]
    directory = form["directory"]
    readme = form.get("readme") or {}
    title = readme.get("title") or f"{engine['displayName']} ACE Engine"
    arch = readme.get("architectureNotes", "").strip()
    auth = readme.get("authenticationNotes", "").strip()

    lines = [
        f"# {title}",
        "",
        engine["description"].strip() if isinstance(engine["description"], str) else "",
        "",
        "## Generated plugin",
        "",
        f"This directory was produced from [`input_form.yaml`](../tools/engine-onboarding/examples/{directory}.input_form.yaml) "
        f"via [`generate_engine.py`](../tools/engine-onboarding/generate_engine.py). "
        "Edit the form and re-run the generator, or hand-edit files as needed.",
        "",
    ]
    if arch:
        lines.extend(["## Architecture", "", arch, ""])
    lines.extend(
        [
            "## Install",
            "",
            "```bash",
            f"kubectl apply -f {directory}/capabilities.yaml   # if present",
            f"kubectl apply -f {directory}/role.yaml            # if present",
            f"kubectl apply -f {directory}/imagecatalog.yaml",
            f"kubectl apply -f {directory}/chartcatalog.yaml",
            f"kubectl apply -f {directory}/engine.yaml",
            f"kubectl apply -f {directory}/blueprint.yaml      # optional",
            f"kubectl apply -f {directory}/examples/instance.yaml",
            "```",
            "",
            "See the [root README](../README.md) for platform prerequisites (ace-operator, Flux).",
            "",
        ]
    )
    pub = form.get("publish") or {}
    if pub.get("enabled"):
        lines.extend(
            [
                "## Publish to partner OCI (marketplace)",
                "",
                "After mirroring upstream chart/images (if needed):",
                "",
                "```bash",
                f"cd {directory}",
                "./publish.sh              # dry run (awc-marketplace validate)",
                "./publish.sh --push       # push (VPN + registry login)",
                "```",
                "",
                "Or from repo root:",
                "",
                "```bash",
                f"make publish-engine DIR={directory}",
                f"make publish-engine DIR={directory} PUSH=1",
                "```",
                "",
            ]
        )
    if auth:
        lines.extend(["## Authentication", "", auth, ""])
    return "\n".join(lines) + "\n"


def should_emit_mirror(form: dict[str, Any]) -> bool:
    mirror = form.get("mirror") or {}
    pub = form.get("publish") or {}
    if mirror.get("skip"):
        return bool(pub.get("enabled"))
    return bool(mirror.get("chart") or mirror.get("images") or pub.get("enabled"))


def write_file(path: Path, content: str, dry_run: bool, force: bool) -> None:
    if path.exists() and not force and not dry_run:
        raise FileExistsError(f"{path} exists (use --force to overwrite)")
    if dry_run:
        print(f"would write {path} ({len(content)} bytes)")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"wrote {path}")


def write_executable(path: Path, content: str, dry_run: bool, force: bool) -> None:
    write_file(path, content, dry_run=dry_run, force=force)
    if dry_run or not path.exists():
        return
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def generate(form: dict[str, Any], out_dir: Path, dry_run: bool, force: bool) -> None:
    outputs: list[tuple[Path, str | None, bool]] = [
        (out_dir / "engine.yaml", render_engine_yaml(form), False),
        (out_dir / "imagecatalog.yaml", render_image_catalog(form), False),
        (out_dir / "chartcatalog.yaml", render_chart_catalog(form), False),
        (out_dir / "capabilities.yaml", render_capabilities(form), False),
        (out_dir / "role.yaml", render_role(form), False),
        (out_dir / "blueprint.yaml", render_blueprint(form), False),
        (out_dir / "examples" / "instance.yaml", render_example_instance(form), False),
        (out_dir / "README.md", render_readme(form), False),
    ]
    if should_emit_mirror(form):
        outputs.append((out_dir / "mirror.yaml", render_mirror_yaml(form), False))
        outputs.append((out_dir / "mirror.sh", render_mirror_sh(form), True))
    pub = form.get("publish") or {}
    if pub.get("enabled"):
        outputs.append((out_dir / "publish.sh", render_publish_sh(form), True))
    oci = render_oci_register_config(form)
    if oci:
        outputs.append((out_dir / "oci-register.config.example.yaml", oci, False))

    for path, content, executable in outputs:
        if content is None:
            # Do not delete hand-maintained README when readme.enabled is false.
            if path.name == "README.md":
                continue
            if path.exists() and force and not dry_run:
                path.unlink()
                print(f"removed {path}")
            continue
        if executable:
            write_executable(path, content, dry_run=dry_run, force=force)
        else:
            write_file(path, content, dry_run=dry_run, force=force)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate ace-engines plugin from input_form.yaml")
    parser.add_argument("--form", type=Path, required=True, help="Path to input_form.yaml")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="ace-engines repository root (default: auto-detect)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Override output directory (default: {repo-root}/{directory})",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parent / "input_form.schema.yaml",
        help="Optional JSON Schema for validation",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print planned writes only")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    form = load_form(args.form)
    validate_optional_schema(form, args.schema)
    out_dir = args.output_dir or (args.repo_root / form["directory"])
    generate(form, out_dir, dry_run=args.dry_run, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
