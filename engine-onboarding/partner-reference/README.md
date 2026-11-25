# Ideas from partner reference repos (read-only)

This directory records patterns from external partner repositories; it is not the onboarding application. Wizard, Web UI, MCP, image discovery, and both generators are available locally from the repository root.

## Links

- [awc-partner-engine-agents](https://github.com/Nijjwol23/awc-partner-engine-agents) — Neo4j marketplace run (reference pipeline)
- [tpe-onboarding-awc](https://github.com/kuldeepsahu1105/tpe-onboarding-awc) — this repository's current onboarding implementation
- [awc-oci-register](https://github.com/agupta-git/awc-oci-register)
- [starrocks-ace-engine](https://github.com/agupta-git/starrocks-ace-engine) — engine YAML patterns

## Worth copying (behavior, not code)

- **Validate before mirror/publish** — static checks and `awc-marketplace validate` before touching OCI
- **Mirror then publish** — push charts/images first; publish with `--skip-images --skip-charts` when metadata-only
- **Publish order** — engine bundle, then blueprint with `--instance name=engine:version`
- **Marketplace schema version 2** — required for the current v1alpha10 publish contract
- **VPN + registry login** — real push only when credentials and network are ready
- **Catalog sync wait** — ~60s after push before Console listing
- **Human review** — their `--approve-*` flags ≈ our PR review + dry-run publish before `PUSH=1`
- **Skip mirror** when artifacts already live in partner registry (`mirror.skip: true`)

## What ace-engines provides instead

- `engine-onboarding/examples/*.input_form.yaml` v1 → `generate_engine.py` compatibility CLI → `{directory}/` package
- Root `examples/*.input.yaml` → `./awc build` → validated multi-template bundle
- Makefile and `./awc`: `scaffold-engine`, `validate-form`, `discover-images`, `mirror-engine`, `publish-engine`, `register-partner-registry`, wizard, Web UI, and MCP

See [PARTNER_PIPELINE.md](../PARTNER_PIPELINE.md).
