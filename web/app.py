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
import os
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
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
_QUEUE_ACTIONS = {"validate", "mirror", "publish", "copy"}
_LAUNCHPAD_ABSENT = (
    "The product list cannot be loaded yet, so this only updates the list on this page. Your files stay on this computer. "
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


_COPY_ABSENT = (
    "Nothing was copied. The product list cannot be loaded yet, so this only updates the list on this page. "
    "Your files stay on this computer. The password was not stored or sent."
)
_PUBLISH_ABSENT = (
    "The product list cannot be loaded yet, so this only updates the list on this page. "
    "Your files stay on this computer. The password was not stored or sent."
)


def launchpad_queue(action: str, username: str, password_present: bool, registry: str, slug: str) -> dict:
    """Record a copy or publish click. The password itself is never accepted or stored."""
    if action not in _QUEUE_ACTIONS:
        job = _record_job(action or "publish", "failed", "That action is not available. Nothing was sent.")
        return {"error": job["detail"], "job": job}
    if not (slug or "").strip():
        job = _record_job(action, "failed", "Set the folder name on the first step before sending images. Nothing was sent.")
        return {"error": job["detail"], "job": job}
    if not (registry or "").strip():
        job = _record_job(action, "failed", "Registry host is empty. Nothing was sent.")
        return {"error": job["detail"], "job": job}
    if not (username or "").strip() or not password_present:
        job = _record_job(
            action, "failed",
            "Registry username and password are required to push. Nothing was sent. The password is not saved.",
        )
        return {"error": job["detail"], "job": job}
    if action == "copy":
        detail = _COPY_ABSENT
    elif action == "publish":
        detail = _PUBLISH_ABSENT
    else:
        detail = _LAUNCHPAD_ABSENT
    job = _record_job(action, "failed", detail)
    return {"error": job["detail"], "job": job}


def _stage_bundle(d: dict) -> dict:
    """Generate the session bundle locally. Does not upload or read VPN credentials."""
    slug = (d.get("slug") or "").strip()
    session_name = (d.get("session") or "").strip()
    if not slug:
        job = _record_job("stage", "failed", "Set the folder name on the first step before creating files. Nothing was written.")
        return {"error": job["detail"], "job": job}
    if not session_name:
        job = _record_job("stage", "failed", "Session name is required. Nothing was staged.")
        return {"error": job["detail"], "job": job}
    result = run_answers(Session.load(session_name).answers)
    if result.get("ok") is False or result.get("problems") or result.get("error"):
        detail = result.get("error") or " ".join(p["message"] for p in result.get("problems") or [])
        job = _record_job("stage", "failed", detail or "The check failed. Nothing was written.")
        return {"ok": False, "error": job["detail"], "problems": result.get("problems") or [], "job": job}
    count = len(result.get("files") or {})
    detail = (
        f"Staged {count} files for partners/{slug}/ in this UI process. "
        "Nothing was uploaded."
    )
    job = _record_job("stage", "succeeded", detail)
    return {"ok": True, "job": job, "files": count}


def launchpad_catalog(username: str, password: str, registry: str) -> dict:
    """Layout stays. This checkout does not call Partner Launchpad. The password is not stored."""
    del username, password
    return {
        "images": [],
        "partners": [],
        "registry": (registry or "").strip(),
        "message": "The product list cannot be loaded yet, so this only updates the list on this page. Your files stay on this computer.",
    }


def _qpayload(question, answers):
    default = question.resolved_default(answers)
    return {
        "id": question.id, "prompt": question.prompt, "kind": question.kind,
        "help": question.help, "choices": question.choices,
        "required": question.required, "default": default,
        "example": q.EXAMPLES.get(question.id, ""),
    }



_FORM_KEYS = ("directory", "engine", "imageCatalog", "chartCatalog", "helm")


def _plain(file: str, message: str) -> str:
    """One sentence: what is wrong, and what to change."""
    text = " ".join(str(message).split()).rstrip(".")
    found = re.search(r"Missing required field spec path '([^']+)'", text)
    if found:
        name = file or "The file"
        return f"{name} is missing {found.group(1)}. Add that field."
    found = re.search(r"forbidden registry host '([^']+)'", text)
    if found:
        return f"{file or 'A file'} points at {found.group(1)}. Use your own registry instead."
    if "Required file is missing" in text:
        return f"{file or 'A required file'} was not produced. Add the inputs that create it."
    found = re.match(r"blueprint\.(\w+) is required", text)
    if found:
        return f"The install guide needs a {found.group(1)}. Add blueprint.{found.group(1)}."
    if "at least one engine" in text:
        return "List at least one product under engines. Add an engine file name."
    if "still need" in text:
        return f"{text}. Fill that in before generating files."
    if text.startswith(("Paste ", "This ", "The ", "List ", "Set ", "Check ")):
        return f"{text}."
    if not file:
        return f"{text}."
    if text.lower().startswith(str(file).lower()):
        return f"{text}."
    return f"{file}: {text}. Fix that before generating files."


def _problem(field: str, file: str, message: str) -> dict:
    return {"field": field, "file": file, "message": _plain(file, message)}


def _fail(field: str, file: str, message: str) -> dict:
    return {"ok": False, "problems": [_problem(field, file, message)]}


def _is_input_form(data: dict) -> bool:
    return isinstance(data, dict) and data.get("version") == "v1" and "directory" in data


def _check_input_form(data: dict) -> list[str]:
    """Same checks as engine-onboarding/validate_form.py. No second schema."""
    problems: list[str] = []
    if data.get("version") != "v1":
        problems.append("The form version must be v1. Set version: v1.")
    for key in _FORM_KEYS:
        if key not in data:
            problems.append(f"The form is missing {key}. Add that section.")
    if problems:
        return problems
    import sys
    eng = str(ROOT / "engine-onboarding")
    if eng not in sys.path:
        sys.path.insert(0, eng)
    from generate_engine import validate_optional_schema

    schema = ROOT / "engine-onboarding" / "input_form.schema.yaml"
    try:
        validate_optional_schema(data, schema)
    except Exception as exc:
        detail = getattr(exc, "message", None) or str(exc)
        detail = " ".join(str(detail).split())
        if "is a required property" in detail:
            missing = detail.split()[0].strip("'")
            problems.append(f"The form is missing {missing}. Add that field.")
        else:
            problems.append(f"The form does not match the expected shape. {detail}")
    return problems


def _answers_problem(field: str, file: str, answers: dict) -> dict | None:
    q.fill_defaults(answers)
    missing = q.next_question(answers)
    if missing is None:
        return None
    prompt = missing.prompt.rstrip()
    if not prompt.endswith("."):
        prompt = prompt.rstrip("?") + "."
    where = file or "The answers"
    return _problem(field, file or missing.id, f"{where} is incomplete. {prompt} Fill that in before generating files.")


def _bundle_result(directory: Path, validation: dict, extra: dict | None = None) -> dict:
    files = {str(p.relative_to(directory)): p.read_text() for p in sorted(directory.rglob("*")) if p.is_file() and p.suffix in (".yaml", ".sh")}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, text)
    return {"files": files, "validation": validation,
            "zip": base64.b64encode(buf.getvalue()).decode(), **(extra or {})}


