#!/usr/bin/env python3
"""Compatibility entry point for the v1 input_form generator.

The implementation lives in onboarding.form_generator alongside the primary
input.yaml pipeline; both use onboarding.render_core for shared ACE output.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from onboarding import form_generator as _implementation

__all__ = [name for name in dir(_implementation) if not name.startswith("_")]
main = _implementation.main


def __getattr__(name: str):
    return getattr(_implementation, name)


if __name__ == "__main__":
    raise SystemExit(main())
