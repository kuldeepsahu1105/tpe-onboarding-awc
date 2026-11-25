import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml

from onboarding.blueprint_composer import compose_blueprint
from onboarding.generator import _build_env, render_bundle
from onboarding.manifest import normalize
from onboarding.questions import fill_defaults
from onboarding.form_generator import (
    load_form,
    render_blueprint as render_form_blueprint,
    render_chart_catalog as render_form_chart_catalog,
    render_engine_yaml as render_form_engine,
    render_image_catalog as render_form_image_catalog,
    render_publish_sh as render_form_publish,
)
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

    def test_both_input_paths_emit_current_catalog_and_publish_contracts(self):
        manifest, directory, _ = self.render(self.answers)
        main_engine = yaml.safe_load((directory / "engine.yaml").read_text())
        self.assertIn("imageCatalog", main_engine["spec"])
        self.assertIn("chartCatalog", main_engine["spec"])
        self.assertNotIn("versionCatalog", main_engine["spec"])
        self.assertIn('SCHEMA_VERSION="${SCHEMA_VERSION:-2}"',
                      (directory / "publish.sh").read_text())

        form = load_form(ROOT / "engine-onboarding/examples/neo4j.input_form.yaml")
        form["publish"].pop("schemaVersion", None)
        form_engine = yaml.safe_load(render_form_engine(form))
        form_blueprint = yaml.safe_load(render_form_blueprint(form))
        self.assertIn("imageCatalog", form_engine["spec"])
        self.assertIn("chartCatalog", form_engine["spec"])
        self.assertNotIn("versionCatalog", form_engine["spec"])
        self.assertEqual(
            main_engine["spec"]["imageCatalog"],
            yaml.safe_load((directory / "imagecatalog.yaml").read_text())["metadata"]["name"],
        )
        self.assertEqual(
            main_engine["spec"]["chartCatalog"],
            yaml.safe_load((directory / "chartcatalog.yaml").read_text())["metadata"]["name"],
        )
        self.assertEqual(
            form_engine["spec"]["imageCatalog"],
            yaml.safe_load(render_form_image_catalog(form))["metadata"]["name"],
        )
        self.assertEqual(
            form_engine["spec"]["chartCatalog"],
            yaml.safe_load(render_form_chart_catalog(form))["metadata"]["name"],
        )
        self.assertIn('SCHEMA_VERSION="${SCHEMA_VERSION:-2}"', render_form_publish(form))
        cluster = form_blueprint["spec"]["hardwareTiers"][0]["cluster"]
        self.assertNotIn("kubernetesVersion", cluster)
        self.assertNotIn("recommended", cluster["nodeGroups"][0]["resources"])
        for rendered_catalog in (
            render_form_image_catalog(form),
            render_form_chart_catalog(form),
        ):
            self.assertEqual(yaml.safe_load(rendered_catalog)["apiVersion"], manifest["apiVersion"])

    def test_validator_requires_current_catalog_references(self):
        manifest, directory, _ = self.render(self.answers)
        engine = yaml.safe_load((directory / "engine.yaml").read_text())
        del engine["spec"]["chartCatalog"]
        (directory / "engine.yaml").write_text(yaml.safe_dump(engine, sort_keys=False))
        result = validate_bundle(directory, manifest)
        self.assertFalse(result.ok)
        self.assertTrue(any("spec.chartCatalog" in finding.message for finding in result.errors))

    def test_primary_templates_emit_catalog_fields_for_v1alpha10(self):
        for path in (
            ROOT / "examples/neo4j.input.yaml",
            ROOT / "examples/puppygraph.input.yaml",
            ROOT / "examples/dataspark.input.yaml",
        ):
            with self.subTest(template=path.name), tempfile.TemporaryDirectory() as tmp:
                answers = fill_defaults(yaml.safe_load(path.read_text()))
                manifest = normalize(answers)
                output = Path(tmp)
                render_bundle(manifest, output)
                engine = yaml.safe_load((output / "engine.yaml").read_text())
                self.assertIn("imageCatalog", engine["spec"])
                self.assertNotIn("versionCatalog", engine["spec"])
                if manifest["engine"]["template"] == "native-k8s":
                    self.assertNotIn("chartCatalog", engine["spec"])
                else:
                    self.assertIn("chartCatalog", engine["spec"])
                self.assertTrue(validate_bundle(output, manifest).ok)

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
            self.assertIn('SCHEMA_VERSION="${SCHEMA_VERSION:-2}"',
                          (Path(result["out_dir"]) / "publish.sh").read_text())
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
        answers["operator"] = {
            "group": "test.example.org",
            "resource": "widgets",
            "kind": "Widget",
            "chartRepoUrl": "https://charts.example.test",
            "chartName": "sample-operator",
            "chartVersion": "1.0.0",
        }
        answers = fill_defaults(answers)
        manifest = normalize(answers)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            render_bundle(manifest, output)
            engine = yaml.safe_load((output / "engine.yaml").read_text())
            self.assertEqual(engine["spec"]["imageCatalog"],
                             yaml.safe_load((output / "imagecatalog.yaml").read_text())["metadata"]["name"])
            self.assertEqual(engine["spec"]["chartCatalog"],
                             yaml.safe_load((output / "chartcatalog.yaml").read_text())["metadata"]["name"])
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
