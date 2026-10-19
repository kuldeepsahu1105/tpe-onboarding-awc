#!/usr/bin/env python3
"""Discover container images referenced by a Helm chart (helm template).

Ported from tpe-onboarding-awc ``awc_onboarding/onboarding/discover.py`` for
ace-engines ``input_form.yaml`` (``imageCatalog.images`` uses ``registry``).

Example::

  python3 tools/engine-onboarding/discover_images.py \\
    --repo-url https://helm.neo4j.com/neo4j --chart neo4j --version 2025.12.1

  make discover-images REPO_URL=https://helm.neo4j.com/neo4j CHART=neo4j VERSION=2025.12.1 \\
    FORM=tools/engine-onboarding/examples/neo4j.input_form.yaml WRITE=1
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import yaml


def split_image_ref(ref: str) -> dict[str, str]:
    """``quay.io/org/app:1.2`` -> ``registry``, ``repository``, ``tag``."""
    ref = str(ref).split("@", 1)[0]
    tag = "latest"
    last = ref.rsplit("/", 1)[-1]
    if ":" in last:
        ref, tag = ref.rsplit(":", 1)
    parts = ref.split("/")
    registry = "docker.io"
    if len(parts) > 1 and ("." in parts[0] or ":" in parts[0] or parts[0] == "localhost"):
        registry, parts = parts[0], parts[1:]
    return {"registry": registry, "repository": "/".join(parts), "tag": tag}


def _camel(value: str) -> str:
    parts = [p for p in re.sub(r"[/_.]", "-", str(value)).split("-") if p]
    if not parts:
        return "image"
    out = parts[0].lower() + "".join(p[:1].upper() + p[1:].lower() for p in parts[1:])
    return re.sub(r"[^a-zA-Z0-9]", "", out) or "image"


def _assign_image_ids(images: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for img in images:
        row = dict(img)
        base = _camel(row["repository"].rsplit("/", 1)[-1])
        img_id, n = base, 2
        while img_id in seen:
            img_id, n = f"{base}{n}", n + 1
        seen.add(img_id)
        row["id"] = img_id
        out.append(row)
    return out


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
    refs = [split_image_ref(ref) for ref in sorted(found) if "{{" not in ref]
    return _assign_image_ids(refs)


def render_chart(
    repo_url: str,
    chart: str,
    version: str,
    values_files: Optional[list[str]] = None,
    set_values: Optional[list[str]] = None,
) -> str:
    if not shutil.which("helm"):
        raise RuntimeError("helm is not installed; install it or pass --rendered.")
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
        if not (repo_url and chart and version):
            raise ValueError("Provide --repo-url, --chart, and --version (or --rendered).")
        text = render_chart(repo_url, chart, version, values_files, set_values)
    return images_from_rendered(text)


def write_into_form(form_path: Path, images: list[dict[str, str]]) -> None:
    """Merge discovered images into input_form.yaml under imageCatalog.images."""
    data = yaml.safe_load(form_path.read_text()) or {}
    ic = data.setdefault("imageCatalog", {})
    ic["images"] = images
    form_path.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-url", help="Helm repo URL or oci:// prefix")
    parser.add_argument("--chart", help="Chart name (or path segment for OCI)")
    parser.add_argument("--version", help="Chart version")
    parser.add_argument("--values", action="append", default=[], help="Values file (repeatable)")
    parser.add_argument("--set", action="append", dest="set_values", default=[], help="key=value (repeatable)")
    parser.add_argument("--rendered", help="Pre-rendered manifest instead of helm template")
    parser.add_argument(
        "--write",
        metavar="FORM",
        help="Merge into this input_form.yaml (imageCatalog.images)",
    )
    args = parser.parse_args(argv)

    try:
        images = discover_images(
            args.repo_url or "",
            args.chart or "",
            args.version or "",
            args.values or None,
            args.set_values or None,
            args.rendered,
        )
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(yaml.safe_dump({"imageCatalog": {"images": images}}, sort_keys=False))
    if args.write:
        path = Path(args.write)
        write_into_form(path, images)
        print(f"Wrote {len(images)} image(s) into {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
