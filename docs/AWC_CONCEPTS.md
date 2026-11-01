# AWC concepts (as used by this toolkit)

| Resource | What it is | Generated file |
|---|---|---|
| **Blueprint** | The Marketplace app (e.g. DataSpark). Lists engine *instances*, how they are wired, versions and cluster sizing. | `blueprint.yaml` |
| **Engine** | One deployable component: config schema, what it `provides`, `dependencies`, health checks, and a Go-template `spec.template`. | `engine.yaml` |
| **Capability** | A typed contract an engine exports (e.g. a DB connection). | `capability.yaml` |
| **ChartCatalog / ImageCatalog** | Registry locations of Helm charts / images. | `chartcatalog.yaml`, `imagecatalog.yaml` |
| **Operator** | Installs a K8s operator for `helm-operator` engines. | `operator.yaml` |
| **Role** | RBAC for the engine. | `role.yaml` |
| **ClusterRequirements / Mirror** | Cluster prerequisites; chart/image mirroring. | `clusterrequirements.yaml`, `mirror.yaml` |

## Engine template classes
`helm-simple`, `helm-multi-role`, `helm-operator`, `native-k8s`.

## Dependency types
- `auto`: private, same lifecycle; the operator creates it. **Not** shown in a Blueprint.
- `optional`: Console-wireable to an existing instance; listed in the Blueprint.
- `ref`: a required reference to an existing instance; listed in the Blueprint.

A dependency's `engine` can be an engine you onboard yourself, a Cloudera-native
engine (CDE, CAI, CDF, ...), or any third-party engine already on the cluster.

## Blueprint composition
One Blueprint = one app. It may contain your engines plus engines that already
exist (`existing:`), e.g. PhoenixAI + CAI + CDE + CDF in one Blueprint.
Dependencies between engines in the same Blueprint are resolved to instance names automatically.
Existing engines contribute an instance but no node group (their sizing is not known to the toolkit).
