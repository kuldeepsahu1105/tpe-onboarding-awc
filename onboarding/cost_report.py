"""Offline, evidence-based cost reporting. No cloud clients or deployment calls."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

from .manifest import normalize


class CostInputError(ValueError):
    """An export cannot be safely interpreted."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CostInputError(message)


def fields(value, required: set[str], optional: set[str] | None = None) -> dict:
    require(isinstance(value, dict), "Expected an object")
    require(required <= value.keys(), f"Missing fields: {sorted(required - value.keys())}")
    require(not value.keys() - required - (optional or set()),
            f"Unknown fields: {sorted(value.keys() - required - (optional or set()))}")
    return value


def text(value) -> str:
    require(isinstance(value, str) and bool(value.strip()), "Expected a nonempty string")
    require(not any(ord(c) < 32 for c in value), "Control characters are not allowed")
    return value


def number(value, *, signed=False) -> Decimal:
    require(isinstance(value, str), "Decimal quantities and amounts must be JSON strings")
    require(bool(re.fullmatch(r"-?\d+(?:\.\d+)?", value)), f"Invalid decimal: {value!r}")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise CostInputError(f"Invalid decimal: {value!r}") from exc
    require(len(result.as_tuple().digits) <= 24 and abs(result.as_tuple().exponent) <= 12,
            "Decimal precision exceeds 24 digits / 12 decimal places")
    require(signed or result >= 0, "Negative quantity/rate is not allowed")
    return result


def decimal_text(value: Decimal) -> str:
    return format(value, "f")


def instant(value) -> datetime:
    text(value)
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CostInputError(f"Invalid ISO timestamp: {value}") from exc
    require(result.tzinfo is not None, "Timestamps must include a timezone")
    return result.astimezone(timezone.utc)


def window(value) -> tuple[datetime, datetime]:
    fields(value, {"start", "end"})
    start, end = instant(value["start"]), instant(value["end"])
    require(start < end, "Period start must precede end (exclusive)")
    return start, end


