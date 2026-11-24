# Offline cost reporting

`cost-report` joins an **actual onboarding input's engine identity** to explicit
inventory allocations, prices the inventoried provider units, and optionally
reports billed costs from a local billing export. It never accesses credentials,
cloud APIs, Kubernetes, Helm, a registry or a deployment command.
This is a separate, additive, opt-in CLI command. Wizard/build/generate/validate,
publish scripts, UI and MCP behavior and output paths are unchanged; they do not
require inventory, prices, billing data or any new dependency.

## Audit and deployment boundary

The current CLI (`onboarding/cli.py`) loads answers, normalizes them with
`onboarding/manifest.py`, and renders ACE YAML with `onboarding/generator.py`.
`cluster.workerCountDefault`, CPU/memory minima and disk defaults become
`ClusterRequirements` sizing metadata. In `helm-simple`, CPU/memory become
per-pod requests/limits passed to the chart, whose behavior still depends on the
chart. The native template creates a Deployment/PVC/Service; other template
classes have different role/operator behavior. These are not observed nodes,
provider instance SKUs, utilization measurements or billing evidence.

Bundle generation is not infrastructure provisioning. Generated mirror/publish
and smoke-test scripts have separate registry/marketplace/cluster side effects;
**cost reporting does not run them**. An EngineInstance is later reconciled by AWC.
No CPU-to-node conversion or dedicated-node inference is made, and pod replicas,
PVC defaults, embedded gateways, dependencies and operators are not priced a
second time on top of an inventoried node. Inventory must explicitly include
their distinct billable components, if any.

## Exact paths, editing and safe execution

From the repository root:

```bash
mkdir -p cost-input
cp examples/costs/inventory.json cost-input/inventory.json
cp examples/costs/prices.json cost-input/prices.json
cp examples/costs/billing.json cost-input/billing.json
vi examples/neo4j.input.yaml
vi cost-input/inventory.json
vi cost-input/prices.json
vi cost-input/billing.json
```

In `vi`, press `i` to edit, then `Esc`, `:wq`, Enter to save; `:q!` discards.
Use your own onboarding input rather than changing the tracked example in normal
usage. Edit source inputs, never generated reports. Keep account exports outside
version control; do not store secrets in exports or evidence labels.

The examples are **synthetic demo-provider data**, not live AWS/Azure/GCP prices
or a real invoice. Replace the provider, account, physical resource IDs, region,
SKU, unit, currency, source references, dates, quantities and allocation evidence
with reviewed exports. Use `engine.name` as the allocation workload, or its
normalization default `<partner.id>-ace-engine` (partner IDs are lowercased with
spaces/underscores replaced by hyphens). For the example it is
`neo4j-ace-engine`. The report preserves declared cluster sizing, Helm values and
roles as **nonbillable context** so the allocation is traceable to the input,
not to guessed hardware.
Keep this YAML context JSON-compatible: quote date/time values, and do not use
YAML sets, nonfinite numbers or circular aliases.

With the toolkit's Python dependencies already installed:

```bash
python3 -m onboarding.cli cost-report \
  --file examples/neo4j.input.yaml \
  --inventory cost-input/inventory.json \
  --prices cost-input/prices.json \
  --billing cost-input/billing.json \
  --out output/cost-report
```

Alternatively, `./awc cost-report` accepts exactly the same flags. The wrapper's
normal first-run setup may install Python dependencies over the network; the
report command itself is offline. For strictly offline execution use an already
prepared interpreter/environment and `python -m onboarding.cli`.

| Parameter | Meaning |
|---|---|
| `--file` | Required source onboarding YAML/JSON; no session is created or changed |
| `--inventory` | Required version-1 normalized inventory JSON path |
| `--prices` | Required version-1 normalized provider ratecard JSON path; `rates: []` is allowed |
| `--billing` | Optional version-1 normalized billing JSON path; omit when unavailable |
| `--out` | Output directory, default `output/cost-report` (relative to toolkit root, regardless of current directory) |

