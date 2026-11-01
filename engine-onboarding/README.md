# ACE engine onboarding (in-monorepo subset)

[`engine-onboarding/`](.) is the **lightweight** path for plugins that live in **ace-engines**: `input_form.yaml` → generated `{directory}/` (Engine, catalogs, optional Blueprint, basic mirror/publish scripts).

**Helm image discovery** runs in-repo (`discover_images.py`). **Wizard, Web UI, and MCP** delegate to **[tpe-onboarding-awc](https://github.com/kuldeepsahu1105/tpe-onboarding-awc/tree/kuldeepsahu1105-awc-engine-onboarding-toolkit)** (the repository root on branch `kuldeepsahu1105-awc-engine-onboarding-toolkit`) via `AWC_ONBOARDING_REPO` and Makefile wrappers — not vendored here. Typical flow: discover images / run the extended wizard, produce `input_form.yaml`, scaffold into ace-engines, then merge production-ready YAML.

**In-repo subset + Neo4j sample on GitHub:** [ace-inrepo-onboarding-tool](https://github.com/kuldeepsahu1105/tpe-onboarding-awc/tree/ace-inrepo-onboarding-tool) (`tools/engine-onboarding` + `neo4j/`).

Partner pipeline comparison: **[PARTNER_PIPELINE.md](PARTNER_PIPELINE.md)** · reference notes: **[partner-reference/](partner-reference/README.md)**

---

## Quick start

```bash
cd ace-engines

make validate-form FORM=engine-onboarding/input_form.minimal.example.yaml
make scaffold-engine FORM=engine-onboarding/input_form.minimal.example.yaml FORCE=1
```

Optional: **`make serve-engine-form`** (http://127.0.0.1:8766) exports the same YAML shape as the CLI form.

Neo4j example (includes generated `mirror.sh` / `publish.sh` when `publish.enabled: true` in form):

```bash
# Optional: refresh imageCatalog.images from the upstream Helm chart (needs helm)
make discover-images REPO_URL=https://helm.neo4j.com/neo4j CHART=neo4j VERSION=2025.12.1 \
  FORM=engine-onboarding/examples/neo4j.input_form.yaml WRITE=1

make scaffold-engine FORM=engine-onboarding/examples/neo4j.input_form.yaml FORCE=1
make mirror-engine DIR=neo4j
make publish-engine DIR=neo4j              # dry run
make publish-engine DIR=neo4j PUSH=1 APPROVE_PUBLISH=1   # after review (VPN/registry)
```

Extended toolkit (wizard / MCP) — clone once, then:

```bash
export AWC_ONBOARDING_REPO=$HOME/tpe-onboarding-awc   # repository root
make onboarding-wizard
make onboarding-mcp-config   # JSON for Cursor MCP settings
```

Requirements: Python 3.9+, PyYAML. Optional: `jsonschema` for schema validation.

---

## `input_form.yaml` (v1)

| Section | Purpose |
|---------|---------|
| `version` | Must be `v1` |
| `directory` | Output folder name (`neo4j`, `my-service`, …) |
| `engine` | `name`, `displayName`, `description`; optional `operator` |
| `dependencies.entries[]` | `auto` \| `ref` \| `optional` (Polaris/HMS-style) |
| `imageCatalog` / `chartCatalog` | Pinned images and charts |
| `helm` | `chartID` + values (ACE Go templates preserved) |
| `mirror` / `publish` | Generates `mirror.sh`, `publish.sh` |
| `ociRegister` | Example `oci-register.config.example.yaml` |
| `blueprint` | Optional Blueprint; `existingEngines[]` for refs already on cluster |
| `provides`, `configSchema`, `healthChecks`, `capabilities`, `features`, `rbac` | As in existing engines |

Schema: [`input_form.schema.yaml`](input_form.schema.yaml). Examples: [`input_form.minimal.example.yaml`](input_form.minimal.example.yaml), [`examples/neo4j.input_form.yaml`](examples/neo4j.input_form.yaml), [`examples/hms-style.input_form.yaml`](examples/hms-style.input_form.yaml).

---

## Makefile (repo root)

| Target | Description |
|--------|-------------|
| `make scaffold-engine FORM=…` | Generate plugin under `{directory}/` |
| `make validate-form FORM=…` | Validate form file |
| `make mirror-engine DIR=…` | Run generated `mirror.sh` |
| `make publish-engine DIR=…` | Run `publish.sh`; `PUSH=1` to push |
| `make register-partner-registry CONFIG=…` | [awc-oci-register](https://github.com/agupta-git/awc-oci-register) wrapper |
| `make serve-engine-form` | Simple JSON Schema HTML form |
| `make build-ui-schema` | Refresh `web/input_form.ui.schema.json` |
| `make discover-images REPO_URL=… CHART=… VERSION=…` | List chart images (`discover_images.py`); `FORM=… WRITE=1` merges into form |
| `make onboarding-wizard` | Terminal Q&A (requires `AWC_ONBOARDING_REPO`) |
| `make onboarding-ui` | Extended Web UI (`./awc ui`) |
| `make onboarding-mcp` | MCP server for AI assistants |
| `make onboarding-mcp-config` | Print MCP client JSON |

Use `FORCE=1` / `DRY_RUN=1` with `scaffold-engine` as needed. Optional: `VALUES=file.yaml` / `SET=key=val` on `discover-images`.

---

## Scope ( intentionally small )

- Helm-first scaffold into ace-engines layout; not operator-first or multi-chart automation
- In-repo **discover-images** only; wizard/MCP/ingest/agents live in **tpe-onboarding-awc** (wrappers above)
- RBAC presets are minimal; production engines still need review (mesh, docs, e2e)

When you outgrow this subset, use **tpe-onboarding-awc** for blueprint compose and multi-template bundles, then commit the result here.
