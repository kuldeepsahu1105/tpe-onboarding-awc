"""Shared rendering primitives used by both supported onboarding input formats."""

from __future__ import annotations

from typing import Any

import yaml

MARKETPLACE_SCHEMA_VERSION = 2


def yaml_document(document: dict[str, Any], *, width: int = 1000) -> str:
    return yaml.safe_dump(document, sort_keys=False, default_flow_style=False, width=width)


def catalog_document(api_version: str, kind: str, name: str, entries: list[dict]) -> dict:
    key = {"ImageCatalog": "images", "ChartCatalog": "charts"}.get(kind)
    if key is None:
        raise ValueError(f"Unsupported catalog kind: {kind}")
    return {
        "apiVersion": api_version,
        "kind": kind,
        "metadata": {"name": name},
        "spec": {key: entries},
    }


def catalog_yaml(api_version: str, kind: str, name: str, entries: list[dict]) -> str:
    return yaml_document(catalog_document(api_version, kind, name, entries))