Outputs are `cost-report.txt`, `cost-report.json` and `cost-report.csv`. The
command prints their paths. Existing files with these names are replaced only
after inputs are validated. Do not point `--out` at source input directories.
Malformed input prints `Cost report error: ...` to stderr and exits 1 without
writing a new report. A valid but incomplete report exits 0; inspect coverage
and warnings, not just the exit status.

## Normalized export contract (schema_version 1)

All three exports are UTF-8 JSON objects with integer `schema_version: 1`.
The complete executable shapes are in `examples/costs/*.json`. Required keys
must be present; unrecognized keys and duplicate JSON keys are errors. Raw AWS
CUR, Azure Cost Management, GCP billing CSV/JSON and provider pricing catalogs
have different schemas; they are **not accepted verbatim**. Normalize them
offline to this contract, keeping original export URI/file/row/version in
`source`, then pass the normalized JSON paths above. The report records paths
and SHA-256 hashes of every input. It cannot authenticate the files or confirm
that a claimed provider price is genuine.

Numbers used in arithmetic must be decimal **strings**, not JSON floats:
`"744"`, `"0.20"`, `"-10.00"`. Up to 24 digits and 12 decimal places are accepted;
exponents, NaN/infinity, booleans and negative quantities/rates are rejected.
Arithmetic uses a local 100-digit Decimal context with no float conversions or
cent rounding. Monetary outputs are exact decimal strings or `null`, and
allocation amounts reconcile before display rounding.

Every `period` is `{start, end}` with timezone-bearing ISO timestamps; start is
inclusive and end exclusive, and start must precede end. Report quantity is
**total consumption in the stated provider unit over this period**, not a rate
per hour automatically multiplied by runtime. For October, a continuously
running node would use 744 node-hours; a 10-hour deployment uses 10. A
GiB-month amount requires the provider's month/proration convention documented
in `quantity_basis`. No implicit 730-hour month, calendar conversion, tiering,
proration, exchange rate or unit conversion is performed.

### Inventory

Top-level keys: `schema_version`, `source`, `as_of`, `period`, `resources`,
`excluded_scope` (array of strings; explicitly declare omitted scope).
`as_of` identifies export freshness, not the assumed runtime.

Each resource requires:

| Key | Meaning |
|---|---|
| `id` | Unique local billing-component ID, referenced by billing `resource_id` |
| `provider_resource_id` | Stable original provider resource identifier, not a pod request or a display label |
| `account` | Provider account/subscription/project identifier |
| `charge_key` | Unique component key, e.g. `<provider-resource-id>/compute`; keep stable across estimate and billing |
| `kind` | `node`, `storage`, `network`, `load_balancer`, `control_plane`, `license`, `other` |
| `provider`, `region`, `sku`, `unit`, `currency` | Exact pricing identity; currency is three uppercase letters |
| `quantity` | Nonnegative decimal-string consumption, or `null` when unknown |
| `quantity_basis`, `source` | Explicit assumptions and inventory row evidence |
| `tenancy` | `dedicated`, `shared`, `unattributed` |
| `allocations` | Array of `{workload, fraction, method, source}` |

An allocation must identify a workload, a decimal-string fraction greater than
0 and at most 1, its method (e.g. measured node-hour share, reviewed fixed share)
and provenance. Fractions across workloads must sum to at most 1; the remainder
is explicitly **unattributed**. A dedicated resource requires exactly one
fraction of 1 backed by evidence; an unattributed resource requires no
allocations. Shared resources are counted once at gross resource cost, then
allocated, never duplicated as dedicated nodes per engine.

Duplicate IDs, charge keys and physical provider/account/region/resource/unit
dimensions are rejected even if renamed or assigned a different SKU/currency.
For a component covered by a bundled price, do not also inventory the included
components. Unit/ID aliases and semantic overlap cannot be discovered offline;
this conservative format supports one nonoverlapping component per physical
resource/unit. Normalize more complex multi-meter/bundled exports before use.

#### Optional infrastructure specifications