def run_answers(answers: dict) -> dict:
    """Validate first. Files are returned only when the check passes."""
    if not isinstance(answers, dict) or not answers:
        return _fail("yaml", "input.yaml", "Paste the product YAML first. Add partner and engine fields.")
    if _is_input_form(answers):
        problems = [_problem("yaml", "input.yaml", item) for item in _check_input_form(answers)]
        if problems:
            return {"ok": False, "problems": problems}
        return {"ok": True, "passed": "Check passed. The form has the required sections."}
    gap = _answers_problem("yaml", "input.yaml", answers)
    if gap:
        return {"ok": False, "problems": [gap]}
    try:
        manifest = normalize(answers)
    except Exception as exc:
        return _fail("yaml", "input.yaml", str(exc))
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        render_bundle(manifest, out)
        report = validate_bundle(out, manifest).as_dict()
        if not report["ok"]:
            return {"ok": False, "problems": [_problem("yaml", e["file"], e["message"]) for e in report["errors"]]}
        folder = (manifest.get("partner") or {}).get("id") or ""
        result = _bundle_result(out, report, {"folder": folder, "ok": True})
        count = len(result.get("files") or {})
        result["passed"] = f"Check passed. {count} files are ready."
        return result


def run_blueprint(blueprint_text: str, engines: dict) -> dict:
    """Validate the install guide and each engine file before any bundle is returned."""
    problems: list[dict] = []
    if not (blueprint_text or "").strip():
        return _fail("blueprint", "blueprint.input.yaml", "Paste the install guide first. Add blueprint.name and an engines list.")
    try:
        spec = yaml.safe_load(blueprint_text) or {}
    except yaml.YAMLError:
        return _fail("blueprint", "blueprint.input.yaml", "This is not valid YAML. Fix the broken line in the install guide.")
    if not isinstance(spec, dict):
        return _fail("blueprint", "blueprint.input.yaml", "The install guide must be named fields. Start with blueprint:.")
    bp = spec.get("blueprint") or {}
    for key in ("name", "owner", "displayName"):
        if not bp.get(key):
            problems.append(_problem("blueprint", "blueprint.input.yaml", f"blueprint.{key} is required"))
    components = spec.get("engines") or []
    if not components:
        problems.append(_problem("blueprint", "blueprint.input.yaml", "engines must list at least one engine"))
    for name, body in (engines or {}).items():
        label = name or "engine file"
        if not str(body or "").strip():
            problems.append(_problem(label, label, f"{label} is empty. Paste that product YAML."))
            continue
        try:
            data = yaml.safe_load(body) or {}
        except yaml.YAMLError:
            problems.append(_problem(label, label, f"{label} is not valid YAML. Fix the broken line in that file."))
            continue
        if not isinstance(data, dict):
            problems.append(_problem(label, label, f"{label} must be named fields. Start with partner: or version:."))
            continue
        if _is_input_form(data):
            for item in _check_input_form(data):
                problems.append(_problem(label, label, item))
            continue
        gap = _answers_problem(label, label, data)
        if gap:
            problems.append(gap)
    if problems:
        return {"ok": False, "problems": problems}
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        for name, body in engines.items():
            (base / Path(name).name).write_text(body)
        spec_path = base / "blueprint.input.yaml"
        spec_path.write_text(blueprint_text)
        try:
            result = compose_blueprint(spec_path, base / "out")
        except ValueError as exc:
            return _fail("blueprint", "blueprint.input.yaml", str(exc))
        reports = result.get("validation") or {}
        for name, report in reports.items():
            for err in report.get("errors") or []:
                problems.append(_problem(name, err.get("file") or name, err.get("message") or "Check failed"))
        if problems or not result.get("ok", True):
            return {"ok": False, "problems": problems or [_problem("blueprint", "blueprint.yaml", "The install guide did not pass the check. Fix the items above.")]}
        bundled = _bundle_result(Path(result["out_dir"]), reports, {"ok": True})
        count = len(bundled.get("files") or {})
        bundled["passed"] = f"Check passed. {count} files are ready."
        return bundled


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
        if url.path == "/cloudera-logo.png":
            logo = INDEX.with_name("cloudera-logo.png")
            return self._send(logo.read_bytes(), ctype="image/png")
        if url.path.startswith("/fonts/") and ".." not in url.path:
            font = (INDEX.parent / url.path.lstrip("/")).resolve()
            if font.is_file() and font.parent == (INDEX.parent / "fonts").resolve():
                return self._send(font.read_bytes(), ctype="font/ttf")
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
                               "shortName": q._get(s.answers, "partner.id") or "",
                               "question": question and _qpayload(question, s.answers)})
        if url.path == "/api/registry-answers":
            s = Session.load(qs.get("session", "default"))
            return self._send({
                "folder": q._get(s.answers, "partner.id") or "",
                "registry": q._get(s.answers, "publish.destinationRegistry") or "",
                "repository": q._get(s.answers, "publish.namespace") or "",
            })
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
            raw = d.get("yaml") or ""
            if not str(raw).strip():
                return _fail("yaml", "input.yaml", "Paste the product YAML first. Add partner and engine fields.")
            try:
                loaded = yaml.safe_load(raw)
            except yaml.YAMLError:
                return _fail("yaml", "input.yaml", "This is not valid YAML. Fix the broken line and try again.")
            if not isinstance(loaded, dict):
                return _fail("yaml", "input.yaml", "The input must be named fields. Start with partner: and engine:.")
            return run_answers(loaded)
        if path == "/api/run-blueprint":
            return run_blueprint(d["blueprint"], d.get("engines", {}))
        if path == "/api/launchpad/stage":
            return _stage_bundle(d)
        if path == "/api/launchpad/queue":
            # Presence only. The password string is dropped and never stored or logged.
            password = d.pop("password", None)
            password_present = bool(password) or bool(d.get("passwordPresent"))
            del password
            return launchpad_queue(
                d.get("action") or "",
                d.get("username") or "",
                password_present,
                d.get("registry") or "",
                d.get("slug") or "",
            )
        if path == "/api/launchpad/catalog":
            return launchpad_catalog(d.get("username") or "", d.get("password") or "", d.get("registry") or "")
        return {"error": "not found"}

    def log_message(self, *a):
        pass


