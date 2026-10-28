"""Web UI for the AWC onboarding toolkit (stdlib only, no AI required).

    python -m web.app [--port 8765]

Same engine as the CLI/MCP server: guided questions, paste-YAML one-shot,
and a multi-engine Blueprint composer. Publish & OCI and OCI catalog are
local panels: they record intent and never call Partner Launchpad or ECR.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import tempfile
import threading
import uuid
import zipfile
from datetime import datetime, timezone
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

# In-memory only. Passwords are never stored. Restarting the UI clears the table.
_jobs_lock = threading.Lock()
_jobs: list[dict] = []
_QUEUE_ACTIONS = {"validate", "mirror", "publish"}
_LAUNCHPAD_ABSENT = (
    "Partner Launchpad queue client is not in this checkout. "
    "The password was not stored or sent. "
    "Use mirror.sh, then publish.sh --push, from the engine directory."
)


def _record_job(kind: str, status: str, detail: str) -> dict:
    job = {
        "id": str(uuid.uuid4()),
        "when": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "type": kind,
        "status": status,
        "detail": detail,
    }
    with _jobs_lock:
        _jobs.insert(0, job)
        del _jobs[50:]
    return job


def _creds_present(username: str, password: str) -> bool:
    return bool((username or "").strip()) and bool(password)


def launchpad_queue(action: str, username: str, password: str, registry: str, slug: str) -> dict:
    """Accept a queue click. Empty VPN credentials fail closed. Filled credentials are discarded."""
    if action not in _QUEUE_ACTIONS:
        job = _record_job(action or "queue", "failed", f"Unknown queue action: {action}")
        return {"error": job["detail"], "job": job}
    if not (slug or "").strip():
        job = _record_job(action, "failed", "Engine slug is required. Nothing was queued.")
        return {"error": job["detail"], "job": job}
    if not (registry or "").strip():
        job = _record_job(action, "failed", "Target registry is empty. Nothing was queued.")
        return {"error": job["detail"], "job": job}
    if not _creds_present(username, password):
        job = _record_job(
            action, "failed",
            "Mission Control VPN username and password are required. Nothing was sent to Partner Launchpad.",
        )
        return {"error": job["detail"], "job": job}
    job = _record_job(action, "failed", _LAUNCHPAD_ABSENT)
    return {"error": job["detail"], "job": job}


def _stage_bundle(d: dict) -> dict:
    """Generate the session bundle locally. Does not upload or read VPN credentials."""
    slug = (d.get("slug") or "").strip()
    session_name = (d.get("session") or "").strip()
    if not slug:
        job = _record_job("stage", "failed", "Engine slug is required. Nothing was staged.")
        return {"error": job["detail"], "job": job}
    if not session_name:
        job = _record_job("stage", "failed", "Session name is required. Nothing was staged.")
        return {"error": job["detail"], "job": job}
    result = run_answers(Session.load(session_name).answers)
    if result.get("error"):
        job = _record_job("stage", "failed", result["error"])
        return {"error": result["error"], "job": job}
    count = len(result.get("files") or {})
    detail = (
        f"Staged {count} files for partners/{slug}/ in this UI process. "
        "Nothing was uploaded."
    )
    job = _record_job("stage", "succeeded", detail)
    return {"ok": True, "job": job, "files": count}


def launchpad_catalog(username: str, password: str, registry: str) -> dict:
    """Catalog refresh never calls ECR. Empty credentials are a clear failure."""
    if not _creds_present(username, password):
        return {
            "images": [],
            "error": "Mission Control VPN username and password are required to refresh the program catalog. No registry was queried.",
        }
    path = (registry or "").strip()
    where = path or "the target registry"
    return {
        "images": [],
        "message": f"No images in {where} yet. This checkout does not query ECR.",
    }


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
        if url.path == "/api/launchpad/jobs":
            with _jobs_lock:
                return self._send({"jobs": list(_jobs)})
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
        if path == "/api/launchpad/stage":
            return _stage_bundle(d)
        if path == "/api/launchpad/queue":
            password = d.get("password") or ""
            result = launchpad_queue(
                d.get("action") or "",
                d.get("username") or "",
                password,
                d.get("registry") or "",
                d.get("slug") or "",
            )
            return result
        if path == "/api/launchpad/catalog":
            return launchpad_catalog(d.get("username") or "", d.get("password") or "", d.get("registry") or "")
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
