import copy
import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from decimal import Decimal
from pathlib import Path

import yaml

from onboarding.cli import DEFAULT_OUT, REPO_ROOT, build_parser, main
from onboarding.cost_report import (
    CostInputError, build_report, load_export, render_csv, render_txt, write_report,
)


ROOT = Path(__file__).resolve().parents[1]


class CostReportTests(unittest.TestCase):
    def setUp(self):
        self.answers = yaml.safe_load((ROOT / "examples/neo4j.input.yaml").read_text())
        self.inventory = json.loads((ROOT / "examples/costs/inventory.json").read_text())
        self.prices = json.loads((ROOT / "examples/costs/prices.json").read_text())
        self.billing = json.loads((ROOT / "examples/costs/billing.json").read_text())

    def report(self, billing=True):
        return build_report(self.answers, self.inventory, self.prices,
                            self.billing if billing else None, {})

    def test_decimal_shared_allocation_credits_and_missing_price(self):
        r = self.report()
        estimate = r["estimates"][0]
        self.assertEqual(Decimal(estimate["amount"]), Decimal("148.80"))
        self.assertEqual([Decimal(a["amount"]) for a in estimate["allocations"]],
                         [Decimal("37.20"), Decimal("74.40"), Decimal("37.20")])
        self.assertIsNone(r["estimates"][1]["amount"])
        c = r["coverage"]["estimates"]["USD"]
        self.assertEqual(Decimal(c["priced_subtotal"]), Decimal("148.80"))
        self.assertIsNone(c["supplied_rows_total"])
        self.assertEqual(c["missing_rows"], 1)
        self.assertEqual(Decimal(c["workload_known_subtotal"]), Decimal("37.20"))
        self.assertIsNone(c["complete_scope_total"])
        actual = r["coverage"]["actuals"]["USD"]
        self.assertEqual(Decimal(actual["billed_subtotal"]), Decimal("120"))
        self.assertEqual(Decimal(actual["workload_known_subtotal"]), Decimal("30"))
        self.assertEqual(r["coverage"]["inventory_resources_without_billing"], ["demo-volume-1"])

    def test_no_node_inference_from_requests_limits_or_cluster_sizing(self):
        original = self.report()
        self.answers["cluster"].update(minCpu="10000", workerCountDefault=9000)
        self.answers["helm"]["values"] = {"resources": {"requests": {"cpu": "1000"}}}
        updated = self.report()
        self.assertEqual(original["estimates"], updated["estimates"])
        self.inventory["resources"] = []
        r = self.report(billing=False)
        self.assertEqual(r["estimates"], [])
        self.assertEqual(r["coverage"]["estimates"], {})
        self.assertFalse(r["coverage"]["scope_complete"])

    def test_billing_unavailable_is_unknown(self):
        r = self.report(billing=False)
        self.assertIsNone(r["coverage"]["actuals"])
        self.assertFalse(r["coverage"]["billing_available"])
        self.assertIsNone(r["metadata"]["billing"])

    def test_artifact_reconciliation_and_full_evidence(self):
        r = self.report()
        rows = list(csv.DictReader(io.StringIO(render_csv(r))))
        self.assertTrue(all(row["schema_version"] == "1" for row in rows))
        for section in ("metadata", "resources", "estimates", "actuals", "coverage", "warnings"):
            values = [json.loads(row["details"]) for row in rows if row["section"] == section]
            self.assertEqual(values, r[section] if isinstance(r[section], list) else [r[section]])
        for section in ("estimates", "actuals"):
            csv_sum = sum((Decimal(row["amount"]) for row in rows
                           if row["section"] == section and row["amount"]), Decimal(0))
            report_sum = sum((Decimal(row["amount"]) for row in r[section]
                              if row["amount"] is not None), Decimal(0))
            self.assertEqual(csv_sum, report_sum)
            for row in r[section]:
                if row["amount"] is not None:
                    self.assertEqual(sum(Decimal(a["amount"]) for a in row["allocations"]),
                                     Decimal(row["amount"]))
        self.assertIn(json.dumps(r, indent=2), render_txt(r))
        with tempfile.TemporaryDirectory() as d:
            paths = write_report(r, Path(d))
            self.assertEqual(len(paths), 3)
            self.assertEqual(json.loads((Path(d) / "cost-report.json").read_text()), r)

    def test_currencies_remain_separate(self):
        other = copy.deepcopy(self.inventory["resources"][0])
        other.update(id="other-node", provider_resource_id="other-provider-node",
                     charge_key="other-node/compute", currency="EUR")
        self.inventory["resources"].append(other)
        r = self.report()
        self.assertEqual(set(r["coverage"]["estimates"]), {"USD", "EUR"})
        self.assertIsNone(r["estimates"][-1]["amount"])
        self.assertIsNone(r["coverage"]["estimates"]["EUR"]["supplied_rows_total"])
        self.assertEqual(r["coverage"]["estimates"]["EUR"]["priced_subtotal"], "0")

    def test_all_missing_and_zero_rates_are_distinct(self):
        self.prices["rates"] = []
        r = self.report()
        self.assertTrue(all(row["amount"] is None for row in r["estimates"]))
        self.assertEqual(r["coverage"]["estimates"]["USD"]["known_rows"], 0)
        self.setUp()
        self.prices["rates"][0]["rate"] = "0"
        r = self.report()
        self.assertEqual(Decimal(r["estimates"][0]["amount"]), 0)
        self.assertIsNone(r["estimates"][0]["missing_reason"])

    def test_tiny_costs_are_exact_plain_decimal_strings(self):
        self.prices["rates"][0]["rate"] = "0.000000000001"
        self.inventory["resources"][0]["quantity"] = "0.000000000001"
        self.inventory["resources"][0]["specs"]["hours"] = "0.000000000001"
        r = self.report()
        self.assertEqual(r["estimates"][0]["amount"], "0.000000000000000000000001")
        self.assertEqual(r["estimates"][0]["allocations"][0]["amount"],
                         "0.00000000000000000000000025")

    def test_expired_price_is_unpriced(self):
        self.prices["rates"][0]["valid_to"] = "2026-10-15T00:00:00Z"
        r = self.report()
        self.assertIsNone(r["estimates"][0]["amount"])
        self.assertEqual(r["estimates"][0]["missing_reason"], "price_not_valid_for_full_period")

    def test_unattributed_billing_and_unknown_amount(self):
        line = self.billing["lines"][0]
        line.update(resource_id=None, provider_resource_id="unmapped-provider-node",
                    charge_key="unmapped-compute", amount=None)
        self.billing["lines"] = [line]
        r = self.report()
        self.assertIsNone(r["actuals"][0]["allocations"][0]["workload"])
        self.assertIsNone(r["coverage"]["actuals"]["USD"]["supplied_rows_total"])
        self.assertIsNone(r["coverage"]["actuals"]["USD"]["workload_known_subtotal"])

    def test_missing_workload_link_does_not_claim_zero_cost(self):
        self.answers["engine"]["name"] = "another-engine"
        r = self.report()
        self.assertIsNone(r["coverage"]["estimates"]["USD"]["workload_known_subtotal"])
        self.assertTrue(any("No inventoried allocation" in w for w in r["warnings"]))

    def test_malformed_numeric_and_allocation_values(self):
        for value in ("NaN", "Infinity", "-1", "1e3", "0.1234567890123", 1.0, True):
            with self.subTest(value=value):
                self.inventory["resources"][0]["quantity"] = value
                with self.assertRaises(CostInputError):
                    self.report()
        self.setUp()
        for fraction in ("1.1", "-0.1", "0", "NaN"):
            with self.subTest(fraction=fraction):
                self.inventory["resources"][0]["allocations"][0]["fraction"] = fraction
                with self.assertRaises(CostInputError):
                    self.report()

    def test_duplicate_and_overlapping_inputs_rejected(self):
        for name, key in (("inventory", "resources"), ("prices", "rates"), ("billing", "lines")):
            with self.subTest(name=name):
                self.setUp()
                doc = getattr(self, name)
                doc[key].append(copy.deepcopy(doc[key][0]))
                with self.assertRaises(CostInputError):
                    self.report()
        self.setUp()
        duplicate = copy.deepcopy(self.billing["lines"][0])
        duplicate["id"] = "different-id-same-charge"
        self.billing["lines"].append(duplicate)
        with self.assertRaisesRegex(CostInputError, "Overlapping"):
            self.report()

    def test_identity_and_period_errors(self):
        mutations = [
            ("billing", "currency", "EUR"),
            ("billing", "account", "wrong-account"),
            ("billing", "resource_id", "not-in-inventory"),
            ("billing", "sku", "wrong-sku"),
        ]
        for _, key, value in mutations:
            with self.subTest(key=key):
                self.setUp()
                self.billing["lines"][0][key] = value
                with self.assertRaises(CostInputError):
                    self.report()
        for period in ({"start": "2026-11-01T00:00:00Z", "end": "2026-10-01T00:00:00Z"},
                       {"start": "2026-10-01", "end": "2026-11-01"},
                       {"start": "yesterday", "end": "tomorrow"}):
            self.setUp()
            self.inventory["period"] = period
            with self.assertRaises(CostInputError):
                self.report()
        self.setUp()
        self.billing["period"]["end"] = "2026-11-02T00:00:00Z"
        with self.assertRaisesRegex(CostInputError, "periods must match"):
            self.report()

    def test_schema_and_shape_errors(self):
        for value in ([], None, "not an object"):
            self.inventory["resources"] = value
            with self.assertRaises(CostInputError):
                self.report()
        for doc in ("inventory", "prices", "billing"):
            self.setUp()
            getattr(self, doc)["schema_version"] = True
            with self.assertRaises(CostInputError):
                self.report()
        self.setUp()
        self.inventory["resources"][0]["unexpected"] = "typo"
        with self.assertRaisesRegex(CostInputError, "Unknown fields"):
            self.report()

    def test_non_json_yaml_context_has_explicit_error(self):
        for snippet in ("date: 2026-10-01", "number: .nan", "set: !!set {value: null}"):
            self.setUp()
            self.answers["helm"]["values"] = yaml.safe_load(snippet)
            with self.assertRaisesRegex(CostInputError, "JSON-compatible"):
                self.report()

    def test_unknown_quantity_is_null_not_zero(self):
        self.inventory["resources"][0]["quantity"] = None
        r = self.report()
        self.assertIsNone(r["estimates"][0]["quantity"])
        self.assertIsNone(r["estimates"][0]["amount"])
        self.assertEqual(r["estimates"][0]["missing_reason"], "missing_quantity")
        self.assertIsNone(r["coverage"]["estimates"]["USD"]["workload_known_subtotal"])

    def test_infrastructure_specs_shared_count_and_rollup_math(self):
        second = copy.deepcopy(self.inventory["resources"][0])
        second.update(id="node-2", provider_resource_id="provider-node-2", charge_key="node-2/compute")
        self.inventory["resources"].append(second)
        r = self.report()
        nodes = [g for g in r["coverage"]["grouped_estimates"] if g["kind"] == "node"]
        self.assertEqual(len(nodes), 1)
        group = nodes[0]
        self.assertEqual(group["physical_count"], "2")
        self.assertEqual(group["identified_physical_resources"], 2)
        self.assertEqual(group["vcpu_total"], "8")
        self.assertEqual(group["ram_gib_total"], "32")
        self.assertEqual(group["quantity_total"], "1488")
        self.assertEqual(Decimal(group["cost"]["priced_subtotal"]), Decimal("297.60"))
        self.assertEqual(Decimal(group["cost"]["workload_known_subtotal"]), Decimal("74.40"))
        self.assertEqual(Decimal(r["estimates"][0]["per_node_price"]), Decimal("148.80"))
        self.assertEqual(r["estimates"][0]["per_node_price"], r["estimates"][0]["extended_price"])
        actual = r["coverage"]["grouped_actuals"][0]
        self.assertEqual(actual["physical_count"], "1")  # charge plus credit is still one node
        self.assertEqual(actual["vcpu_total"], "4")
        self.assertIsNone(actual["quantity_total"])
        storage = [g for g in r["coverage"]["grouped_estimates"] if g["kind"] == "storage"][0]
        self.assertEqual(storage["disk_gb_total"], "100")
        self.assertEqual(storage["disk_iops_total"], "3000")
        self.assertEqual(storage["disk_throughput_mbps_total"], "125")
        csv_rows = list(csv.DictReader(io.StringIO(render_csv(r))))
        node = next(row for row in csv_rows if row["section"] == "estimates" and row["kind"] == "node")
        self.assertEqual(node["physical_count"], "1")
        self.assertEqual(node["node_role"], "worker")
        self.assertEqual(node["vcpu"], "4")
        self.assertEqual(node["spec_source"], self.inventory["resources"][0]["specs"]["source"])
        rollup = next(row for row in csv_rows
                      if row["section"] == "estimates_rollups" and row["kind"] == "node")
        self.assertEqual(rollup["physical_count"], "2")
        self.assertEqual(Decimal(rollup["priced_subtotal"]), Decimal("297.60"))
        self.assertEqual(json.loads(rollup["details"]), group)
        self.assertIn("GROUPED ROLLUPS", render_txt(r))
        self.assertIn("disk_throughput_mbps", render_txt(r))

    def test_network_usage_rates_and_unknown_specs(self):
        node = self.inventory["resources"][0]
        node.update(kind="network", unit="GB", quantity="50",
                    specs={"source": "network usage export", "network_type": "internet-egress"})
        self.prices["rates"][0].update(unit="GB", rate="0.09")
        r = self.report(billing=False)
        estimate = r["estimates"][0]
        self.assertEqual(estimate["network_usage"], "50")
        self.assertEqual(estimate["unit_price"], "0.09")
        self.assertEqual(Decimal(estimate["extended_price"]), Decimal("4.50"))
        self.assertIsNone(estimate["per_node_price"])
        group = r["coverage"]["grouped_estimates"][0]
        self.assertEqual(group["network_type"], "internet-egress")
        self.assertIsNone(group["physical_count"])
        self.assertIsNone(group["vcpu_total"])
        self.setUp()
        del self.inventory["resources"][0]["specs"]
        r = self.report()
        self.assertTrue(all(v is None for v in r["estimates"][0]["specs"].values()))
        self.assertIsNone(r["estimates"][0]["per_node_price"])

    def test_invalid_specs_rejected_without_inference(self):
        for key, value in (("physical_count", "2"), ("physical_count", "0"),
                           ("vcpu", "-1"), ("ram_gib", 16), ("hours", "730"),
                           ("node_role", ""), ("disk_gb", "NaN"), ("extra", "typo")):
            with self.subTest(key=key, value=value):
                self.setUp()
                self.inventory["resources"][0]["specs"][key] = value
                with self.assertRaises(CostInputError):
                    self.report()
        self.setUp()
        self.inventory["resources"][0]["specs"] = {"vcpu": "4"}
        with self.assertRaises(CostInputError):
            self.report()

    def test_dedicated_and_shared_constraints(self):
        for tenancy, allocations in (
            ("dedicated", []),
            ("dedicated", self.inventory["resources"][0]["allocations"]),
            ("unattributed", self.inventory["resources"][0]["allocations"]),
        ):
            with self.subTest(tenancy=tenancy):
                r = self.inventory["resources"][0]
                r["tenancy"], r["allocations"] = tenancy, copy.deepcopy(allocations)
                with self.assertRaises(CostInputError):
                    self.report()
        self.setUp()
        r = self.inventory["resources"][0]
        r["allocations"][0]["fraction"] = "0.75"
        with self.assertRaisesRegex(CostInputError, "exceed"):
            self.report()
        self.setUp()
        duplicate = copy.deepcopy(self.inventory["resources"][0])
        duplicate.update(id="renamed-node", charge_key="alias")
        self.inventory["resources"].append(duplicate)
        with self.assertRaisesRegex(CostInputError, "physical resource"):
            self.report()

    def test_actual_signs_periods_and_consistent_metric(self):
        for index, amount in ((0, "-1"), (1, "1"), (0, "NaN")):
            self.setUp()
            self.billing["lines"][index]["amount"] = amount
            with self.assertRaises(CostInputError):
                self.report()
        self.setUp()
        self.billing["metric"] = ["net_cost", "gross_cost"]
        with self.assertRaises(CostInputError):
            self.report()
        self.setUp()
        self.billing["lines"][0]["period"]["end"] = "2026-11-02T00:00:00Z"
        with self.assertRaisesRegex(CostInputError, "outside report period"):
            self.report()
        self.setUp()
        self.billing["lines"][1]["amount"] = "-200.00"
        self.assertEqual(Decimal(self.report()["coverage"]["actuals"]["USD"]["billed_subtotal"]),
                         Decimal("-70.00"))

    def test_adjacent_actual_windows_are_not_overlaps(self):
        first = self.billing["lines"][0]
        second = copy.deepcopy(first)
        first["period"]["end"] = "2026-10-15T00:00:00Z"
        second.update(id="second-half", amount="20.00")
        second["period"]["start"] = "2026-10-15T00:00:00Z"
        self.billing["lines"] = [first, second]
        self.assertEqual(Decimal(self.report()["coverage"]["actuals"]["USD"]["billed_subtotal"]),
                         Decimal("150.00"))

    def test_available_empty_billing_is_not_zero_bill(self):
        self.billing["lines"] = []
        r = self.report()
        self.assertTrue(r["coverage"]["billing_available"])
        self.assertEqual(r["coverage"]["actuals"], {})
        self.assertEqual(len(r["coverage"]["inventory_resources_without_billing"]), 2)

    def test_cost_cli_does_not_deploy_or_create_sessions(self):
        from unittest.mock import patch

        input_paths = [ROOT / "examples/neo4j.input.yaml",
                       ROOT / "examples/costs/inventory.json",
                       ROOT / "examples/costs/prices.json"]
        original_inputs = [p.read_bytes() for p in input_paths]
        with tempfile.TemporaryDirectory() as d, redirect_stdout(io.StringIO()), \
                patch("subprocess.run", side_effect=AssertionError("External command attempted")), \
                patch("subprocess.Popen", side_effect=AssertionError("Process attempted")), \
                patch("socket.socket", side_effect=AssertionError("Network attempted")), \
                patch("onboarding.cli.render_bundle", side_effect=AssertionError("Bundle generated")), \
                patch("onboarding.cli.Session.load", side_effect=AssertionError("Session touched")):
            self.assertEqual(main([
                "cost-report", "--file", str(ROOT / "examples/neo4j.input.yaml"),
                "--inventory", str(ROOT / "examples/costs/inventory.json"),
                "--prices", str(ROOT / "examples/costs/prices.json"), "--out", d]), 0)
            self.assertEqual({p.name for p in Path(d).iterdir()},
                             {"cost-report.json", "cost-report.csv", "cost-report.txt"})
        self.assertEqual([p.read_bytes() for p in input_paths], original_inputs)

    def test_existing_cli_signatures_and_default_paths_unchanged(self):
        parser = build_parser()
        cases = [
            (["wizard"], "cmd_wizard", {"session": "default"}),
            (["answers", "--file", "answers.yaml"], "cmd_answers",
             {"session": "default", "file": "answers.yaml"}),
            (["generate"], "cmd_generate", {"session": "default", "out": None}),
            (["validate"], "cmd_validate", {"session": "default", "out": None}),
            (["all", "--file", "input.yaml"], "cmd_all", {"file": "input.yaml", "out": None}),
            (["blueprint", "--file", "blueprint.yaml"], "cmd_blueprint",
             {"file": "blueprint.yaml", "out": None}),
            (["discover-images"], "cmd_discover",
             {"repo_url": None, "chart": None, "version": None, "values": None,
              "set": None, "rendered": None, "write": None}),
        ]
        for argv, function, expected in cases:
            with self.subTest(argv=argv):
                args = parser.parse_args(argv)
                self.assertEqual(args.func.__name__, function)
                for key, value in expected.items():
                    self.assertEqual(getattr(args, key), value)
                self.assertFalse(hasattr(args, "inventory"))
                self.assertFalse(hasattr(args, "prices"))
                self.assertFalse(hasattr(args, "billing"))
        self.assertEqual(DEFAULT_OUT, REPO_ROOT / "output")

    def test_existing_example_bundles_still_generate_and_validate(self):
        from onboarding.generator import render_bundle
        from onboarding.manifest import normalize
        from onboarding.questions import fill_defaults
        from onboarding.validator import validate_bundle

        for name in ("neo4j", "puppygraph", "starrocks"):
            with self.subTest(engine=name), tempfile.TemporaryDirectory() as d:
                answers = yaml.safe_load((ROOT / f"examples/{name}.input.yaml").read_text())
                fill_defaults(answers)
                manifest = normalize(answers)
                render_bundle(manifest, Path(d))
                result = validate_bundle(Path(d), manifest)
                self.assertTrue(result.ok, result.as_dict())
                self.assertFalse(any(Path(d).glob("cost-report.*")))

    def test_cli_success_and_errors_no_outputs_on_invalid_input(self):
        with tempfile.TemporaryDirectory() as d, redirect_stdout(io.StringIO()):
            args = ["cost-report", "--file", str(ROOT / "examples/neo4j.input.yaml"),
                    "--inventory", str(ROOT / "examples/costs/inventory.json"),
                    "--prices", str(ROOT / "examples/costs/prices.json"),
                    "--billing", str(ROOT / "examples/costs/billing.json"),
                    "--out", str(Path(d) / "valid")]
            self.assertEqual(main(args), 0)
            result = json.loads((Path(d) / "valid/cost-report.json").read_text())
            self.assertIn("sha256", result["metadata"]["evidence"]["prices"])
            bad = Path(d) / "bad.json"
            bad.write_text('{"schema_version":1,"schema_version":1}')
            args[args.index("--inventory") + 1] = str(bad)
            args[-1] = str(Path(d) / "invalid")
            with redirect_stderr(io.StringIO()) as err:
                self.assertEqual(main(args), 1)
            self.assertIn("Duplicate JSON key", err.getvalue())
            self.assertFalse((Path(d) / "invalid").exists())


if __name__ == "__main__":
    unittest.main()
