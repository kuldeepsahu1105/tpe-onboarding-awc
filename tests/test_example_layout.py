from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import unittest
from urllib.request import urlopen

import yaml


ROOT = Path(__file__).resolve().parents[1]


class ExampleLayoutTests(unittest.TestCase):
    def test_self_hosted_package_keeps_its_instance(self):
        package = ROOT / "tpe-onboarding"
        engine = yaml.safe_load((package / "engine.yaml").read_text())
        instance = yaml.safe_load((package / "examples/instance.yaml").read_text())
        self.assertEqual(instance["spec"]["engine"], engine["metadata"]["name"])
        self.assertFalse((ROOT / "examples/tpe-onboarding").exists())

    def test_form_server_exposes_canonical_example(self):
        directory = ROOT / "engine-onboarding"
        handler = partial(SimpleHTTPRequestHandler, directory=str(directory))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(base + "/web/") as response:
                self.assertIn(b"form-app.js", response.read())
            with urlopen(base + "/examples/input_form.minimal.example.yaml") as response:
                self.assertEqual(yaml.safe_load(response.read())["version"], "v1")
            with urlopen(base + "/web/input_form.ui.schema.json") as response:
                self.assertEqual(response.status, 200)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
