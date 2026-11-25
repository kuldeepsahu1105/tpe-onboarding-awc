# Partner onboarding pipeline

This repository contains two supported input paths with different schemas and command entry points:

| Path | Input | Entry point | Best for |
|---|---|---|---|
| Primary onboarding | `examples/*.input.yaml` | `./awc build <file>` | Guided partner workflow, multiple templates, current Blueprints, validation, mirroring, publishing |
| Form-v1 compatibility | `engine-onboarding/examples/*.input_form.yaml` | `make scaffold-engine FORM=...` | Existing Helm-first form workflows and their generated package layout |

Both generators use the `onboarding` package and share Blueprint construction, catalog/YAML rendering, and the v1alpha10 marketplace publish schema default. The `input_form` v1 schema remains distinct; translate data explicitly rather than treating it as interchangeable with primary `*.input.yaml`.

## Form-v1 workflow

```bash
make discover-images REPO_URL=https://helm.neo4j.com/neo4j CHART=neo4j VERSION=2025.12.1 \
  FORM=engine-onboarding/examples/neo4j.input_form.yaml WRITE=1
make validate-form FORM=engine-onboarding/examples/neo4j.input_form.yaml
make scaffold-engine FORM=engine-onboarding/examples/neo4j.input_form.yaml FORCE=1
make mirror-engine DIR=neo4j
make publish-engine DIR=neo4j
make publish-engine DIR=neo4j PUSH=1
make register-partner-registry CONFIG=neo4j/oci-register.config.example.yaml
```

The generated package defaults to marketplace schema version 2. Publishing remains a dry run unless `PUSH=1` is selected; validate artifacts and registry access before an actual push.

## Primary workflow

```bash
./awc wizard
./awc build examples/neo4j.input.yaml
./awc ui
./awc mcp
```

For multi-engine Blueprint composition, use `./awc blueprint <blueprint.input.yaml>`. The supported current contract uses top-level Engine `imageCatalog` and (for Helm engines) `chartCatalog` references. The explicit legacy Blueprint mode remains available for older deployment contracts; it should not be used for v1alpha10 packages that require the current shape.

## External references

- [awc-partner-engine-agents](https://github.com/Nijjwol23/awc-partner-engine-agents) — staged pipeline example
- [awc-oci-register](https://github.com/agupta-git/awc-oci-register) — partner OCI registration
