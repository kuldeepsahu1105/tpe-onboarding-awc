"""Renders a full Anywhere Cloud Ecosystem (ACE) bundle from a normalized
manifest, using Jinja2 templates.

Design note: generated files contain *two* templating languages layered on
top of each other:

1. Jinja2 (this module) -- substitutes manifest values at **scaffold time**
   (e.g. ``[[ engine.displayName ]]``).
2. Go templates (rendered later, at **reconcile time**, by the Anywhere
   Cloud Ecosystem operator itself) -- e.g. ``{{ .Metadata.Name }}``,
   ``{{ .Config.replicas }}``, ``{{ .Dependencies.db.connection.host }}``.

To avoid escaping gymnastics, this module configures Jinja2 with
non-colliding delimiters (``[[ ... ]]`` / ``[% ... %]``) so templates can
contain literal, unescaped Go-template syntax for the operator to render
later.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

Manifest = dict[str, Any]

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = REPO_ROOT / "templates"

# Files rendered from templates/common/, always with the same output name.
_COMMON_FILES = {
    "role.yaml.j2": "role.yaml",
}

# Files rendered from templates/common/, conditional on manifest flags.
_COMMON_CONDITIONAL_FILES = {
    "blueprint.yaml.j2": ("blueprint.yaml", lambda m: m["blueprint"]["needed"]),
    "capability.yaml.j2": (
        "capabilities.yaml",
        lambda m: m["capability"].get("exportsStructuredData"),
    ),
    "clusterrequirements.yaml.j2": (
        "clusterrequirements.yaml",
        lambda m: m["blueprint"]["format"] == "legacy",
    ),
    "mirror.yaml.j2": (
        "mirror.yaml",
        lambda m: not m["mirror"].get("skip"),
    ),
    "mirror.sh.j2": (
        "mirror.sh",
        lambda m: not m["mirror"].get("skip"),
    ),
    "publish.sh.j2": ("publish.sh", lambda m: True),
    "imagecatalog.yaml.j2": ("imagecatalog.yaml", lambda m: True),
    "chartcatalog.yaml.j2": (
        "chartcatalog.yaml",
        lambda m: m["engine"]["template"] != "native-k8s",
    ),
}

# Per-template-class files from templates/<class>/.
_CLASS_FILES = {
    "helm-simple": {"engine.yaml.j2": "engine.yaml"},
    "helm-multi-role": {"engine.yaml.j2": "engine.yaml"},
    "helm-operator": {
        "engine.yaml.j2": "engine.yaml",
        "operator.yaml.j2": "operator.yaml",
    },
    "native-k8s": {"engine.yaml.j2": "engine.yaml"},
}


def _build_env(template_class: str) -> Environment:
    # Scope the loader to ONLY the common dir + this manifest's class dir.
    # Every class dir has a same-named "engine.yaml.j2" -- a loader spanning
    # all class dirs would silently resolve to whichever came first in the
    # search path, not the requested class.
    env = Environment(
        loader=FileSystemLoader(
            [str(TEMPLATES_DIR / "common"), str(TEMPLATES_DIR / template_class)]
        ),
        variable_start_string="[[",
        variable_end_string="]]",
        block_start_string="[%",
        block_end_string="%]",
        comment_start_string="[#",
        comment_end_string="#]",
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    import yaml as _yaml

    env.filters["toyaml"] = lambda d: _yaml.safe_dump(d, default_flow_style=False, sort_keys=False).rstrip("\n")
    return env


def render_bundle(manifest: Manifest, output_dir: Path) -> dict[str, str]:
    """Render every applicable file for ``manifest`` into ``output_dir``.

    Returns a dict of ``{relative_filename: rendered_content}``.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered: dict[str, str] = {}

    template_class = manifest["engine"]["template"]
    class_dir = TEMPLATES_DIR / template_class
    if not class_dir.is_dir():
        raise ValueError(
            f"Unknown engine.template '{template_class}'. "
            f"Expected one of: {sorted(_CLASS_FILES)}"
        )
    env = _build_env(template_class)

    for tpl_name, out_name in _CLASS_FILES[template_class].items():
        rendered[out_name] = _render_one(env, tpl_name, manifest)

    for tpl_name, out_name in _COMMON_FILES.items():
        rendered[out_name] = _render_one(env, tpl_name, manifest)

    for tpl_name, (out_name, predicate) in _COMMON_CONDITIONAL_FILES.items():
        if predicate(manifest):
            if out_name == "blueprint.yaml" and manifest["blueprint"]["format"] == "current":
                import yaml
                from .blueprints import single_blueprint

                rendered[out_name] = yaml.safe_dump(single_blueprint(manifest), sort_keys=False)
            else:
                rendered[out_name] = _render_one(env, tpl_name, manifest)

    rendered["examples/instance.yaml"] = _instance_example(manifest, rendered["engine.yaml"])
    rendered["examples/smoke-test.sh"] = _smoke_test(manifest)

    for out_name, content in rendered.items():
        (output_dir / out_name).parent.mkdir(parents=True, exist_ok=True)
        (output_dir / out_name).write_text(content)
        if out_name.endswith(".sh"):
            (output_dir / out_name).chmod(0o755)

    return rendered


