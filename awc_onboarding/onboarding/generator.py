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
        "capability.yaml",
        lambda m: m["capability"].get("exportsStructuredData"),
    ),
    "clusterrequirements.yaml.j2": ("clusterrequirements.yaml", lambda m: True),
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
            rendered[out_name] = _render_one(env, tpl_name, manifest)

    for out_name, content in rendered.items():
        (output_dir / out_name).write_text(content)
        if out_name.endswith(".sh"):
            (output_dir / out_name).chmod(0o755)

    return rendered


def _render_one(env: Environment, template_name: str, manifest: Manifest) -> str:
    template = env.get_template(template_name)
    text = template.render(**manifest)
    # Collapse 3+ blank lines left over from skipped Jinja blocks.
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.rstrip() + "\n"
