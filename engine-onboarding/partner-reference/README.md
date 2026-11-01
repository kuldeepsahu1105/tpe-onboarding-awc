# Ideas from partner reference repos (read-only)

We do **not** port agent code, MCP server implementation, `helm-profile.json`, or `partners/<id>/` layouts into ace-engines. Use [`scripts/awc_onboarding.sh`](../scripts/awc_onboarding.sh) + `AWC_ONBOARDING_REPO` for wizard/MCP; [`discover_images.py`](../discover_images.py) for Helm image lists.

## Links

- [awc-partner-engine-agents](https://github.com/Nijjwol23/awc-partner-engine-agents) — Neo4j marketplace run (reference pipeline)
- [tpe-onboarding-awc](https://github.com/kuldeepsahu1105/tpe-onboarding-awc/tree/kuldeepsahu1105-awc-engine-onboarding-toolkit) — extended onboarding (wizard / MCP / ingest); ace-engines [`engine-onboarding/`](../) is the in-monorepo subset
- [awc-oci-register](https://github.com/agupta-git/awc-oci-register)
- [starrocks-ace-engine](https://github.com/agupta-git/starrocks-ace-engine) — engine YAML patterns

## Worth copying (behavior, not code)

- **Validate before mirror/publish** — static checks and `awc-marketplace validate` before touching OCI
- **Mirror then publish** — push charts/images first; publish with `--skip-images --skip-charts` when metadata-only
- **Publish order** — engine bundle, then blueprint with `--instance name=engine:version`
- **Schema version 1** — Partner AWC console sync expectation
- **VPN + registry login** — real push only when credentials and network are ready
- **Catalog sync wait** — ~60s after push before Console listing
- **Human review** — their `--approve-*` flags ≈ our PR review + dry-run publish before `PUSH=1`
- **Skip mirror** when artifacts already live in partner registry (`mirror.skip: true`)

## What ace-engines provides instead

- [`input_form.yaml`](../input_form.yaml) v1 → [`generate_engine.py`](../generate_engine.py) → committed `{directory}/` plugin
- Makefile: `scaffold-engine`, `validate-form`, `discover-images`, `mirror-engine`, `publish-engine`, `register-partner-registry`, `onboarding-wizard`, `onboarding-mcp-config`

See [PARTNER_PIPELINE.md](../PARTNER_PIPELINE.md).
