"""Command-line entry point for the AWC Engine Onboarding Toolkit.

    python -m onboarding.cli wizard   --session <id>
    python -m onboarding.cli answers  --session <id> --file answers.yaml
    python -m onboarding.cli generate --session <id> [--out DIR]
    python -m onboarding.cli validate --session <id> [--out DIR]
    python -m onboarding.cli all      --file answers.yaml [--out DIR]
    python -m onboarding.cli blueprint --file blueprint.input.yaml [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from . import questions as q
from .generator import render_bundle
from .manifest import normalize
from .session import Session
from .validator import validate_bundle
from .wizard import run_wizard

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "output"


def _load_answers_file(path: Path) -> dict:
    text = path.read_text()
    return yaml.safe_load(text) if path.suffix in (".yaml", ".yml") else json.loads(text)


def cmd_wizard(args: argparse.Namespace) -> int:
    session = Session.load(args.session)
    run_wizard(session)
    return 0


def cmd_answers(args: argparse.Namespace) -> int:
    session = Session.load(args.session)
    session.answers = _load_answers_file(Path(args.file))
    q.fill_defaults(session.answers)
    session.save()
    missing = q.next_question(session.answers)
    if missing:
        print(f"Answers file is incomplete -- still need: {missing.id} ({missing.prompt})")
        return 1
    print(f"Loaded complete answers into session '{args.session}'.")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    session = Session.load(args.session)
    missing = q.next_question(session.answers)
    if missing:
        print(f"Session '{args.session}' is incomplete -- still need: {missing.id}")
        print("Run 'wizard' or 'answers' first.")
        return 1
    manifest = normalize(session.answers)
    out_dir = Path(args.out) if args.out else DEFAULT_OUT / manifest["partner"]["id"] / "ace"
    files = render_bundle(manifest, out_dir)
    (out_dir.parent / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Rendered {len(files)} file(s) to {out_dir}:")
    for name in sorted(files):
        print(f"  - {name}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    session = Session.load(args.session)
    manifest = normalize(session.answers)
    out_dir = Path(args.out) if args.out else DEFAULT_OUT / manifest["partner"]["id"] / "ace"
    if not out_dir.is_dir():
        print(f"No bundle found at {out_dir} -- run 'generate' first.")
        return 1
    result = validate_bundle(out_dir, manifest)
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.ok else 1


def cmd_all(args: argparse.Namespace) -> int:
    session_id = Path(args.file).stem
    session = Session.load(session_id)
    session.answers = _load_answers_file(Path(args.file))
    q.fill_defaults(session.answers)
    session.save()
    missing = q.next_question(session.answers)
    if missing:
        print(f"Answers file is incomplete -- still need: {missing.id} ({missing.prompt})")
        return 1
    manifest = normalize(session.answers)
    out_dir = Path(args.out) if args.out else DEFAULT_OUT / manifest["partner"]["id"] / "ace"
    files = render_bundle(manifest, out_dir)
    (out_dir.parent / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"Rendered {len(files)} file(s) to {out_dir}")
    result = validate_bundle(out_dir, manifest)
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.ok else 1


def cmd_blueprint(args: argparse.Namespace) -> int:
    from .blueprint_composer import compose_blueprint

    out_root = Path(args.out) if args.out else DEFAULT_OUT
    result = compose_blueprint(Path(args.file), out_root)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def cmd_discover(args: argparse.Namespace) -> int:
    from .discover import discover_images, write_into_input

    try:
        images = discover_images(
            args.repo_url or "", args.chart or "", args.version or "",
            args.values, args.set, args.rendered,
        )
    except (RuntimeError, OSError) as exc:
        print(f"Error: {exc}")
        return 1
    print(yaml.safe_dump({"images": images}, sort_keys=False))
    if args.write:
        write_into_input(Path(args.write), images)
        print(f"Wrote {len(images)} image(s) into {args.write}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="awc-onboard", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_wizard = sub.add_parser("wizard", help="Interactively answer onboarding questions")
    p_wizard.add_argument("--session", default="default")
    p_wizard.set_defaults(func=cmd_wizard)

    p_answers = sub.add_parser("answers", help="Load a complete answers file into a session")
    p_answers.add_argument("--session", default="default")
    p_answers.add_argument("--file", required=True)
    p_answers.set_defaults(func=cmd_answers)

    p_generate = sub.add_parser("generate", help="Render the ACE bundle for a session")
    p_generate.add_argument("--session", default="default")
    p_generate.add_argument("--out")
    p_generate.set_defaults(func=cmd_generate)

    p_validate = sub.add_parser("validate", help="Statically validate a rendered bundle")
    p_validate.add_argument("--session", default="default")
    p_validate.add_argument("--out")
    p_validate.set_defaults(func=cmd_validate)

    p_all = sub.add_parser("all", help="answers + generate + validate in one shot")
    p_all.add_argument("--file", required=True)
    p_all.add_argument("--out")
    p_all.set_defaults(func=cmd_all)

    p_bp = sub.add_parser("blueprint", help="Compose ONE Blueprint from several engine input files")
    p_bp.add_argument("--file", required=True)
    p_bp.add_argument("--out")
    p_bp.set_defaults(func=cmd_blueprint)

    p_d = sub.add_parser("discover-images", help="List images a Helm chart needs (runs helm template)")
    p_d.add_argument("--repo-url")
    p_d.add_argument("--chart")
    p_d.add_argument("--version")
    p_d.add_argument("--values", action="append", help="values file (repeatable)")
    p_d.add_argument("--set", action="append", help="key=value override (repeatable)")
    p_d.add_argument("--rendered", help="pre-rendered manifest instead of running helm")
    p_d.add_argument("--write", help="merge result into this input.yaml under 'images:'")
    p_d.set_defaults(func=cmd_discover)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