Each resource may include `specs`, an object with required nonempty `source`
(the node/disk/network export row or reviewed specification evidence). All
other spec keys are optional and nullable:

| Keys | Type and interpretation |
|---|---|
| `node_role`, `node_type` | Strings, e.g. worker/control-plane and provider instance type; not pod sizing |
| `physical_count` | Decimal string `"1"` only: one stable `provider_resource_id` per inventory row; list every physical ID rather than an aggregate fleet |
| `vcpu`, `ram_gib` | Nonnegative decimal strings, capacity per physical resource, not allocated workload requests |
| `hours` | Nonnegative decimal string for nodes with unit `node-hour`; must equal the individually inventoried node's consumption `quantity` when known |
| `disk_type`, `disk_gb`, `disk_iops`, `disk_throughput_mbps` | Disk type string and nonnegative decimal-string capacity/specs; GB is decimal GB, throughput is MB/s, not GiB/MiB; no implicit conversions |
| `network_type` | String describing the usage meter, e.g. internet-egress or inter-zone; network usage and rate come from the resource's explicit `quantity`, `unit` and matched price |

Absent specs produce nulls/UNKNOWN, not fabricated hardware. Each supplied
spec is backed by `specs.source`. `physical_count` is independent of usage and
allocation: a shared node with a 25% engine fraction is still one physical
node, not 0.25 nodes. No machine count or hardware specs are inferred from
requests, limits, replicas, SKU names or elapsed calendar time.

Estimate details expose `unit_price`, `extended_price` (the same amount as
quantity times valid rate), `network_usage` for network rows, and
`per_node_price` (the full-period amount for one explicitly counted node).
`per_node_price` is not an hourly rate; `unit_price` is the provider-unit rate.
Actual billing amounts remain exported amounts, not recomputed estimates;
actual spec details reuse mapped inventory evidence, while unknown actual
quantities/per-node prices remain unavailable.

`coverage.grouped_estimates` and `grouped_actuals` group by provider, account,
region, kind, SKU, unit, currency, node role/type, disk type and network type.
Each group includes distinct physical IDs, `identified_physical_resources`,
explicit `physical_count` (null if any count is unavailable), known usage
subtotal/full quantity total (estimate only), capacity/spec totals (null when
any contributing physical spec is unknown), and the same separate cost
coverage as detail rows. Repeated actual charge/credit rows do not multiply
physical counts or capacity. Missing price rows still contribute known
physical specs but not invented cost.

TXT includes detail and grouped tables plus complete JSON evidence. CSV has
flat spec/rate/count columns and extra `estimates_rollups`/`actuals_rollups`
sections with full group JSON in `details`. These are alternative summaries,
not extra charges. Never sum rollup costs with detail costs; never sum physical
counts/capacities across unit groups (one physical resource may have multiple
distinct meters). The count of identified physical IDs is not proof of export
completeness, and no workload-specific physical count is claimed.

### Prices

Top-level keys: `schema_version`, `source`, `as_of`, `rates`.
Each rate requires `provider`, `region`, `sku`, `unit`, `currency`, `rate`,
`source`, `as_of`, `valid_from`, `valid_to`. Its source should identify the
provider price-list version/URI/export row and purchase model (on-demand,
reserved, negotiated, etc.). SKU must distinguish OS, tenancy and purchase
model where those affect price.

One exact, case-sensitive rate per provider/region/SKU/unit/currency is accepted.
Duplicate keys are ambiguous and rejected. A matching rate must be valid for
the **entire report period**. Missing/expired/mismatched rates or null quantities
produce null resource amounts with a reason, not invented zero rates. For
varying or tiered rates, prepare separate nonoverlapping reports with appropriate
normalized quantities/rates. No live provider lookup is attempted.

### Billing

Top-level keys: `schema_version`, `source`, `as_of`, `period`, `metric`,
`project`, `tags` (string-to-string object), `allocation_limitations` (strings),
`lines`. Period must equal inventory period. Choose exactly one consistent
`metric`: `net_cost`, `gross_cost` or `amortized_cost`. Do not mix metrics or
include an aggregate invoice total alongside its detail rows.

