"""Interactive terminal wizard: asks the question graph one at a time and
writes the answers into a Session.
"""

from __future__ import annotations

import sys

from . import questions as q
from .session import Session


def run_wizard(session: Session) -> None:
    print(f"\nAWC Engine Onboarding Wizard -- session '{session.session_id}'")
    print("Answer each question; press Enter to accept the shown default; type '?' for help.\n")

    while True:
        question = session.next_question()
        if question is None:
            break
        answered, total = session.progress()
        try:
            _ask(session, question, answered, total)
            if question.id == "dependencies.hasAny" and session.answers["dependencies"]["hasAny"]:
                _collect_dependencies(session)
        except (EOFError, KeyboardInterrupt):
            session.save()
            print(f"\nStopped. Progress saved; resume with: wizard --session {session.session_id}")
            return

    print("\nAll questions answered. Run:")
    print(f"  python -m onboarding.cli generate --session {session.session_id}")
    print("to render the ACE bundle.\n")


def _ask(session: Session, question: q.Question, answered: int, total: int) -> None:
    default = question.resolved_default(session.answers)
    suffix = ""
    if question.kind == "bool":
        suffix = " [" + ("Y/n" if default else "y/N") + "]"
    elif question.choices:
        suffix = " (" + "/".join(question.choices) + ")"
        if default:
            suffix += f" [{default}]"
    elif default not in (None, ""):
        suffix = f" [{default}]"

    while True:
        print(f"[{answered + 1}/{total}] {question.prompt}{suffix}")
        example = q.EXAMPLES.get(question.id)
        if example:
            print(f"    e.g. {example}")
        raw = input("> ").strip()
        if raw == "?":
            print(f"    {question.help or 'No additional help for this question.'}\n")
            continue
        if raw == "" and default is not None:
            raw = default
        if raw == "" and question.required:
            print("    This question requires an answer.\n")
            continue
        if question.choices and str(raw) not in question.choices:
            print(f"    Please choose one of: {', '.join(question.choices)}\n")
            continue
        try:
            value = q.coerce(question, raw)
        except ValueError:
            print("    Could not parse that value, try again.\n")
            continue
        session.answer(question.id, value)
        return


def _ask_raw(prompt: str, default: str = "", required: bool = True, choices: list[str] | None = None) -> str:
    suffix = f" ({'/'.join(choices)})" if choices else ""
    if default:
        suffix += f" [{default}]"
    while True:
        print(f"{prompt}{suffix}")
        raw = input("> ").strip()
        if raw == "" and default:
            raw = default
        if raw == "" and required:
            print("    This question requires an answer.\n")
            continue
        if choices and raw not in choices:
            print(f"    Please choose one of: {', '.join(choices)}\n")
            continue
        return raw


def _ask_bool(prompt: str, default: bool = False) -> bool:
    raw = _ask_raw(prompt, default=("y" if default else "n"), required=False)
    return raw.strip().lower() in {"y", "yes", "true", "1"}


def _collect_dependencies(session: Session) -> None:
    """Repeatable loop collecting one or more dependency entries (each
    referencing ANY other Engine already on the cluster -- internal or
    external) directly into ``answers['dependencies']['items']``, bypassing
    the static question graph since the count is unbounded.
    """
    items: list[dict] = []
    index = 1
    print(
        "\nDependency details -- the 'Engine' can be any Engine resource name "
        "already present on the cluster (your own previously-onboarded engine, "
        "a Cloudera-native one, or a third-party/open-source partner engine)."
    )
    while True:
        print(f"\n-- Dependency #{index} --")
        name = _ask_raw("Short name for the dependency as used in templates (e.g. 'db', 'auth')")
        engine = _ask_raw("Name of the Engine resource it depends on (e.g. 'postgres-engine')")
        dep_type = _ask_raw(
            "Dependency wiring type? auto=private/same-lifecycle (operator auto-creates "
            "a child, invisible to the Console), optional=user may wire an existing "
            "instance or omit it, ref=user must pick an existing instance.",
            default="auto",
            choices=["auto", "optional", "ref"],
        )
        entry = {"name": name, "engine": engine, "type": dep_type}
        if dep_type != "auto":
            entry["instance"] = _ask_raw(
                f"Blueprint instance name of that existing '{engine}' (what the Console "
                "lists it as, so this engine's Blueprint entry can wire to it)?",
                default=engine.removesuffix("-engine"),
            )
        items.append(entry)
        index += 1
        if not _ask_bool("Add another dependency?", default=False):
            break
    session.answers.setdefault("dependencies", {})["entries"] = items
    session.save()


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    session_id = argv[0] if argv else "default"
    session = Session.load(session_id)
    run_wizard(session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
