import http.client
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from web import app


ROOT = Path(__file__).resolve().parents[1]


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.bundle = self.root / "output" / "test"
        self.bundle.mkdir(parents=True)
        (self.bundle / "mirror.sh").write_text("#!/bin/sh\n")
        (self.bundle / "publish.sh").write_text("#!/bin/sh\n")
        self.config = self.root / "registry.yaml"
        self.config.write_text("test: true\n")
        self.root_patch = patch.object(app, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    @patch("web.app.subprocess.run")
    def test_confirmed_operations_use_argument_arrays_and_gates(self, run):
        run.return_value.returncode = 0
        cases = [
            ("registry-init", self.root / "new.yaml", "registry.sh", ["init", str(self.root / "new.yaml")]),
            ("registry-plan", self.config, "registry.sh", ["plan", str(self.config)]),
            ("registry-verify", self.config, "registry.sh", ["verify", str(self.config)]),
            ("registry-apply", self.config, "registry.sh", ["apply", str(self.config)]),
            ("mirror", self.bundle, "mirror_engine.sh", [str(self.bundle)]),
            ("publish-dry-run", self.bundle, "publish_engine.sh", [str(self.bundle)]),
            ("publish", self.bundle, "publish_engine.sh", [str(self.bundle), "--push"]),
        ]
        for action, target, script, args in cases:
            with self.subTest(action=action):
                result = app.run_local_operation(action, str(target), True)
                self.assertTrue(result["ok"])
                command = run.call_args.args[0]
                self.assertEqual(command[0], "bash")
                self.assertEqual(Path(command[1]).name, script)
                self.assertEqual(command[2:], args)
                env = run.call_args.kwargs["env"]
                if action == "registry-apply":
                    self.assertEqual(env["APPROVE_REGISTRY_APPLY"], "1")
                if action == "publish":
                    self.assertEqual(env["APPROVE_PUBLISH"], "1")

    @patch("web.app.subprocess.run")
    def test_rejects_unconfirmed_missing_and_unsafe_targets(self, run):
        self.assertFalse(app.run_local_operation("mirror", str(self.bundle), False)["ok"])
        self.assertFalse(app.run_local_operation("mirror", str(self.root), True)["ok"])
        self.assertFalse(app.run_local_operation("publish", str(self.bundle / "missing"), True)["ok"])
        self.assertFalse(app.run_local_operation("registry-plan", str(self.root / "missing"), True)["ok"])
        self.assertFalse(app.run_local_operation("registry-init", str(self.config), True)["ok"])
        self.assertFalse(app.run_local_operation([], str(self.config), True)["ok"])
        (self.bundle / "mirror.sh").unlink()
        (self.bundle / "mirror.sh").symlink_to(self.config)
        self.assertFalse(app.run_local_operation("mirror", str(self.bundle), True)["ok"])
        run.assert_not_called()

    @patch("web.app.subprocess.run")
    def test_error_does_not_expose_subprocess_output(self, run):
        run.return_value.returncode = 17
        run.return_value.stdout = "secret-token"
        run.return_value.stderr = "secret-token"
        result = app.run_local_operation("registry-plan", str(self.config), True)
        self.assertFalse(result["ok"])
        self.assertIn("exit 17", result["error"])
        self.assertNotIn("secret-token", str(result))
        self.assertEqual(run.call_args.kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs["stderr"], subprocess.DEVNULL)

    def test_origin_guard(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        port = server.server_address[1]
        body = json.dumps({"action": "registry-plan", "path": str(self.config), "confirmed": True})

        def request(origin):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            conn.request("POST", "/api/operations", body, {
                "Content-Type": "application/json", "Origin": origin,
            })
            response = conn.getresponse()
            payload = json.loads(response.read())
            conn.close()
            return response.status, payload

        with patch("web.app.run_local_operation", return_value={"ok": True}) as run:
            self.assertEqual(request("https://example.com")[0], 403)
            run.assert_not_called()
            self.assertEqual(request(f"http://127.0.0.1:{port}"), (200, {"ok": True}))
            run.assert_called_once()


class SaveBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.root_patch = patch.object(app, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    @patch("web.app.run_answers")
    def test_revalidates_yaml_and_saves_generated_files(self, run_answers):
        run_answers.return_value = {
            "ok": True,
            "folder": "example",
            "files": {"engine.yaml": "version: 1\n", "publish.sh": "#!/bin/sh\n"},
        }

        result = app.save_generated_bundle({
            "kind": "yaml",
            "yaml": "partner:\n  id: example\n",
            "folder": "example",
        })

        self.assertEqual(result, {"ok": True, "path": "output/example", "files": 2})
        run_answers.assert_called_once_with({"partner": {"id": "example"}})
        self.assertEqual((self.root / result["path"] / "engine.yaml").read_text(), "version: 1\n")
        self.assertTrue((self.root / result["path"] / "publish.sh").stat().st_mode & 0o111)

    @patch("web.app.run_answers")
    @patch("web.app.Session.load")
    def test_revalidates_saved_guided_answers(self, load_session, run_answers):
        load_session.return_value.answers = {"partner": {"id": "guided-example"}}
        run_answers.return_value = {"ok": True, "files": {"engine.yaml": "name: example\n"}}

        result = app.save_generated_bundle({
            "kind": "session", "session": "my-engine", "folder": "guided-example",
        })

        self.assertTrue(result["ok"])
        load_session.assert_called_once_with("my-engine")
        run_answers.assert_called_once_with({"partner": {"id": "guided-example"}})

    @patch("web.app.run_blueprint")
    def test_revalidates_blueprint_and_engine_inputs(self, run_blueprint):
        blueprint = "blueprint:\n  name: sample\n"
        engines = {"sample.input.yaml": "engine:\n  displayName: Sample\n"}
        run_blueprint.return_value = {"ok": True, "files": {"blueprint.yaml": "name: sample\n"}}

        result = app.save_generated_bundle({
            "kind": "blueprint", "blueprint": blueprint,
            "engines": engines, "folder": "sample",
        })

        self.assertTrue(result["ok"])
        run_blueprint.assert_called_once_with(blueprint, engines)

    @patch("web.app.run_answers")
    def test_failed_validation_does_not_create_output(self, run_answers):
        run_answers.return_value = {
            "ok": False,
            "problems": [{"message": "Required details are missing."}],
        }

        result = app.save_generated_bundle({
            "kind": "yaml", "yaml": "partner: {}\n", "folder": "example",
        })

        self.assertFalse(result["ok"])
        self.assertIn("Required details are missing", result["error"])
        self.assertFalse((self.root / "output").exists())

    @patch("web.app.run_answers")
    def test_rejects_unsafe_folder_and_file_paths(self, run_answers):
        run_answers.return_value = {"ok": True, "files": {"../outside.yaml": "bad"}}
        unsafe_folder = app.save_generated_bundle({
            "kind": "yaml", "yaml": "partner: {}\n", "folder": "../outside",
        })
        self.assertFalse(unsafe_folder["ok"])

        unsafe_file = app.save_generated_bundle({
            "kind": "yaml", "yaml": "partner: {}\n", "folder": "example",
        })
        self.assertFalse(unsafe_file["ok"])
        self.assertFalse((self.root / "output").exists())

    @patch("web.app.run_answers")
    def test_existing_folder_is_never_overwritten(self, run_answers):
        run_answers.return_value = {"ok": True, "files": {"engine.yaml": "new: true\n"}}
        destination = self.root / "output" / "example"
        destination.mkdir(parents=True)
        existing_file = destination / "engine.yaml"
        existing_file.write_text("old: true\n")

        result = app.save_generated_bundle({
            "kind": "yaml", "yaml": "partner: {}\n", "folder": "example",
        })

        self.assertFalse(result["ok"])
        self.assertIn("already exists", result["error"])
        self.assertEqual(existing_file.read_text(), "old: true\n")

    def test_save_endpoint_requires_local_origin(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(server.shutdown)
        port = server.server_address[1]
        body = json.dumps({"kind": "yaml", "yaml": "partner: {}\n", "folder": "example"})

        def request(origin):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
            conn.request("POST", "/api/save-bundle", body, {
                "Content-Type": "application/json", "Origin": origin,
            })
            response = conn.getresponse()
            payload = json.loads(response.read())
            conn.close()
            return response.status, payload

        with patch("web.app.save_generated_bundle", return_value={"ok": True}) as save:
            self.assertEqual(request("https://example.com")[0], 403)
            save.assert_not_called()
            self.assertEqual(request(f"http://127.0.0.1:{port}"), (200, {"ok": True}))
            save.assert_called_once()


class RegistryWrapperTests(unittest.TestCase):
    def test_init_and_apply_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tool = root / "fake-register"
            log = root / "calls"
            tool.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$1" >> "$FAKE_LOG"\n'
                'if [ "$1" = init ]; then printf "initialized\\n" > "$3"; fi\n'
                'if [ "$1" = verify ] && [ "${FAIL_VERIFY:-}" = 1 ]; then exit 7; fi\n'
            )
            tool.chmod(0o755)
            env = {**os.environ, "AWC_OCI_REGISTER": str(tool), "FAKE_LOG": str(log)}
            env.pop("APPROVE_REGISTRY_APPLY", None)
            config = root / "config.yaml"
            wrapper = str(ROOT / "engine-onboarding/scripts/registry.sh")

            def invoke(action, **extra):
                return subprocess.run(["bash", wrapper, action, str(config)],
                                      env={**env, **extra}, capture_output=True, text=True)

            self.assertEqual(invoke("init").returncode, 0)
            self.assertEqual(config.read_text(), "initialized\n")
            self.assertNotEqual(invoke("init").returncode, 0)
            self.assertEqual(config.read_text(), "initialized\n")
            self.assertNotEqual(invoke("apply").returncode, 0)
            self.assertNotEqual(invoke("apply", APPROVE_REGISTRY_APPLY="1", FAIL_VERIFY="1").returncode, 0)
            self.assertEqual(log.read_text().splitlines(), ["init", "verify"])
            self.assertEqual(invoke("apply", APPROVE_REGISTRY_APPLY="1").returncode, 0)
            self.assertEqual(log.read_text().splitlines(), ["init", "verify", "verify", "apply"])


if __name__ == "__main__":
    unittest.main()