Each line requires `id`, `account`, `provider_resource_id`, `charge_key`,
`resource_id`, `provider`, `region`, `sku`, `unit`, `currency`, `amount`,
`record_type`, `period`, `source`.

`resource_id` refers to inventory, or is `null` for an unmapped physical resource.
Mapped identities/account/currency/charge key must agree exactly; their billing
amount is allocated using the same explicitly supplied inventory shares.
An unmapped line stays fully unattributed; it cannot silently match an
inventoried physical dimension without a reference. Line windows must be
contained in the report period; they are not automatically prorated. Two
charge windows (or two credit windows) for the same physical resource/unit
cannot overlap, even under different line IDs or charge-key aliases.
Aggregate legitimate same-window charge/credit rows offline, preserving their
row references in `source`. Charges and credits may overlap each other.

`amount` is a decimal string or `null` when unavailable. `record_type: charge`
requires a nonnegative amount; `credit` requires a nonpositive amount. Include
credits separately **only if not already included in the exported cost metric's
charge amount**. Signed actual subtotals can be negative. No estimate is added
to an actual. Mixed currencies remain separate; a mapped billing currency
mismatch is an error, never implicitly converted.

Export `as_of`, project/tag filters, metric, line time windows and allocation
limitations are preserved. `freshness_seconds` is export age relative to report
generation (negative/future dates raise a warning); no universal staleness SLA
is assumed. An old or partial billing export is not a complete invoice, and a
fixed allocation is not a workload-attributed charge from the provider.

## Output and reconciliation

The versioned JSON always has `metadata`, `resources`, `estimates`, `actuals`,
`coverage`, `warnings`. TXT shows separate estimate/actual tables, currency
coverage summaries and the complete evidence payload. CSV is a single
section-tagged file with a `schema_version` column: resource estimate and billing rows have flat identity/money
columns; `details` contains the complete JSON value for **every section**.
`price`, `allocations` and `period` cells also contain JSON. Reading each
section's `details` reconstructs the JSON report without losing provenance,
warnings or nulls. An empty flat monetary cell means unknown, not zero.

Sum only `amount` on rows of **one** section and currency; do not sum resource
metadata, allocation cells, summary `details`, or estimates together with
actuals. Allocation amounts including the unattributed remainder sum to the
underlying row's amount. Gross inventory costs are not all this engine's costs:
`workload_known_subtotal` uses only allocations matching the onboarding engine.
If no known allocation links to that engine it is null, not a claim of zero.

Coverage is per currency:

- `priced_subtotal` (estimates) / `billed_subtotal` (actuals) sums only known rows.
- `rows`, `known_rows`, `missing_rows` describe **row coverage**, not spend-weighted completeness.
- `supplied_rows_total` is null if any supplied row is unknown; otherwise it is only the total of supplied rows, not a complete account/workload bill.
- `workload_missing_rows`, `unattributed_rows` and `unattributed_known_subtotal` expose partial attribution.
- `complete_scope_total` is always null, and `scope_complete` is false: offline inputs cannot establish complete deployment or billing scope.

Omitting `--billing` produces `actuals: []`, `billing_available: false` and null
actual coverage. An available empty export instead has empty actual coverage,
not a zero bill. Resources lacking billing lines are listed explicitly.
Empty inventory cannot be replaced by pod sizing; no infrastructure is inferred.

The synthetic example intentionally leaves storage unpriced: USD priced
subtotal is **148.80**, known workload estimate **37.20**, estimate
`supplied_rows_total` null; billed subtotal is separately **120.00** including
a -10.00 credit, with known workload actual **30.00**. Neither is a complete
workload cost. Provider-specific raw parsers, measured utilization collection,
automatic shared-cost attribution, taxes, rate tiers, currency conversion,
forecasting and complete invoice reconciliation are not implemented.

Run the offline regression suite from the repository root:

```bash
python3 -m unittest discover -s tests -v
```
