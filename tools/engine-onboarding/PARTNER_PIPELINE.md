# Partner pipeline (reference vs ace-engines)

## Two tiers

| | **This repo** [`tools/engine-onboarding/`](.) | **Extended toolkit** [tpe-onboarding-awc](https://github.com/kuldeepsahu1105/tpe-onboarding-awc/tree/kuldeepsahu1105-awc-engine-onboarding-toolkit) |
|---|-----------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|
| Role | Lightweight **in-monorepo** subset: form → ACE YAML under `{directory}/`, `discover-images`, basic `mirror.sh` / `publish.sh`, Makefile wrappers; wizard/MCP via `AWC_ONBOARDING_REPO` | Full partner onboarding: wizard, Web UI, MCP, Helm ingest, multi-template scaffold, blueprint compose, richer validate |
| When to use | Day-to-day engine plugins committed in **ace-engines**; CI-friendly scaffold | Partners need the full guided flow before merging hardened YAML here |

Same `input_form`-style concepts; the extended toolkit lives on GitHub (`awc_onboarding/` on branch `kuldeepsahu1105-awc-engine-onboarding-toolkit`), not vendored in ace-engines.

**Other references (read-only):**

- [awc-partner-engine-agents](https://github.com/Nijjwol23/awc-partner-engine-agents) — staged pipeline example (Neo4j → marketplace)
- [awc-oci-register](https://github.com/agupta-git/awc-oci-register) — partner OCI on AWC control plane (until CCF-95)

Patterns to reuse: [partner-reference/README.md](partner-reference/README.md).

---

## Eight steps (their flow) vs our Makefile

| Step | Nijjwol / extended toolkit | ace-engines (this subset) |
|------|----------------------------|---------------------------|
| 0 Input | `partner.yaml` or toolkit `*.input.yaml` | `input_form.yaml` |
| 1 Ingest | `helm-profile.json` (agents repo) or toolkit `discover-images` | `make discover-images …` → `imageCatalog.images` in form (or hand-edit) |
| 2 Scaffold | Jinja → `partners/<id>/ace/` | `make scaffold-engine FORM=… FORCE=1` |
| 3 Validate | policy + `awc-marketplace validate` | `make validate-form FORM=…`; `./publish.sh` dry-run |
| 4 Mirror | helm/docker → partner OCI | `make mirror-engine DIR=<plugin>` |
| 5 Publish | `awc-marketplace publish` (+ VPN `--push`) | `make publish-engine DIR=<plugin>` then `PUSH=1` |
| 6 Test | catalog inspect + smoke | Manual / cluster |
| 7 CP registry | `MARKETPLACE_REGISTRIES` | `make register-partner-registry CONFIG=…` |
| 8 E2E | Console → Marketplace → Deploy | Same |

Nijjwol uses human gates (`--approve-scaffold`, `--approve-publish`). Here: **PR review** before `FORCE=1`; **dry-run publish** until you pass `PUSH=1`.

---

## Our commands (repo root)

```bash
make discover-images REPO_URL=https://helm.neo4j.com/neo4j CHART=neo4j VERSION=2025.12.1 \
  FORM=tools/engine-onboarding/examples/neo4j.input_form.yaml WRITE=1   # optional
make validate-form FORM=tools/engine-onboarding/examples/neo4j.input_form.yaml
make scaffold-engine FORM=tools/engine-onboarding/examples/neo4j.input_form.yaml FORCE=1
make mirror-engine DIR=neo4j
make publish-engine DIR=neo4j
make publish-engine DIR=neo4j PUSH=1
make register-partner-registry CONFIG=neo4j/oci-register.config.example.yaml

# Extended toolkit (clone tpe-onboarding-awc; set AWC_ONBOARDING_REPO to awc_onboarding/)
make onboarding-wizard
make onboarding-mcp-config
```

With `publish.enabled: true`, scaffold emits `mirror.sh`, `publish.sh`, optional `oci-register.config.example.yaml`.

---

## Dependencies in `input_form.yaml`

| `dependencies.entries[].type` | In Blueprint? |
|-------------------------------|---------------|
| `auto` | No (engine-private, e.g. Postgres) |
| `ref` / `optional` | Yes |

`blueprint.existingEngines[]` — engines already on cluster. Example: [`examples/hms-style.input_form.yaml`](examples/hms-style.input_form.yaml).