_WATCH_SUFFIXES = {".py", ".html", ".css", ".js"}
_SKIP_DIRS = {".venv", "sessions", "__pycache__", "output", ".git"}


def _watch_stamp(root: Path) -> tuple:
    stamps = []
    app_py = root / "web" / "app.py"
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in _WATCH_SUFFIXES:
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.suffix == ".py" and path != app_py:
            continue
        stamps.append((str(path), path.stat().st_mtime_ns))
    return tuple(stamps)


def _serve(host: str, port: int) -> None:
    try:
        ThreadingHTTPServer((host, port), Handler).serve_forever()
    except OSError as exc:
        if exc.errno == 48:
            print("Port 8765 is already in use", file=sys.stderr)
            raise SystemExit(1) from None
        raise


def _reload(host: str, port: int) -> None:
    root = Path(__file__).resolve().parents[1]
    while True:
        env = os.environ.copy()
        env["AWC_DEV_CHILD"] = "1"
        proc = subprocess.Popen(
            [sys.executable, "-m", "web.app", "--host", host, "--port", str(port)],
            cwd=str(root),
            env=env,
            start_new_session=True,
        )
        stamp = _watch_stamp(root)
        try:
            while proc.poll() is None:
                time.sleep(0.4)
                if _watch_stamp(root) != stamp:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=5)
                    break
            else:
                raise SystemExit(proc.returncode or 0)
        except KeyboardInterrupt:
            os.killpg(proc.pid, signal.SIGTERM)
            raise SystemExit(0) from None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    if os.environ.get("AWC_DEV_CHILD") == "1":
        _serve(args.host, args.port)
        return
    _reload(args.host, args.port)


if __name__ == "__main__":
    main()
