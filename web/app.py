"""Web UI for the AWC onboarding toolkit (stdlib only, no AI required).

    python -m web.app [--port 8765]

Same engine as the CLI/MCP server: guided questions, paste-YAML one-shot,
and a multi-engine Blueprint composer. Validated bundles can be saved locally;
separately confirmed operations invoke external tools.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import parse_qs, urlparse

import yaml

from onboarding import questions as q
from onboarding.blueprint_composer import compose_blueprint
from onboarding.generator import render_bundle
from onboarding.manifest import normalize
from onboarding.reference_package import DOWNLOADABLE_PACKAGES, reference_zip
from onboarding.session import Session
from onboarding.validator import validate_bundle

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
INDEX = Path(__file__).with_name("index.html")

_operations_lock = threading.Lock()
def run_local_operation(action: str, path: str, confirmed: bool) -> dict:
    """Run a reviewed local script or the external registry CLI without exposing its output."""
    registry_actions = {"registry-init", "registry-plan", "registry-verify", "registry-apply"}
    bundle_actions = {"mirror", "publish-dry-run", "publish"}
    if not isinstance(action, str) or action not in registry_actions | bundle_actions:
        return {"ok": False, "error": "Unknown operation."}
    if confirmed is not True:
        return {"ok": False, "error": "Confirm the operation before running it."}
    if not isinstance(path, str) or not path.strip() or "\0" in path:
        return {"ok": False, "error": "Enter a local path."}
    try:
        target = Path(path).expanduser()
        target = (target if target.is_absolute() else ROOT / target).resolve()
        env = os.environ.copy()
        if action in registry_actions:
            subcommand = action.removeprefix("registry-")
            if subcommand != "init" and not target.is_file():
                return {"ok": False, "error": "Registry configuration file not found."}
            if subcommand == "init" and target.exists():
                return {"ok": False, "error": "The configuration file already exists; choose a new path."}
            if subcommand == "apply":
                env["APPROVE_REGISTRY_APPLY"] = "1"
            command = ["bash", str(ROOT / "engine-onboarding/scripts/registry.sh"), subcommand, str(target)]
            help_command = f"./awc registry {subcommand} <config-path>"
        else:
            base_path = ROOT / "output"
            if base_path.is_symlink() or not base_path.is_dir():
                return {"ok": False, "error": "Save the files in output/ before running this action."}
            base = base_path.resolve()
            if target == base or base not in target.parents or not target.is_dir():
                return {"ok": False, "error": "Choose a saved files folder inside the project's output/ folder."}
            script_name = "mirror.sh" if action == "mirror" else "publish.sh"
            script = target / script_name
            if script.is_symlink() or not script.is_file():
                return {"ok": False, "error": "This folder is missing a required operation file."}
            if action == "mirror":
                command = ["bash", str(ROOT / "engine-onboarding/scripts/mirror_engine.sh"), str(target)]
                help_command = "./awc mirror <bundle-directory>"
            else:
                command = ["bash", str(ROOT / "engine-onboarding/scripts/publish_engine.sh"), str(target)]
                help_command = "./awc publish <bundle-directory>"
                if action == "publish":
                    command.append("--push")
                    env["APPROVE_PUBLISH"] = "1"
                    help_command += " --push (with APPROVE_PUBLISH=1)"
        if not _operations_lock.acquire(blocking=False):
            return {"ok": False, "error": "Another operation is running; wait for it to finish."}
        try:
            result = subprocess.run(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        finally:
            _operations_lock.release()
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": f"Cannot start operation: {exc}"}
    if result.returncode:
        return {"ok": False, "error": (
            f"Operation failed (exit {result.returncode}). Run {help_command} in a terminal for details; "
            "its output may contain sensitive information."
        )}
    message = f"{action} completed. Verify the target state before proceeding."
    if action in {"registry-plan", "registry-verify", "publish-dry-run"}:
        message += f" Output is hidden here to avoid exposing credentials. Run {help_command} in a terminal to review details."
    return {"ok": True, "message": message}


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
        bundled = _bundle_result(
            Path(result["out_dir"]), reports, {"ok": True, "folder": bp.get("name", "")}
        )
        count = len(bundled.get("files") or {})
        bundled["passed"] = f"Check passed. {count} files are ready."
        return bundled


def save_generated_bundle(data: dict) -> dict:
    """Revalidate submitted source and save generated files under output/ without overwriting."""
    kind = data.get("kind")
    if kind == "session":
        session_id = str(data.get("session") or "")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,62}", session_id):
            return {"ok": False, "error": "Session name is invalid."}
        result = run_answers(Session.load(session_id).answers)
    elif kind == "yaml":
        text = data.get("yaml")
        if not isinstance(text, str) or not text.strip():
            return {"ok": False, "error": "Paste the product YAML before saving."}
        try:
            answers = yaml.safe_load(text)
        except yaml.YAMLError:
            return {"ok": False, "error": "The product YAML is invalid. Fix it and validate again."}
        if not isinstance(answers, dict):
            return {"ok": False, "error": "The product YAML must contain named fields."}
        result = run_answers(answers)
    elif kind == "blueprint":
        blueprint = data.get("blueprint")
        engines = data.get("engines")
        if not isinstance(blueprint, str) or not isinstance(engines, dict):
            return {"ok": False, "error": "The install guide and engine files are required."}
        result = run_blueprint(blueprint, engines)
    else:
        return {"ok": False, "error": "Generate a product or Blueprint before saving."}

    if not result.get("ok") or not result.get("files"):
        issues = result.get("problems") or []
        detail = " ".join(issue.get("message", "") for issue in issues[:3]).strip()
        return {"ok": False, "error": detail or "Validated output files are not available to save."}

    folder = str(data.get("folder") or result.get("folder") or "").strip()
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", folder):
        return {"ok": False, "error": "Choose a folder name using lowercase letters, numbers, and hyphens."}

    files = result["files"]
    if len(files) > 200:
        return {"ok": False, "error": "The bundle contains too many files to save from the workbench."}
    safe_files: list[tuple[PurePosixPath, str]] = []
    total_bytes = 0
    for name, content in files.items():
        if not isinstance(name, str) or "\\" in name or "\0" in name:
            return {"ok": False, "error": "The generated bundle contains an unsafe file path."}
        relative = PurePosixPath(name)
        if (
            relative.is_absolute()
            or relative.as_posix() != name
            or any(part in ("", ".", "..") for part in relative.parts)
            or relative.suffix not in (".yaml", ".sh")
            or not isinstance(content, str)
        ):
            return {"ok": False, "error": "The generated bundle contains an unsupported file path or type."}
        total_bytes += len(content.encode("utf-8"))
        safe_files.append((relative, content))
    if not safe_files or total_bytes > 4 * 1024 * 1024:
        return {"ok": False, "error": "The generated bundle is empty or too large to save."}

    output_root = ROOT / "output"
    target = output_root / folder
    created = False
    try:
        if output_root.is_symlink():
            return {"ok": False, "error": "The output directory cannot be a symbolic link."}
        output_root.mkdir(exist_ok=True)
        if not output_root.is_dir() or output_root.resolve().parent != ROOT.resolve():
            return {"ok": False, "error": "The output directory is not a safe local folder."}
        target.mkdir()
        created = True
        for relative, content in safe_files:
            path = target.joinpath(*relative.parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            if path.suffix == ".sh":
                path.chmod(0o755)
    except FileExistsError:
        return {"ok": False, "error": f"output/{folder} already exists. Choose a new folder name; existing files were not changed."}
    except OSError as exc:
        if created:
            shutil.rmtree(target, ignore_errors=True)
        return {"ok": False, "error": f"Could not save the bundle locally: {exc}"}

    return {"ok": True, "path": f"output/{folder}", "files": len(safe_files)}


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, status=200, ctype="application/json", headers=None):
        body = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
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
        if url.path in ("/favicon.ico", "/cloudera-favicon.ico"):
            icon = INDEX.with_name("favicon.ico")
            return self._send(icon.read_bytes(), ctype="image/x-icon")
        if url.path.startswith("/fonts/") and ".." not in url.path:
            font = (INDEX.parent / url.path.lstrip("/")).resolve()
            if font.is_file() and font.parent == (INDEX.parent / "fonts").resolve():
                return self._send(font.read_bytes(), ctype="font/ttf")
        if url.path == "/api/examples":
            names = sorted(str(p.relative_to(EXAMPLES)) for p in EXAMPLES.rglob("*.yaml"))
            return self._send(names)
        if url.path == "/api/reference-package":
            name = qs.get("name", "")
            if name not in DOWNLOADABLE_PACKAGES:
                return self._send({"error": "not found"}, 404)
            try:
                package = reference_zip(name)
            except (OSError, ValueError, yaml.YAMLError) as exc:
                return self._send({"error": f"Cannot package {name}: {exc}"}, 500)
            return self._send(package, ctype="application/zip",
                              headers={"Content-Disposition": f'attachment; filename="{name}.zip"'})
        if url.path == "/api/example":
            path = (EXAMPLES / qs.get("name", "")).resolve()
            if EXAMPLES.resolve() not in path.parents or not path.is_file():
                return self._send({"error": "not found"}, 404)
            text = path.read_text()
            return self._send({"text": text})
        if url.path == "/api/question":
            s = Session.load(qs.get("session", "default"))
            question = s.next_question()
            done, total = s.progress()
            return self._send({"done": question is None, "answered": done, "total": total,
                               "shortName": q._get(s.answers, "partner.id") or "",
                               "question": question and _qpayload(question, s.answers)})
        self._send({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path in {"/api/operations", "/api/save-bundle"}:
            host = self.headers.get("Host", "")
            port = self.server.server_address[1]
            local_hosts = {f"localhost:{port}", f"127.0.0.1:{port}"}
            if (self.server.server_address[0] != "127.0.0.1" or self.client_address[0] != "127.0.0.1"
                    or host not in local_hosts or self.headers.get("Origin") != f"http://{host}"
                    or self.headers.get_content_type() != "application/json"):
                return self._send({"ok": False, "error": "Operations require the local workbench origin."}, 403)
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self._send({"ok": False, "error": "Invalid request length."}, 400)
            maximum_length = 6 * 1024 * 1024 if path == "/api/save-bundle" else 16384
            if not 0 < length <= maximum_length:
                return self._send({"ok": False, "error": "Invalid request length."}, 400)
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try:
            self._send(self._post(path, data))
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
            entries.append({**{k: d.get(k) for k in ("name", "engine", "type")},
                            "instance": d.get("instance"),
                            "runtimeInstance": d.get("instance"),
                            "minimumVersion": d.get("minimumVersion")})
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
        if path == "/api/save-bundle":
            return save_generated_bundle(d)
        if path == "/api/operations":
            return run_local_operation(d.get("action"), d.get("path"), d.get("confirmed"))
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
