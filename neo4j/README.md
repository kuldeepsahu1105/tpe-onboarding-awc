# Neo4j ACE Engine

ACE engine for deploying a standalone Neo4j graph database via the official Neo4j Helm chart (Flux `HelmRelease`).

## Architecture

| Aspect | Detail |
|:-------|:-------|
| **Engine name** | `neo4j-engine` |
| **Deployment** | Helm chart (`neo4j`) via ACE `releases` |
| **Neo4j version** | 5.26.x (image catalog) |
| **Chart** | Neo4j Kubernetes Helm chart `2025.12.1` (chart catalog) |

The engine renders an admin `Secret` (`NEO4J_AUTH` plus discrete `username` / `password` keys) and points the chart at it with `neo4j.passwordFromSecret`. A ClusterIP service named like the `EngineInstance` exposes Bolt (`7687`) and HTTP browser (`7474`).

## Prerequisites

- Kubernetes cluster with **ace-operator** installed and running
- **Flux** helm-controller (for chart installs)
- Platform resources:

```bash
kubectl apply -f platform/capabilities.yaml
kubectl apply -f platform/cluster.yaml
```

## Install engine definitions

```bash
cd <ace-engines-repo-path>

kubectl apply -f neo4j/capabilities.yaml
kubectl apply -f neo4j/role.yaml
kubectl apply -f neo4j/imagecatalog.yaml
kubectl apply -f neo4j/chartcatalog.yaml
kubectl apply -f neo4j/engine.yaml
kubectl apply -f neo4j/blueprint.yaml
kubectl apply -f neo4j/examples/instance.yaml
```

Or use root `apply.sh` (plus `kubectl apply -f neo4j/blueprint.yaml`).

## Deploy an instance

```bash
kubectl apply -f neo4j/examples/instance.yaml
kubectl describe engineinstance neo4j
```

## Publish to Partner AWC marketplace

Regenerate from form when changing publish settings:

```bash
make scaffold-engine FORM=tools/engine-onboarding/examples/neo4j.input_form.yaml FORCE=1
```

Sequence (VPN, `docker login`, `helm registry login`, `awc-marketplace` on `PATH`):

```bash
make mirror-engine DIR=neo4j
make publish-engine DIR=neo4j
make publish-engine DIR=neo4j PUSH=1
```

[`publish.sh`](publish.sh) validates then publishes engine + blueprint with `--skip-images --skip-charts` after mirror. See [PARTNER_PIPELINE.md](../tools/engine-onboarding/PARTNER_PIPELINE.md).

Control-plane registry registration (if needed): [`oci-register.config.example.yaml`](oci-register.config.example.yaml) + `make register-partner-registry CONFIG=neo4j/oci-register.config.example.yaml`.

## Configuration

| Parameter | Default | Description |
|:----------|:--------|:------------|
| `edition` | `community` | `community` or `enterprise` |
| `acceptLicenseAgreement` | `no` | Required for Enterprise |
| `storageSize` | `10Gi` | Data PVC size |
| `cpu` / `memory` | `1000m` / `2Gi` | Requests (chart minimums apply) |
| `istioEnabled` | `true` | `AuthConfig` AWC auth toggle |

## Provides

| Capability | Type |
|:-----------|:-----|
| `boltEndpoint` | `endpoint` |
| `browserEndpoint` | `landing-page` |
| `graphDatabase` | `neo4j-graph-database` |
| `credentials` | secret index |

## Dependencies

None (standalone v1).

## Troubleshooting

| Symptom | Check |
|:--------|:------|
| Engine `MissingReferences` | Image/chart catalogs applied |
| HelmRelease failing | Flux helm-controller logs |
| Publish dry-run fails | `awc-marketplace validate neo4j/` |
