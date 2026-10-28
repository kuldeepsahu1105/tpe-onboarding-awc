#!/usr/bin/env python3
"""Validate input_form.yaml against input_form.schema.yaml."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML required: pip install pyyaml") from exc

# Reuse loader from generator
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_engine import load_form, validate_optional_schema  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ACE engine input_form.yaml")
    parser.add_argument("--form", type=Path, required=True)
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parent / "input_form.schema.yaml",
    )
    args = parser.parse_args()
    form = load_form(args.form)
    validate_optional_schema(form, args.schema)
    print(f"OK: {args.form}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
