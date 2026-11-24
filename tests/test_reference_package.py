import io
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen
import zipfile

import yaml

from onboarding.reference_package import reference_files, reference_zip
from web.app import Handler


class ReferencePackageTests(unittest.TestCase):
    def test_zip_contains_unchanged_reference_files(self):
        files = reference_files("qbeast")
        with zipfile.ZipFile(io.BytesIO(reference_zip("qbeast"))) as archive:
            self.assertEqual(set(archive.namelist()), set(files))
            for name, data in files.items():
                self.assertEqual(archive.read(name), data)

    def test_unknown_package_and_mismatched_blueprint_fail(self):
        with self.assertRaises(ValueError):
            reference_files("../qbeast")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "examples" / "qbeast"
            folder.mkdir(parents=True)
            for name, data in reference_files("qbeast").items():
                (folder / name).write_bytes(data)
            (folder / "blueprint.yaml").write_text(
                "kind: Blueprint\nspec:\n  instances:\n    - engine: wrong\n"
            )
            with patch("onboarding.reference_package.ROOT", Path(tmp)):
                with self.assertRaisesRegex(ValueError, "does not reference"):
                    reference_zip("qbeast")

    def test_catalog_examples_and_capability_match_engine_references(self):
        files = reference_files("qbeast")
        engine = yaml.safe_load(files["engine.yaml"])["spec"]
        images = yaml.safe_load(files["imagecatalog.example.yaml"])
        charts = yaml.safe_load(files["chartcatalog.example.yaml"])
        self.assertEqual(images["metadata"]["name"], engine["imageCatalog"])
        self.assertEqual(charts["metadata"]["name"], engine["chartCatalog"])
        self.assertEqual({i["id"] for i in images["spec"]["images"]}, {"use", "portal"})
        self.assertEqual({c["id"] for c in charts["spec"]["charts"]}, {"useEndpoint", "portal"})
        capability = yaml.safe_load(files["capability.yaml"])
        provided = next(p for p in engine["provides"] if p["capability"] == capability["metadata"]["name"])
        value = yaml.safe_load(provided["value"])
        schema = capability["spec"]["schema"]
        self.assertEqual(set(schema["required"]), set(value))
        for key in schema["required"]:
            self.assertEqual(set(schema["properties"][key]["required"]), set(value[key]))

    def test_broken_role_binding_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "examples" / "qbeast"
            folder.mkdir(parents=True)
            for name, data in reference_files("qbeast").items():
                (folder / name).write_bytes(data)
            role = (folder / "role.yaml").read_text().replace(
                "  name: qbeast-ace-engine-namespaced-role\nsubjects:",
                "  name: wrong\nsubjects:",
            )
            (folder / "role.yaml").write_text(role)
            with patch("onboarding.reference_package.ROOT", Path(tmp)):
                with self.assertRaisesRegex(ValueError, "RoleBinding"):
                    reference_zip("qbeast")

    def test_http_download_and_unknown_package(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}/api/reference-package"
            with urlopen(base + "?name=qbeast") as response:
                self.assertEqual(response.headers.get_content_type(), "application/zip")
                self.assertIn("qbeast.zip", response.headers["Content-Disposition"])
                with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                    self.assertEqual(archive.read("engine.yaml"), reference_files("qbeast")["engine.yaml"])
            with self.assertRaises(HTTPError) as error:
                urlopen(base + "?name=unknown")
            self.assertEqual(error.exception.code, 404)
            error.exception.close()
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
