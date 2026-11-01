"""Discover the container images a Helm chart needs.

Runs ``helm template`` (or reads an already-rendered manifest file), then
collects every ``image:`` reference -- containers, initContainers, and CRD
pod specs. The result feeds the ``images:`` list of an input.yaml, which in
turn drives imagecatalog.yaml, mirror.yaml and mirror.sh.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

import yaml

from .manifest import split_image_ref


def _walk(node: Any, found: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "image" and isinstance(value, str) and value.strip():
                found.add(value.strip())
            else:
                _walk(value, found)
    elif isinstance(node, list):
        for item in node:
            _walk(item, found)


def images_from_rendered(text: str) -> list[dict[str, str]]:
    found: set[str] = set()
    for doc in yaml.safe_load_all(text):
        _walk(doc, found)
    return [split_image_ref(ref) for ref in sorted(found) if "{{" not in ref]


def render_chart(
    repo_url: str,
    chart: str,
    version: str,
    values_files: Optional[list[str]] = None,
    set_values: Optional[list[str]] = None,
) -> str:
    if not shutil.which("helm"):
        raise RuntimeError("helm is not installed; install it or pass a pre-rendered manifest.")
    if repo_url.startswith("oci://"):
        cmd = ["helm", "template", "probe", f"{repo_url.rstrip('/')}/{chart}", "--version", version]
    else:
        cmd = ["helm", "template", "probe", chart, "--repo", repo_url, "--version", version]
    for f in values_files or []:
        cmd += ["-f", f]
    for s in set_values or []:
        cmd += ["--set", s]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"helm template failed: {proc.stderr.strip()}")
    return proc.stdout


def discover_images(
    repo_url: str = "",
    chart: str = "",
    version: str = "",
    values_files: Optional[list[str]] = None,
    set_values: Optional[list[str]] = None,
    rendered_file: Optional[str] = None,
) -> list[dict[str, str]]:
    if rendered_file:
        text = Path(rendered_file).read_text()
    else:
        text = render_chart(repo_url, chart, version, values_files, set_values)
    return images_from_rendered(text)


def write_into_input(input_path: Path, images: list[dict[str, str]]) -> None:
    """Merge discovered images into an input.yaml (comments are not preserved)."""
    data = yaml.safe_load(input_path.read_text()) or {}
    data["images"] = images
    input_path.write_text(yaml.safe_dump(data, sort_keys=False))
