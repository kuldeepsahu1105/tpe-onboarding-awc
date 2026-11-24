"""MCP server for the AWC Engine Onboarding Toolkit.

Exposes the same question graph / generator / validator used by the CLI
(``onboarding/cli.py``) as MCP tools, so an AI agent can conversationally
walk a partner through onboarding ANY engine (Cloudera-native, third-party,
or open-source) onto the Anywhere Cloud Ecosystem (AWC) marketplace, then
render and validate the resulting Blueprint/Engine CRD bundle.

Run it with:

    python -m mcp_server.server

and point an MCP-compatible client/agent at it over stdio.

Typical agent flow for ONE engine onboarding session:
    1. ``start_session``            -- create/resume a session
    2. loop: ``get_next_question`` + ``answer_question`` until ``is_complete``
       (or skip straight to step 3 with a ready-made YAML answers blob)
    3. ``load_answers``             -- (alternative to the Q&A loop) load a
       complete/partial answers YAML/JSON blob in one shot, autofilling
       every optional field that has a sensible default
    4. ``generate_bundle``          -- render the CRD bundle (Engine,
       Blueprint, ChartCatalog, ImageCatalog, Role, [Operator], ...)
    5. ``validate_bundle``          -- statically check the rendered bundle
       against ``standards/validator-rules.yaml`` and sizing baselines

Multiple dependencies on other engines (internal siblings from previous
runs, Cloudera-native engines, or external/third-party engines already
registered on the cluster) are handled by answering ``dependencies.hasAny``
and then calling ``add_dependency`` once per dependency -- never by bundling
more than one engine into a single session. See ``docs/AWC_CONCEPTS.md``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import yaml
from mcp.server.fastmcp import FastMCP

from onboarding import questions as q
from onboarding.generator import render_bundle
from onboarding.manifest import normalize
from onboarding.session import Session
from onboarding.validator import validate_bundle as _validate_bundle

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "output"
EXAMPLES_DIR = REPO_ROOT / "examples"
DOCS_DIR = REPO_ROOT / "docs"

mcp = FastMCP(
    "awc-engine-onboarding",
    instructions=(
        "Guides onboarding of ANY engine (Cloudera-native, third-party, or "
        "open-source) onto the Cloudera Anywhere Cloud (AWC) Ecosystem "
        "marketplace. One engine per session; an engine may depend on any "
        "number of other engines already available on the cluster. Prefer "
        "'list_examples' + 'get_example' to see a close analog before "
        "starting a fresh session, and 'get_concepts_doc' for the full AWC "
        "CRD model (Engine, Blueprint, Capability, ChartCatalog, "
        "ImageCatalog, Role, ClusterRequirements, Operator)."
    ),
)


def _out_dir_for(manifest: dict, out: Optional[str]) -> Path:
    return Path(out) if out else DEFAULT_OUT / manifest["partner"]["id"] / "ace"


def _question_payload(question: q.Question) -> dict[str, Any]:
    return {
        "id": question.id,
        "prompt": question.prompt,
        "kind": question.kind,
        "help": question.help,
        "choices": question.choices,
        "required": question.required,
    }


@mcp.tool()
def start_session(session_id: str) -> dict:
    """Create (or resume) a single onboarding session for ONE engine.

    Use a short, stable id such as the partner/engine slug, e.g. "neo4j" or
    "dataspark". One product is one Engine. DataSpark's API, auth, and
    database images belong on that engine, not in separate engines. Call
    add_dependency only for a different engine already on the cluster.
    """
    session = Session.load(session_id)
    answered, total = session.progress()
    return {
        "session_id": session_id,
        "answered": answered,
        "total_applicable": total,
        "is_complete": session.is_complete(),
    }


@mcp.tool()
def get_next_question(session_id: str) -> dict:
    """Return the next unanswered applicable question for this session, or
    ``{"done": true}`` if every applicable question already has an answer."""
    session = Session.load(session_id)
    question = session.next_question()
    if question is None:
        return {"done": True}
    return {"done": False, "question": _question_payload(question)}


@mcp.tool()
def answer_question(session_id: str, question_id: str, value: Any) -> dict:
    """Record the answer to one question (by its dotted id, e.g.
    'engine.template') and persist the session. Returns the next question."""
    session = Session.load(session_id)
    session.answer(question_id, value)
    question = session.next_question()
    return {
        "saved": True,
        "next": None if question is None else _question_payload(question),
    }


@mcp.tool()
def add_dependency(
    session_id: str,
    name: str,
    engine: str,
    dep_type: str = "auto",
    instance: Optional[str] = None,
    minimum_version: Optional[str] = None,
) -> dict:
    """Add ONE dependency this engine has on another engine already (or
    about to be) available on the cluster -- internal sibling, Cloudera
    native engine, or external/third-party engine. Call once per dependency;
    an engine may have any number of them.

    dep_type:
      - "auto": private, same-lifecycle dependency; the AWC operator
        auto-creates/owns the child instance. Invisible to the Console.
      - "optional": optional runtime reference.
      - "ref": required runtime reference.

    instance: optional real target EngineInstance name for the example binding.
    minimum_version: optional verified engine version floor for ref/optional.
    Listing an instance in a Blueprint does not establish a runtime binding.
    """
    session = Session.load(session_id)
    entries = q._get(session.answers, "dependencies.entries") or []
    entries.append({"name": name, "engine": engine, "type": dep_type, "instance": instance,
                    "runtimeInstance": instance, "minimumVersion": minimum_version})
    q.set_answer(session.answers, "dependencies.hasAny", True)
    q.set_answer(session.answers, "dependencies.entries", entries)
    session.save()
    return {"saved": True, "dependencies": entries}


@mcp.tool()
def load_answers(session_id: str, answers_yaml: str) -> dict:
    """Load a complete or partial answers blob (YAML or JSON text, same
    shape as the files in examples/*.input.yaml) into a session in one shot,
    auto-filling every optional/defaultable question that was left out.
    Returns the still-missing required question, if any.
    """
    session = Session.load(session_id)
    session.answers = yaml.safe_load(answers_yaml) or {}
    q.fill_defaults(session.answers)
    session.save()
    missing = session.next_question()
    return {
        "is_complete": missing is None,
        "missing": None if missing is None else _question_payload(missing),
    }


@mcp.tool()
def get_status(session_id: str) -> dict:
    """Progress summary: how many applicable questions are answered, and
    whether the session is ready for 'generate_bundle'."""
    session = Session.load(session_id)
    answered, total = session.progress()
    question = session.next_question()
    return {
        "answered": answered,
        "total_applicable": total,
        "is_complete": question is None,
        "next": None if question is None else _question_payload(question),
    }


@mcp.tool()
def generate_bundle(session_id: str, out_dir: Optional[str] = None) -> dict:
    """Render the full AWC CRD bundle (Engine, Blueprint, ChartCatalog,
    ImageCatalog, Role, [Operator]) for a complete session. Fails with the
    still-missing question if the session isn't complete yet."""
    session = Session.load(session_id)
    missing = session.next_question()
    if missing is not None:
        return {"ok": False, "error": f"session incomplete, still need '{missing.id}'"}
    manifest = normalize(session.answers)
    out = _out_dir_for(manifest, out_dir)
    files = render_bundle(manifest, out)
    (out.parent / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return {"ok": True, "out_dir": str(out), "files": sorted(files)}


@mcp.tool()
def validate_bundle(session_id: str, out_dir: Optional[str] = None) -> dict:
    """Statically validate a previously-rendered bundle against
    standards/validator-rules.yaml and standards/sizing-baselines.yaml."""
    session = Session.load(session_id)
    manifest = normalize(session.answers)
    out = _out_dir_for(manifest, out_dir)
    if not out.is_dir():
        return {"ok": False, "error": f"no bundle at {out} -- call generate_bundle first"}
    result = _validate_bundle(out, manifest)
    return result.as_dict()


@mcp.tool()
def onboard_engine(session_id: str, answers_yaml: str, out_dir: Optional[str] = None) -> dict:
    """One-shot convenience tool: load a complete answers blob, render the
    bundle, and validate it -- equivalent to 'python -m onboarding.cli all'.
    Use this when the agent (or the partner) already has a filled-in
    input.yaml rather than wanting a turn-by-turn Q&A."""
    load_result = load_answers(session_id, answers_yaml)
    if not load_result["is_complete"]:
        return {"ok": False, "error": "answers incomplete", **load_result}
    gen_result = generate_bundle(session_id, out_dir)
    if not gen_result["ok"]:
        return gen_result
    val_result = validate_bundle(session_id, out_dir)
    return {"ok": val_result.get("ok", False), "generate": gen_result, "validate": val_result}


@mcp.tool()
def compose_blueprint(blueprint_yaml_path: str, out_dir: Optional[str] = None) -> dict:
    """Build ONE Blueprint from a blueprint input file listing its engines.
    Each listed engine's input.yaml is rendered and validated, and a single
    blueprint.yaml wiring them together is emitted. A one-engine app such as
    DataSpark or Phoenix AI does not need this; generate that input.yaml
    directly."""
    from onboarding.blueprint_composer import compose_blueprint as _compose

    return _compose(Path(blueprint_yaml_path), Path(out_dir) if out_dir else DEFAULT_OUT)


@mcp.tool()
def discover_images(
    repo_url: str, chart: str, version: str, set_values: Optional[list[str]] = None
) -> list[dict]:
    """Run `helm template` on an upstream chart and return every container
    image it deploys ({source, repository, tag}). Paste the result under
    `images:` in the engine input.yaml so mirror.sh/imagecatalog cover all of
    them. Pass required chart values as set_values, e.g. ["neo4j.name=x"].
    Needs `helm` on PATH."""
    from onboarding.discover import discover_images as _d

    return _d(repo_url, chart, version, None, set_values)


@mcp.tool()
def list_examples() -> list[str]:
    """List the bundled golden-example input.yaml files (DataSpark, Neo4j,
    StarRocks, PuppyGraph, PhoenixAI) covering every template class, as a
    reference before onboarding a new engine."""
    names = sorted(p.stem.replace(".input", "") for p in EXAMPLES_DIR.glob("*.input.yaml"))
    return names


@mcp.tool()
def get_example(name: str) -> str:
    """Return the raw input.yaml text for one bundled example (see
    list_examples), to use as a starting template for a similar engine."""
    path = EXAMPLES_DIR / f"{name}.input.yaml"
    if not path.is_file():
        raise ValueError(f"No such example '{name}'. Call list_examples() for valid names.")
    return path.read_text()


@mcp.tool()
def get_reference_package(name: str) -> dict[str, str]:
    """Get the hand-authored Qbeast reference files, including its prerequisites.

    Unlike get_example, these are final manifests, not generator inputs.
    Available package: qbeast.
    """
    from onboarding.reference_package import reference_files

    return {path: content.decode("utf-8") for path, content in reference_files(name).items()}


@mcp.tool()
def get_concepts_doc() -> str:
    """Return docs/AWC_CONCEPTS.md -- the full AWC CRD model (Engine,
    Blueprint, Capability, ChartCatalog, ImageCatalog, Role,
    ClusterRequirements, Operator, and how dependencies/template classes
    work) that every question in this toolkit maps back to."""
    return (DOCS_DIR / "AWC_CONCEPTS.md").read_text()


@mcp.tool()
def get_onboarding_guide() -> str:
    """Return docs/ONBOARDING_GUIDE.md -- the step-by-step human-readable
    walkthrough of onboarding one engine, for when an agent wants to narrate
    the process or a human wants to self-serve without the agent."""
    return (DOCS_DIR / "ONBOARDING_GUIDE.md").read_text()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