def sequence(value) -> list:
    require(isinstance(value, list), "Expected an array")
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_export(path: Path) -> tuple[dict, dict]:
    raw = path.read_bytes()
    try:
        doc = json.loads(raw, object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError) as exc:
        raise CostInputError(f"{path}: {exc}") from exc
    require(isinstance(doc, dict), f"{path}: expected an object")
    require(type(doc.get("schema_version")) is int and doc["schema_version"] == 1,
            f"{path}: schema_version must be 1")
    return doc, {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


def currency(value) -> str:
    require(isinstance(value, str) and bool(re.fullmatch("[A-Z]{3}", value)),
            "Currency must be a three-letter uppercase code")
    return value


IDENTITY = ("provider", "region", "sku", "unit")


def identity(row) -> tuple:
    return tuple(text(row[k]) for k in IDENTITY)


def allocations(row) -> list[dict]:
    entries, owners, total = [], set(), Decimal(0)
    for item in sequence(row["allocations"]):
        fields(item, {"workload", "fraction", "method", "source"})
        owner = text(item["workload"])
        require(owner not in owners, f"Duplicate allocation workload: {owner}")
        owners.add(owner)
        fraction = number(item["fraction"])
        require(0 < fraction <= 1, "Allocation fraction must be > 0 and <= 1")
        total += fraction
        entries.append({**item, "method": text(item["method"]), "source": text(item["source"])})
    require(total <= 1, "Allocation fractions exceed 1")
    require(row["tenancy"] in ("dedicated", "shared", "unattributed"), "Invalid tenancy")
    if row["tenancy"] == "dedicated":
        require(len(entries) == 1 and total == 1, "Dedicated resource requires one full allocation")
    if row["tenancy"] == "unattributed":
        require(not entries, "Unattributed resources cannot have allocations")
    return entries


def distribute(amount: Decimal | None, entries: list[dict]) -> list[dict]:
    result = [{**a, "amount": None if amount is None else decimal_text(amount * Decimal(a["fraction"]))}
              for a in entries]
    remainder = 1 - sum((Decimal(a["fraction"]) for a in entries), Decimal(0))
    if remainder:
        result.append({"workload": None, "fraction": decimal_text(remainder), "method": "unattributed",
                       "source": None, "amount": None if amount is None else decimal_text(amount * remainder)})
    return result


SPEC_TEXT = ("node_role", "node_type", "disk_type", "network_type")
SPEC_NUMBERS = ("physical_count", "vcpu", "ram_gib", "hours", "disk_gb",
                "disk_iops", "disk_throughput_mbps")


def resource_specs(resource: dict) -> dict:
    raw = resource.get("specs")
    result = {key: None for key in (*SPEC_TEXT, *SPEC_NUMBERS, "source")}
    if raw is None:
        return result
    fields(raw, {"source"}, set(SPEC_TEXT + SPEC_NUMBERS))
    text(raw["source"])
    for key in SPEC_TEXT:
        if raw.get(key) is not None:
            text(raw[key])
    for key in SPEC_NUMBERS:
        if raw.get(key) is not None:
            value = number(raw[key])
            if key == "physical_count":
                require(value == 1, "Each inventoried provider_resource_id represents one physical "
                        "resource; list individual IDs instead of aggregate physical_count")
    if raw.get("hours") is not None:
        require(resource["kind"] == "node" and resource["unit"] == "node-hour",
                "hours requires an inventoried node with unit node-hour")
        require(resource["quantity"] is None or number(raw["hours"]) == number(resource["quantity"]),
                "Node hours must equal quantity for an individually inventoried node")
    result.update(raw)
    return result


def grouped_rollups(rows: list[dict], workload: str, *, estimate: bool) -> list[dict]:
    groups = {}
    keys = ("provider", "account", "region", "kind", "sku", "unit", "currency")
    for row in rows:
        spec = row["specs"]
        key = tuple(row.get(k) for k in keys) + tuple(spec[k] for k in SPEC_TEXT)
        groups.setdefault(key, []).append(row)
    result = []
    for key, group in groups.items():
        physical = {}
        for row in group:
            physical.setdefault(row["provider_resource_id"], row["specs"])
        quantities = [r.get("quantity") for r in group]
        rollup = {**dict(zip((*keys, *SPEC_TEXT), key)),
                  "resource_ids": sorted(physical),
                  "identified_physical_resources": len(physical),
                  "physical_count": str(len(physical)) if all(
                      s["physical_count"] is not None for s in physical.values()) else None,
                  "known_quantity_subtotal": decimal_text(sum(
                      (Decimal(q) for q in quantities if q is not None), Decimal(0))) if estimate else None,
                  "quantity_total": decimal_text(sum(map(Decimal, quantities), Decimal(0)))
                  if estimate and all(q is not None for q in quantities) else None,
                  "cost": summarize(group, workload, estimate=estimate)[group[0]["currency"]]}
        for spec_key in ("vcpu", "ram_gib", "disk_gb", "disk_iops", "disk_throughput_mbps"):
            rollup[spec_key + "_total"] = decimal_text(sum(
                (Decimal(s[spec_key]) for s in physical.values()), Decimal(0))) if all(
                    s[spec_key] is not None for s in physical.values()) else None
        result.append(rollup)
    return result


def build_report(answers: dict, inventory: dict, prices: dict, billing: dict | None,
                 evidence: dict) -> dict:
    """Validate all inputs before deriving any monetary output."""
    with localcontext() as ctx:
        ctx.prec = 100
        return _build_report(answers, inventory, prices, billing, evidence)


def _build_report(answers, inventory, prices, billing, evidence):
    require(isinstance(answers, dict), "Onboarding input must be an object")
    try:
        json.dumps(answers, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise CostInputError(
            "Onboarding input must contain JSON-compatible values and sortable object keys; "
            "quote YAML date/time values and reject nonfinite numbers or circular aliases"
        ) from exc
    require(isinstance(answers.get("partner"), dict) and isinstance(answers.get("engine"), dict),
            "Onboarding input requires partner and engine objects")
    text(answers["partner"].get("id"))
    for name in ("name", "template"):
        if name in answers["engine"]:
            text(answers["engine"][name])
    for name in ("cluster", "helm"):
        require(name not in answers or isinstance(answers[name], dict),
                f"Onboarding {name} must be an object")
    manifest = normalize({"partner": answers["partner"], "engine": answers["engine"]})
    require(manifest["engine"]["template"] in
            ("helm-simple", "helm-multi-role", "helm-operator", "native-k8s"),
            "Unknown onboarding engine template")
    workload = manifest["engine"]["name"]
    fields(inventory, {"schema_version", "source", "as_of", "period", "resources", "excluded_scope"})
    fields(prices, {"schema_version", "source", "as_of", "rates"})
    for doc in (inventory, prices):
        require(type(doc["schema_version"]) is int and doc["schema_version"] == 1,
                "schema_version must be 1")
        text(doc["source"])
        instant(doc["as_of"])
    start, end = window(inventory["period"])
    excluded = [text(s) for s in sequence(inventory["excluded_scope"])]
    rates = {}
    for rate in sequence(prices["rates"]):
        fields(rate, {*IDENTITY, "currency", "rate", "source", "as_of", "valid_from", "valid_to"})
        key = identity(rate) + (currency(rate["currency"]),)
        require(key not in rates, f"Duplicate/ambiguous price key: {key}")
        number(rate["rate"])
        text(rate["source"])
        instant(rate["as_of"])
        valid_start, valid_end = instant(rate["valid_from"]), instant(rate["valid_to"])
        require(valid_start < valid_end, "Price validity start must precede end")
        rates[key] = rate

    resources, estimates, seen_charges, physical_dimensions = {}, [], set(), set()
    warnings = [
        "Inventory is caller-supplied, not discovered or verified against a cloud account.",
        "Pod requests/limits, replicas and ClusterRequirements do not establish billable nodes.",
        "No infrastructure is provisioned. Taxes, discounts, support, network, licenses and other "
        "charges are excluded unless explicitly inventoried.",
        "Estimates and actuals are separate views and must never be added.",
        "Allocation fractions are caller assertions, not measured workload usage.",
        "Resource IDs and charge keys must identify nonoverlapping billing components. "
        "Semantic aliases, embedded bundle charges and export completeness cannot be verified offline.",
    ]
    for r in sequence(inventory["resources"]):
        fields(r, {"id", "account", "provider_resource_id", "charge_key", "kind", *IDENTITY, "currency", "quantity",
                   "quantity_basis", "source", "tenancy", "allocations"}, {"specs"})
        rid, charge = text(r["id"]), text(r["charge_key"])
        require(rid not in resources, f"Duplicate resource id: {rid}")
        require(charge not in seen_charges, f"Duplicate inventory charge_key: {charge}")
        seen_charges.add(charge)
        require(text(r["kind"]) in ("node", "storage", "network", "load_balancer",
                                    "control_plane", "license", "other"), "Unsupported resource kind")
        text(r["source"])
        text(r["account"])
        text(r["quantity_basis"])
        key = identity(r) + (currency(r["currency"]),)
        physical = (r["provider"], r["account"], r["region"],
                    text(r["provider_resource_id"]), r["unit"])
        require(physical not in physical_dimensions,
                "Duplicate physical resource billing dimension (provider/account/region/resource/unit)")
        physical_dimensions.add(physical)
        quantity = None if r["quantity"] is None else number(r["quantity"])
        specs = resource_specs(r)
        entries = allocations(r)
        rate = rates.get(key)
        reason = None
        if quantity is None:
            reason = "missing_quantity"
        elif rate is None:
            reason = "missing_price"
        elif not (instant(rate["valid_from"]) <= start and end <= instant(rate["valid_to"])):
            reason = "price_not_valid_for_full_period"
        amount = None if reason else quantity * number(rate["rate"])
        resources[rid] = r
        estimates.append({"resource_id": rid, "account": r["account"],
                          "provider_resource_id": r["provider_resource_id"], "charge_key": charge,
                          **dict(zip(IDENTITY, key)),
                          "currency": r["currency"], "quantity": None if quantity is None else decimal_text(quantity),
                          "quantity_basis": r["quantity_basis"], "source": r["source"], "price": rate,
                          "kind": r["kind"], "specs": specs,
                          "unit_price": rate["rate"] if rate and reason != "price_not_valid_for_full_period" else None,
                          "per_node_price": decimal_text(amount) if amount is not None
                          and r["kind"] == "node" and specs["physical_count"] is not None else None,
                          "extended_price": None if amount is None else decimal_text(amount),
                          "network_usage": None if r["kind"] != "network" or quantity is None
                          else decimal_text(quantity),
                          "amount": None if amount is None else decimal_text(amount), "missing_reason": reason,
                          "allocations": distribute(amount, entries)})

    actuals, billing_meta, intervals, billing_identities = [], None, {}, {}
    if billing is not None:
        fields(billing, {"schema_version", "source", "as_of", "period", "metric",
                         "project", "tags", "allocation_limitations", "lines"})
        require(type(billing["schema_version"]) is int and billing["schema_version"] == 1,
                "schema_version must be 1")
        text(billing["source"])
        instant(billing["as_of"])
        require(window(billing["period"]) == (start, end), "Billing and inventory periods must match")
        require(billing["metric"] in ("net_cost", "gross_cost", "amortized_cost"),
                "Unsupported billing metric; use one consistent metric per export")
        text(billing["project"])
        require(isinstance(billing["tags"], dict), "Billing tags must be an object")
        for k, v in billing["tags"].items():
            text(k)
            text(v)
        for limitation in sequence(billing["allocation_limitations"]):
            text(limitation)
        billing_meta = {k: v for k, v in billing.items() if k != "lines"}
        seen_lines = set()
        for line in sequence(billing["lines"]):
            fields(line, {"id", "account", "provider_resource_id", "charge_key", "resource_id", *IDENTITY, "currency", "amount",
                          "period", "source", "record_type"})
            lid, charge = text(line["id"]), text(line["charge_key"])
            require(lid not in seen_lines, f"Duplicate billing line id: {lid}")
            seen_lines.add(lid)
            text(line["source"])
            text(line["account"])
            text(line["provider_resource_id"])
            currency(line["currency"])
            identity(line)
            charge_identity = (line["provider"], line["account"], line["region"],
                               line["provider_resource_id"], line["sku"], line["unit"], line["currency"])
            require(charge not in billing_identities or billing_identities[charge] == charge_identity,
                    "Billing charge_key has conflicting physical identity or currency")
            billing_identities[charge] = charge_identity
            require(line["record_type"] in ("charge", "credit"), "Invalid billing record_type")
            amount = None if line["amount"] is None else number(line["amount"], signed=True)
            if amount is not None:
                require((line["record_type"] == "credit" and amount <= 0) or
                        (line["record_type"] == "charge" and amount >= 0),
                        "Charges must be nonnegative; credits must be nonpositive")
            ls, le = window(line["period"])
            require(start <= ls < le <= end, "Billing line period is outside report period")
            interval_key = (line["provider"], line["account"], line["region"],
                            line["provider_resource_id"], line["unit"], line["record_type"])
            prior = intervals.setdefault(interval_key, [])
            require(not any(ls < pe and ps < le for ps, pe in prior),
                    f"Overlapping billing lines for charge_key: {charge}")
            prior.append((ls, le))
            r = None
            if line["resource_id"] is not None:
                r = resources.get(text(line["resource_id"]))
                require(r is not None, f"Unknown billing resource_id: {line['resource_id']}")
                require(charge == r["charge_key"] and identity(line) == identity(r)
                        and line["currency"] == r["currency"] and line["account"] == r["account"],
                        "Billing identity/currency does not match inventory resource")
                require(line["provider_resource_id"] == r["provider_resource_id"],
                        "Billing provider_resource_id does not match inventory")
            else:
                require(charge not in seen_charges,
                        "Billing charge_key matches inventory; provide its resource_id")
                physical = (line["provider"], line["account"], line["region"],
                            line["provider_resource_id"], line["unit"])
                require(physical not in physical_dimensions,
                        "Billing physical resource matches inventory; provide its resource_id")
            actuals.append({**line, "amount": None if amount is None else decimal_text(amount),
                            "kind": r["kind"] if r else None,
                            "specs": resource_specs(r) if r else resource_specs({}),
                            "allocations": distribute(amount, r["allocations"] if r else [])})
            if amount is None:
                warnings.append(f"Billing line {lid}: amount unavailable.")
    else:
        warnings.append("Billing unavailable: actual costs are unknown, not zero.")
    if excluded:
        warnings.append("Excluded scope: " + "; ".join(excluded))
    if not resources:
        warnings.append("Empty inventory: no infrastructure cost coverage.")
    if not any(a["workload"] == workload for r in resources.values() for a in r["allocations"]):
        warnings.append(f"No inventoried allocation links to onboarding engine {workload}; "
                        "its workload cost is unknown.")
    for row in estimates:
        if row["missing_reason"]:
            warnings.append(f"{row['resource_id']}: {row['missing_reason']}")
    warnings.append("Billing absence for a resource is not evidence of zero billed cost; "
                    "exports may be partial, stale, filtered or omit credits.")
    now = datetime.now(timezone.utc)
    freshness = {}
    for name, doc in (("inventory", inventory), ("prices", prices), ("billing", billing)):
        if doc is not None:
            age = now - instant(doc["as_of"])
            freshness[name] = str(Decimal(age.days * 86400 + age.seconds) +
                                  Decimal(age.microseconds) / Decimal(1000000))
            if age.days < 0:
                warnings.append(f"{name}: as_of is in the future; review export freshness.")
    return {
        "schema_version": 1,
        "metadata": {"generated_at": now.isoformat(),
                     "period": inventory["period"], "workload": workload,
                     "engine_template": manifest["engine"]["template"],
                     "nonbillable_workload_context": {
                         "cluster": answers.get("cluster", {}),
                         "helm_values": answers.get("helm", {}).get("values", {}),
                         "roles": answers["engine"].get("roles", []),
                         "interpretation": "Declared sizing/values only; not observed resources or usage."},
                     "evidence": evidence, "inventory_source": inventory["source"],
                     "inventory_as_of": inventory["as_of"], "prices_source": prices["source"],
                     "prices_as_of": prices["as_of"], "billing": billing_meta,
                     "freshness_seconds": freshness,
                     "quantity_convention": "Total provider-unit consumption over the explicit period; "
                     "no implicit 730-hour month, node inference, unit conversion or proration."},
        "resources": list(resources.values()), "estimates": estimates, "actuals": actuals,
        "coverage": {"estimates": summarize(estimates, workload, estimate=True),
                     "actuals": summarize(actuals, workload) if billing is not None else None,
                     "grouped_estimates": grouped_rollups(estimates, workload, estimate=True),
                     "grouped_actuals": grouped_rollups(actuals, workload, estimate=False)
                     if billing is not None else None,
                     "billing_available": billing is not None, "excluded_scope": excluded,
                     "inventory_resources_without_billing": sorted(
                         set(resources) - {a["resource_id"] for a in actuals}),
                     "scope_complete": False},
        "warnings": warnings,
    }


def summarize(rows: list[dict], workload: str, *, estimate=False) -> dict:
    result = {}
    for code in sorted({r["currency"] for r in rows}):
        group = [r for r in rows if r["currency"] == code]
        known = [r for r in group if r["amount"] is not None]
        subtotal = sum((Decimal(r["amount"]) for r in known), Decimal(0))
        attributed = sum((Decimal(a["amount"]) for r in known for a in r["allocations"]
                          if a["workload"] == workload), Decimal(0))
        unallocated = sum((Decimal(a["amount"]) for r in known for a in r["allocations"]
                           if a["workload"] is None), Decimal(0))
        result[code] = {
            "rows": len(group), "known_rows": len(known), "missing_rows": len(group) - len(known),
            "priced_subtotal" if estimate else "billed_subtotal": decimal_text(subtotal),
            "supplied_rows_total": decimal_text(subtotal) if len(known) == len(group) else None,
            "workload_known_subtotal": decimal_text(attributed) if any(
                a["workload"] == workload and a["amount"] is not None
                for r in group for a in r["allocations"]) else None,
            "unattributed_known_subtotal": decimal_text(unallocated),
            "unattributed_rows": sum(any(a["workload"] is None for a in r["allocations"])
                                     for r in group),
            "workload_missing_rows": sum(r["amount"] is None and any(
                a["workload"] == workload for a in r["allocations"]) for r in group),
            "complete_scope_total": None,
        }
    return result


def render_csv(report: dict) -> str:
    out = io.StringIO(newline="")
    columns = ["schema_version", "section", "id", "resource_id", "provider_resource_id",
               "account", "charge_key", "provider", "region", "sku", "unit", "currency",
               "quantity", "quantity_basis", "amount", "missing_reason", "period",
               "price", "allocations", "source", "record_type", "kind",
               *SPEC_TEXT, *SPEC_NUMBERS, "spec_source", "unit_price", "per_node_price",
               "extended_price", "network_usage", "identified_physical_resources",
               "known_quantity_subtotal", "quantity_total",
               "vcpu_total", "ram_gib_total", "disk_gb_total", "disk_iops_total",
               "disk_throughput_mbps_total", "priced_subtotal", "billed_subtotal", "details"]
    writer = csv.DictWriter(out, fieldnames=columns)
    writer.writeheader()
    # JSON cells preserve all evidence and metadata without inventing aggregate money rows.
    for section in ("metadata", "resources", "estimates", "actuals", "coverage", "warnings"):
        value = report[section]
        rows = value if isinstance(value, list) else [value]
        for row in rows:
            record = {"schema_version": report["schema_version"], "section": section,
                      "details": json.dumps(row, sort_keys=True)}
            if section in ("estimates", "actuals"):
                record.update({k: row.get(k) for k in columns if k in row})
                record["id"] = row.get("id", row.get("resource_id"))
                record["period"] = json.dumps(row.get("period", report["metadata"]["period"]))
                for key in ("price", "allocations"):
                    record[key] = json.dumps(row.get(key), sort_keys=True)
                record.update({k: row["specs"][k] for k in (*SPEC_TEXT, *SPEC_NUMBERS)})
                record["spec_source"] = row["specs"]["source"]
            writer.writerow(record)
    for kind in ("estimates", "actuals"):
        for row in report["coverage"]["grouped_" + kind] or []:
            record = {k: v for k, v in row.items() if k in columns}
            record.update({k: v for k, v in row["cost"].items() if k in columns})
            record.update(schema_version=report["schema_version"], section=kind + "_rollups",
                          details=json.dumps(row, sort_keys=True))
            writer.writerow(record)
    return out.getvalue()


def table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [max(len(row[i]) for row in [headers, *rows]) for i in range(len(headers))]
    return "\n".join(" | ".join(value.ljust(widths[i]) for i, value in enumerate(row))
                     for row in [headers, ["-" * w for w in widths], *rows])


def render_txt(report: dict) -> str:
    sections = ["AWC OFFLINE COST REPORT (schema 1)",
                "Workload: " + report["metadata"]["workload"],
                "Estimates are NOT actuals. Totals cover only supplied inventory/exports.",
                "UNKNOWN means missing data, never zero."]
    for kind in ("estimates", "actuals"):
        rows = report[kind]
        sections.append(kind.upper())
        sections.append(table(["ID", "Provider", "Region", "SKU", "Quantity", "Unit", "Rate",
                               "Currency", "Amount"],
                              [[str(r.get("id", r.get("resource_id"))), r["provider"], r["region"],
                                r["sku"], str(r.get("quantity") or "UNKNOWN"),
                                r["unit"], r["price"]["rate"] if r.get("price") else "N/A",
                                r["currency"], r["amount"] or "UNKNOWN"] for r in rows]))
        sections.append(json.dumps(report["coverage"][kind], indent=2))
        sections.append("INFRASTRUCTURE DETAIL (physical counts are not allocated workload counts)")
        detail_keys = ("physical_count", "node_role", "node_type", "vcpu", "ram_gib", "hours",
                       "disk_type", "disk_gb", "disk_iops", "disk_throughput_mbps", "network_type")
        sections.append(table(["ID", *detail_keys, "network_usage", "unit_price", "per_node_price",
                               "extended_price"],
                              [[str(r.get("id", r.get("resource_id"))),
                                *[r["specs"][k] if r["specs"][k] is not None else "UNKNOWN"
                                  for k in detail_keys],
                                *[r.get(k) if r.get(k) is not None else "UNKNOWN"
                                  for k in ("network_usage", "unit_price", "per_node_price",
                                            "extended_price")]] for r in rows]))
        rollups = report["coverage"]["grouped_" + kind]
        sections.append("GROUPED ROLLUPS (do not add to detail costs or sum counts across unit groups)")
        sections.append(table(
            ["Kind", "SKU", "Currency", "Unit", "Physical count", "Usage total", "Known subtotal"],
            [[g["kind"] or "UNKNOWN", g["sku"], g["currency"], g["unit"],
              g["physical_count"] or "UNKNOWN", g["quantity_total"] or "UNKNOWN",
              g["cost"]["priced_subtotal" if kind == "estimates" else "billed_subtotal"]]
             for g in rollups or []]))
        sections.append(json.dumps(rollups, indent=2))
    sections.append("EVIDENCE, RESOURCES, ALLOCATIONS, COVERAGE AND WARNINGS\n" +
                    json.dumps(report, indent=2))
    return "\n\n".join(sections) + "\n"


def write_report(report: dict, output: Path) -> list[Path]:
    artifacts = {"cost-report.json": json.dumps(report, indent=2) + "\n",
                 "cost-report.csv": render_csv(report), "cost-report.txt": render_txt(report)}
    output.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, content in artifacts.items():
        path = output / name
        path.write_text(content, encoding="utf-8")
        paths.append(path)
    return paths
