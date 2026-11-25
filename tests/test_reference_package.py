import io
from http.server import ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
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

ROOT = Path(__file__).resolve().parents[1]


class ReferencePackageTests(unittest.TestCase):
    def test_zip_contains_unchanged_fictional_sample_files(self):
        files = reference_files("sample")
        with zipfile.ZipFile(io.BytesIO(reference_zip("sample"))) as archive:
            self.assertEqual(set(archive.namelist()), set(files))
            for name, data in files.items():
                self.assertEqual(archive.read(name), data)
                self.assertEqual((archive.getinfo(name).external_attr >> 16) & 0o777,
                                 0o755 if name.endswith(".sh") else 0o644)
        with self.assertRaisesRegex(ValueError, "fictional sample"):
            reference_zip("qbeast")

    def test_sample_zip_uses_only_fictional_placeholders(self):
        files = reference_files("sample")
        self.assertNotIn("mirror.sh", files)
        self.assertNotIn("publish.sh", files)
        self.assertIn(b"not a Qbeast package", files["README.md"])
        self.assertIn(b"example.invalid", files["imagecatalog.yaml"])
        self.assertIn(b"example.invalid", files["chartcatalog.yaml"])
        self.assertNotIn(b"1.3.12", b"".join(files.values()))
        with zipfile.ZipFile(io.BytesIO(reference_zip("sample"))) as archive:
            self.assertEqual(set(archive.namelist()), set(files))

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
                    reference_files("qbeast")

    def test_catalog_examples_and_capability_match_engine_references(self):
        files = reference_files("qbeast")
        engine = yaml.safe_load(files["engine.yaml"])["spec"]
        images = yaml.safe_load(files["imagecatalog.yaml"])
        charts = yaml.safe_load(files["chartcatalog.yaml"])
        self.assertEqual(images["metadata"]["name"], engine["imageCatalog"])
        self.assertEqual(charts["metadata"]["name"], engine["chartCatalog"])
        self.assertEqual({i["id"] for i in images["spec"]["images"]}, {"use", "portal"})
        self.assertEqual({c["id"] for c in charts["spec"]["charts"]}, {"useEndpoint", "portal"})
        capability = yaml.safe_load(files["capabilities.yaml"])
        provided = next(p for p in engine["provides"] if p["capability"] == capability["metadata"]["name"])
        value = yaml.safe_load(provided["value"])
        schema = capability["spec"]["schema"]
        self.assertEqual(set(schema["required"]), set(value))
        for key in schema["required"]:
            self.assertEqual(set(schema["properties"][key]["required"]), set(value[key]))

    def test_release_and_mirror_plan_match_catalogs(self):
        files = reference_files("qbeast")
        blueprint = yaml.safe_load(files["blueprint.yaml"])
        instance = blueprint["spec"]["instances"][0]
        self.assertEqual(instance["minimumVersion"], "1.3.12")
        self.assertEqual(blueprint["spec"]["hardwareTiers"][0]["cluster"]["kubernetesVersion"], "v1.34.3")
        images = yaml.safe_load(files["imagecatalog.yaml"])["spec"]["images"]
        charts = yaml.safe_load(files["chartcatalog.yaml"])["spec"]["charts"]
        plan = yaml.safe_load(files["mirror.yaml"])
        self.assertEqual(
            {f'{i["registry"]}/{i["repository"]}:{i["tag"]}' for i in images},
            {i["source"] for i in plan["images"]},
        )
        self.assertEqual(
            {(f'oci://{c["registry"]}/{c["repository"]}', c["version"]) for c in charts},
            {(c["source"], c["version"]) for c in plan["charts"]},
        )
        self.assertIn(b"SCHEMA_VERSION=2", files["publish.sh"])

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
                    reference_files("qbeast")

    def test_mirror_propagates_plan_errors_and_runs_only_planned_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            log = root / "calls"
            yq = root / "yq"
            yq.write_text(
                '#!/bin/sh\n'
                '[ "${FAIL_PLAN:-}" != 1 ] || exit 9\n'
                'case "$1" in\n'
                '  .charts*) printf "oci://source/chart\\tchart\\t1.0\\toci://target/charts\\n" ;;\n'
                '  .images*) printf "source/image:1\\ttarget/image:1\\n" ;;\n'
                '  *) exit 2 ;;\nesac\n'
            )
            helm = root / "helm"
            helm.write_text('#!/bin/sh\nprintf "helm %s\\n" "$*" >> "$CALLS"\n')
            skopeo = root / "skopeo"
            skopeo.write_text('#!/bin/sh\nprintf "skopeo %s\\n" "$*" >> "$CALLS"\n')
            for tool in (yq, helm, skopeo):
                tool.chmod(0o755)
            env = {**os.environ, "PATH": f'{root}:{os.environ["PATH"]}',
                   "DEST_REGISTRY": "target", "DEST_NAMESPACE": "demo", "CALLS": str(log)}
            script = ROOT / "examples/qbeast/mirror.sh"
            failed = subprocess.run(["bash", str(script)], env={**env, "FAIL_PLAN": "1"}, capture_output=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertFalse(log.exists())
            completed = subprocess.run(["bash", str(script)], env=env, capture_output=True)
            self.assertEqual(completed.returncode, 0, completed.stderr.decode())
            calls = log.read_text().splitlines()
            self.assertEqual(len(calls), 3)
            self.assertTrue(calls[0].startswith("helm pull oci://source/chart --version 1.0"))
            self.assertIn("chart-1.0.tgz oci://target/charts", calls[1])
            self.assertEqual(calls[2], "skopeo copy --all docker://source/image:1 docker://target/image:1")

    def test_http_download_and_unknown_package(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}/api/reference-package"
            with urlopen(base + "?name=sample") as response:
                self.assertEqual(response.headers.get_content_type(), "application/zip")
                self.assertIn("sample.zip", response.headers["Content-Disposition"])
                with zipfile.ZipFile(io.BytesIO(response.read())) as archive:
                    self.assertEqual(archive.read("README.md"), reference_files("sample")["README.md"])
            with self.assertRaises(HTTPError) as error:
                urlopen(base + "?name=qbeast")
            self.assertEqual(error.exception.code, 404)
            error.exception.close()
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
