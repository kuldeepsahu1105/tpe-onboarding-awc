#!/usr/bin/env python3
"""Build web/input_form.ui.schema.json from input_form.schema.yaml for JSON Editor."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "input_form.schema.yaml"
OUT = ROOT / "web" / "input_form.ui.schema.json"


def main() -> None:
    schema = yaml.safe_load(SRC.read_text(encoding="utf-8"))
    schema.pop("$schema", None)
    schema["title"] = "ACE Engine onboarding (v1)"
    props = schema.setdefault("properties", {})

    props["providesYaml"] = {
        "type": "string",
        "format": "textarea",
        "title": "provides (YAML array, optional)",
        "description": "Merged into provides on export. Use when the visual editor is awkward for nested provides.",
        "options": {"input_height": "140px"},
    }
    props["configSchemaYaml"] = {
        "type": "string",
        "format": "textarea",
        "title": "configSchema (YAML object, optional)",
        "options": {"input_height": "140px"},
    }
    props["healthChecksYaml"] = {
        "type": "string",
        "format": "textarea",
        "title": "healthChecks (YAML array, optional)",
        "options": {"input_height": "100px"},
    }
    props["capabilitiesYaml"] = {
        "type": "string",
        "format": "textarea",
        "title": "capabilities (YAML array, optional)",
        "options": {"input_height": "100px"},
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
