"""Persisted wizard session state.

Both the interactive CLI and the MCP server share the same session model so
a partner can start answering questions in one interface and finish in the
other (e.g. start in the terminal, hand off to an AI agent over MCP).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import questions as q

SESSIONS_DIR = Path(__file__).resolve().parents[1] / "sessions"


@dataclass
class Session:
    session_id: str
    answers: dict[str, Any] = field(default_factory=dict)

    @property
    def path(self) -> Path:
        return SESSIONS_DIR / f"{self.session_id}.json"

    def save(self) -> None:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.answers, indent=2))

    @classmethod
    def load(cls, session_id: str) -> "Session":
        path = SESSIONS_DIR / f"{session_id}.json"
        answers = json.loads(path.read_text()) if path.is_file() else {}
        return cls(session_id=session_id, answers=answers)

    def next_question(self) -> q.Question | None:
        return q.next_question(self.answers)

    def progress(self) -> tuple[int, int]:
        applicable = q.applicable_questions(self.answers)
        answered = sum(
            1
            for question in applicable
            if q.is_answered(question, self.answers)
        )
        return answered, len(applicable)

    def answer(self, question_id: str, raw_value: Any) -> None:
        question = q.question_by_id(question_id)
        if question is None:
            raise ValueError(f"Unknown question id '{question_id}'")
        value = q.coerce(question, raw_value)
        if question.required and question.kind == "text" and not str(value or "").strip():
            raise ValueError("This question needs an answer.")
        q.set_answer(self.answers, question_id, value)
        self.save()

    def is_complete(self) -> bool:
        return self.next_question() is None
