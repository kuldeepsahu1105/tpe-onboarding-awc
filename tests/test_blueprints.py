import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml

from onboarding.blueprint_composer import compose_blueprint
from onboarding.generator import _build_env, render_bundle
from onboarding.manifest import normalize
from onboarding.validator import validate_bundle
from web.app import run_blueprint


ROOT = Path(__file__).resolve().parents[1]


class BlueprintTests(unittest.TestCase):
    def setUp(self):
        self.answers = yaml.safe_load((ROOT / "examples/neo4j.input.yaml").read_text())

    def render(self, answers):
        manifest = normalize(answers)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name)
        render_bundle(manifest, directory)
        return manifest, directory, yaml.safe_load((directory / "blueprint.yaml").read_text())

    def test_current_default_and_legacy_opt_in(self):
        manifest, directory, bp = self.render(self.answers)
        self.assertTrue(validate_bundle(directory, manifest).ok)
        self.assertEqual(bp["spec"]["instances"][0]["minimumVersion"], "5.26.0")
        cluster = bp["spec"]["hardwareTiers"][0]["cluster"]
        self.assertNotIn("kubernetesVersion", cluster)
        self.assertNotIn("recommended", cluster["nodeGroups"][0]["resources"])
        self.assertEqual(bp["spec"]["ui"]["displayName"], "Neo4j")
        self.assertNotIn("versionMatrix", bp["spec"])
        self.assertFalse((directory / "clusterrequirements.yaml").exists())
        (directory / "clusterrequirements.yaml").write_text("kind: ClusterRequirements\n")
        self.assertFalse(validate_bundle(directory, manifest).ok)

        legacy = copy.deepcopy(self.answers)
        legacy["blueprint"]["format"] = "legacy"
        manifest, directory, bp = self.render(legacy)
        self.assertTrue(validate_bundle(directory, manifest).ok)
        self.assertIn("versionMatrix", bp["spec"])
        self.assertIn("cluster", bp["spec"])
        self.assertTrue((directory / "clusterrequirements.yaml").exists())

    def test_generated_capability_uses_marketplace_filename(self):
        answers = copy.deepcopy(self.answers)
        answers["capability"]["exportsStructuredData"] = True
        manifest, directory, _ = self.render(answers)
        self.assertTrue((directory / "capabilities.yaml").is_file())
        self.assertFalse((directory / "capability.yaml").exists())
        (directory / "capability.yaml").write_text("kind: Capability\n")
        self.assertFalse(validate_bundle(directory, manifest).ok)

    def test_reference_declaration_and_runtime_binding_are_distinct(self):
        answers = copy.deepcopy(self.answers)
        answers["dependencies"] = {"entries": [
            {"name": "db", "engine": "postgres-plugin", "type": "auto",
             "version": "18.0.0", "config": {"databases": "polaris"}},
            {"name": "ranger", "engine": "udf-plugin", "type": "ref",
             "minimumVersion": "1.6.0", "runtimeInstance": "shared-udf"},
            {"name": "other", "engine": "other-plugin", "type": "optional"},
        ]}
        _, directory, bp = self.render(answers)
        self.assertEqual([i["name"] for i in bp["spec"]["instances"]], ["neo4j"])
        engine = yaml.safe_load((directory / "engine.yaml").read_text())
        self.assertEqual(engine["spec"]["dependencies"][0]["config"], {"databases": "polaris"})
        self.assertEqual(engine["spec"]["dependencies"][1]["minimumVersion"], "1.6.0")
        instance = yaml.safe_load((directory / "examples/instance.yaml").read_text())
        self.assertEqual(instance["spec"]["dependencies"], [{"name": "ranger", "instance": "shared-udf"}])

    def test_explicit_new_dependency_requires_version_and_name(self):
        answers = copy.deepcopy(self.answers)
        dep = {"name": "ranger", "engine": "udf-plugin", "type": "ref", "includeInBlueprint": True}
        answers["dependencies"] = {"entries": [dep]}
        with self.assertRaisesRegex(ValueError, "explicit instance and minimumVersion"):
            self.render(answers)
        dep.update(instance="udf", minimumVersion="1.6.0")
        _, _, bp = self.render(answers)
        self.assertEqual(bp["spec"]["instances"][0], {
            "name": "udf", "engine": "udf-plugin", "minimumVersion": "1.6.0"
        })
        self.assertNotIn("dependencies", bp["spec"]["instances"][1])
        self.assertIn('--instance "udf=udf-plugin:1.6.0"', (self.render(answers)[1] / "publish.sh").read_text())

    def test_polaris_udf_composition_and_duplicate_rejection(self):
        spec = ROOT / "examples/polaris-udf.blueprint.input.yaml"
        web_result = run_blueprint(spec.read_text(), {})
        self.assertTrue(web_result["ok"])
        self.assertIn("blueprint.yaml", web_result["files"])
        with tempfile.TemporaryDirectory() as tmp:
            result = compose_blueprint(spec, Path(tmp))
            bp = yaml.safe_load((Path(result["out_dir"]) / "blueprint.yaml").read_text())
            self.assertEqual([(i["engine"], i["minimumVersion"]) for i in bp["spec"]["instances"]],
                             [("udf-plugin", "1.6.0"), ("polaris-plugin", "2.0.0")])
            self.assertTrue(bp["spec"]["hardwareTiers"][0]["cluster"]["nodeGroups"])
            data = yaml.safe_load(spec.read_text())
            data["engines"][1]["existing"]["instance"] = "udf"
            duplicate = Path(tmp) / "duplicate.yaml"
            duplicate.write_text(yaml.safe_dump(data))
            with self.assertRaisesRegex(ValueError, "Duplicate Blueprint instance"):
                compose_blueprint(duplicate, Path(tmp))

    def test_operator_role_has_no_broad_cluster_binding(self):
        answers = copy.deepcopy(self.answers)
        answers["engine"]["template"] = "helm-operator"
        answers["operator"] = {"group": "test.example.org", "resource": "widgets", "kind": "Widget"}
        manifest = normalize(answers)
        role = _build_env("helm-operator").get_template("role.yaml.j2").render(**manifest)
        roles = list(yaml.safe_load_all(role))
        self.assertIn("ClusterRole", [r["kind"] for r in roles])
        self.assertNotIn("ClusterRoleBinding", [r["kind"] for r in roles])

    def test_form_generator_preserves_only_explicit_blueprint_dependencies(self):
        spec = importlib.util.spec_from_file_location(
            "form_generator", ROOT / "engine-onboarding/generate_engine.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        form = yaml.safe_load((ROOT / "engine-onboarding/examples/neo4j.input_form.yaml").read_text())
        form["dependencies"] = {"entries": [
            {"name": "ranger", "engine": "udf-plugin", "type": "ref", "minimumVersion": "1.6.0"},
            {"name": "db", "engine": "postgres-plugin", "type": "auto", "version": "18.0.0"},
        ]}
        bp = yaml.safe_load(module.render_blueprint(form))
        self.assertEqual(len(bp["spec"]["instances"]), 1)
        cluster = bp["spec"]["hardwareTiers"][0]["cluster"]
        self.assertNotIn("kubernetesVersion", cluster)
        self.assertNotIn("recommended", cluster["nodeGroups"][0]["resources"])
        dep = form["dependencies"]["entries"][0]
        dep.update(includeInBlueprint=True, instance="udf")
        bp = yaml.safe_load(module.render_blueprint(form))
        self.assertIn({"name": "udf", "engine": "udf-plugin", "minimumVersion": "1.6.0"},
                      bp["spec"]["instances"])
        form["blueprint"]["format"] = "legacy"
        bp = yaml.safe_load(module.render_blueprint(form))
        self.assertIn("kubernetesVersion", bp["spec"]["hardwareTiers"][0]["cluster"])


if __name__ == "__main__":
    unittest.main()
