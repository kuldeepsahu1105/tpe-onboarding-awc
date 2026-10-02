"""Web UI for the AWC onboarding toolkit (stdlib only, no AI required).

    python -m web.app [--port 8765]

Same engine as the CLI/MCP server: guided questions, paste-YAML one-shot,
and a multi-engine Blueprint composer.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import tempfile
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml

from onboarding import questions as q
from onboarding.blueprint_composer import compose_blueprint
from onboarding.generator import render_bundle
from onboarding.manifest import normalize
from onboarding.session import Session
from onboarding.validator import validate_bundle

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
INDEX = Path(__file__).with_name("index.html")


def _qpayload(question, answers):
    default = question.resolved_default(answers)
    return {
        "id": question.id, "prompt": question.prompt, "kind": question.kind,
        "help": question.help, "choices": question.choices,
        "required": question.required, "default": default,
        "example": q.EXAMPLES.get(question.id, ""),
    }


def _bundle_result(directory: Path, validation: dict, extra: dict | None = None) -> dict:
    files = {str(p.relative_to(directory)): p.read_text() for p in sorted(directory.rglob("*")) if p.is_file() and p.suffix in (".yaml", ".sh")}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, text)
    return {"files": files, "validation": validation,
            "zip": base64.b64encode(buf.getvalue()).decode(), **(extra or {})}


def run_answers(answers: dict) -> dict:
    answers = answers or {}
    q.fill_defaults(answers)
    missing = q.next_question(answers)
    if missing:
        return {"error": f"Still need '{missing.id}': {missing.prompt}"}
    manifest = normalize(answers)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        render_bundle(manifest, out)
        return _bundle_result(out, validate_bundle(out, manifest).as_dict())


def run_blueprint(blueprint_text: str, engines: dict) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        for name, text in engines.items():
            (base / Path(name).name).write_text(text)
        spec = base / "blueprint.input.yaml"
        spec.write_text(blueprint_text)
        result = compose_blueprint(spec, base / "out")
        return _bundle_result(Path(result["out_dir"]), result["validation"], {"ok": result["ok"]})


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, status=200, ctype="application/json"):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        qs = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/":
            return self._send(INDEX.read_bytes(), ctype="text/html; charset=utf-8")
        if url.path == "/api/examples":
            names = sorted(str(p.relative_to(EXAMPLES)) for p in EXAMPLES.rglob("*.yaml"))
            return self._send(names)
        if url.path == "/api/example":
            path = (EXAMPLES / qs.get("name", "")).resolve()
            if EXAMPLES.resolve() not in path.parents or not path.is_file():
                return self._send({"error": "not found"}, 404)
            return self._send({"text": path.read_text()})
        if url.path == "/api/question":
            s = Session.load(qs.get("session", "default"))
            question = s.next_question()
            done, total = s.progress()
            return self._send({"done": question is None, "answered": done, "total": total,
                               "question": question and _qpayload(question, s.answers)})
        self._send({"error": "not found"}, 404)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try:
            self._send(self._post(urlparse(self.path).path, data))
        except Exception as exc:  # surface errors to the UI, not a stack trace
            self._send({"error": str(exc)}, 400)

    def _post(self, path, d):
        if path == "/api/answer":
            s = Session.load(d["session"])
            s.answer(d["id"], d["value"])
            return {"ok": True}
        if path == "/api/back":
            s = Session.load(d["session"])
            last = None
            for item in q.QUESTIONS:
                if item.is_applicable(s.answers) and q._get(s.answers, item.id, q._SENTINEL) is not q._SENTINEL:
                    last = item
            if last is None:
                return {"id": None}
            parts = last.id.split(".")
            cur = s.answers
            for part in parts[:-1]:
                cur = cur[part]
            value = cur.pop(parts[-1])
            s.save()
            return {"id": last.id, "value": value}
        if path == "/api/dependency":
            s = Session.load(d["session"])
            entries = q._get(s.answers, "dependencies.entries") or []
            entries.append({k: d.get(k) for k in ("name", "engine", "type", "instance")})
            q.set_answer(s.answers, "dependencies.entries", entries)
            s.save()
            return {"entries": entries}
        if path == "/api/reset":
            s = Session.load(d["session"])
            s.answers = {}
            s.save()
            return {"ok": True}
        if path == "/api/run-session":
            return run_answers(Session.load(d["session"]).answers)
        if path == "/api/run-yaml":
            return run_answers(yaml.safe_load(d["yaml"]))
        if path == "/api/run-blueprint":
            return run_blueprint(d["blueprint"], d.get("engines", {}))
        return {"error": "not found"}

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    print(f"AWC Onboarding UI: http://{args.host}:{args.port}")
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
