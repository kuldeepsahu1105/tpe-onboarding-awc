# ACE engine onboarding

This repository supports two input formats through one shared onboarding package:

- The primary `awc` pipeline reads `examples/*.input.yaml` manifests and generates validated bundles with Jinja templates.
- The compatible `engine-onboarding` CLI reads the separate `input_form` v1 schema and generates its Helm-first package layout. Its implementation is in `onboarding/form_generator.py`; `generate_engine.py` remains the CLI and import-compatibility entry point.

The schemas stay distinct, but both paths share current Blueprint construction, YAML/catalog rendering, and marketplace schema-version defaults. Do not copy fields between the two input formats without translating them.

Helm image discovery, terminal wizard, Web UI, and MCP are all available in this repository. Start the workbench with `./awc ui`; no external `AWC_ONBOARDING_REPO` clone is required.

Partner pipeline comparison: **[PARTNER_PIPELINE.md](PARTNER_PIPELINE.md)** · reference notes: **[partner-reference/](partner-reference/README.md)**

---

## Quick start

```bash
make validate-form FORM=engine-onboarding/examples/minimal.input_form.yaml
make scaffold-engine FORM=engine-onboarding/examples/minimal.input_form.yaml FORCE=1
```

Optional: **`make serve-engine-form`** (http://127.0.0.1:8766/web/) edits the `input_form` v1 shape. For the primary workflow, use **`./awc ui`**.

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

Primary workflow (wizard / web UI / MCP):

```bash
./awc wizard
./awc ui
./awc mcp
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

Schema: [`input_form.schema.yaml`](input_form.schema.yaml). Examples: [`examples/input_form.minimal.example.yaml`](examples/input_form.minimal.example.yaml), [`examples/neo4j.input_form.yaml`](examples/neo4j.input_form.yaml), [`examples/hms-style.input_form.yaml`](examples/hms-style.input_form.yaml).

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
| `make onboarding-wizard` | Terminal Q&A from the primary onboarding pipeline |
| `make onboarding-ui` | Primary onboarding Web UI (`./awc ui`) |
| `make onboarding-mcp` | MCP server for AI assistants |
| `make onboarding-mcp-config` | Print MCP client JSON |

Use `FORCE=1` / `DRY_RUN=1` with `scaffold-engine` as needed. Current v1alpha10 publish scripts default to marketplace schema version 2. Optional: `VALUES=file.yaml` / `SET=key=val` on `discover-images`.

---

## Scope

- The `input_form` v1 generator remains Helm-first; use the primary `awc` pipeline for multi-template and operator workflows.
- The two input schemas are intentionally separate; they share rendering helpers but have different fields and validation.
- RBAC presets are minimal; production engines still need review (mesh, docs, e2e)