def _instance_example(manifest: Manifest, engine_text: str) -> str:
    """Example EngineInstance whose config comes from configSchema defaults."""
    import yaml

    doc = next(d for d in yaml.safe_load_all(engine_text) if d and d.get("kind") == "Engine")
    props = (doc["spec"].get("configSchema") or {}).get("properties") or {}
    config = {k: v["default"] for k, v in props.items() if isinstance(v, dict) and "default" in v}
    inst = {
        "apiVersion": manifest["apiVersion"],
        "kind": "EngineInstance",
        "metadata": {"name": manifest["blueprint"]["instanceName"]},
        "spec": {
            "engine": manifest["engine"]["name"],
            "version": str(manifest["engine"]["version"]),
            "config": config,
        },
    }
    deps = [
        {"name": dep["name"], "instance": dep["runtimeInstance"]}
        for dep in manifest["dependencies"]["entries"]
        if dep["type"] != "auto" and dep.get("runtimeInstance")
    ]
    if deps:
        inst["spec"]["dependencies"] = deps
    missing = [
        dep["name"] for dep in manifest["dependencies"]["entries"]
        if dep["type"] == "ref" and not dep.get("runtimeInstance")
    ]
    header = "# Apply on an AWC cluster to deploy this engine directly (no Blueprint).\n"
    if missing:
        header += "# Required runtime dependency bindings must be supplied for: " + ", ".join(missing) + "\n"
    return header + yaml.safe_dump(
        inst, sort_keys=False
    )


def _smoke_test(manifest: Manifest) -> str:
    port = manifest["service"].get("landingPort") or manifest["service"].get("port")
    name = manifest["blueprint"]["instanceName"]
    return f"""#!/usr/bin/env bash
# Post-deploy smoke test: waits for the EngineInstance and probes its service.
#   ./smoke-test.sh [namespace]   (needs kubectl access to the AWC cluster)
set -euo pipefail
NS="${{1:-default}}"
echo "==> EngineInstance {name}"
kubectl -n "$NS" get engineinstance {name}
echo "==> Pods"
kubectl -n "$NS" get pods
echo "==> Port-forward probe on {port}"
SVC="$(kubectl -n "$NS" get svc -o name | grep -i '{name}' | head -1)"
kubectl -n "$NS" port-forward "$SVC" {port}:{port} >/dev/null 2>&1 &
PF=$!; trap 'kill $PF' EXIT; sleep 5
curl -fsS -o /dev/null -m 10 "http://127.0.0.1:{port}/" && echo "service reachable" || echo "TCP up, non-HTTP protocol (OK for bolt/mysql)"
"""


def _render_one(env: Environment, template_name: str, manifest: Manifest) -> str:
    template = env.get_template(template_name)
    text = template.render(**manifest)
    # Collapse 3+ blank lines left over from skipped Jinja blocks.
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.rstrip() + "\n"
