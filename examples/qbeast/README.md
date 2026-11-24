# Qbeast on Anywhere Cloud

This reference package organizes the supplied manifests with a separate
capability contract and registry configuration example. The supplied
Blueprint, Engine, and RBAC are unchanged. They define a Qbeast workspace with
a portal, Spark backend, and MCP endpoint.

| File | Purpose |
| --- | --- |
| `blueprint.yaml` | Marketplace blueprint, instance, and hardware sizing |
| `engine.yaml` | Engine configuration, Flux releases, routes, and health checks |
| `role.yaml` | Namespaced and cluster-scoped permissions for the engine and charts |
| `capability.yaml` | Proposed `qbeast-workspace` contract derived from the engine's provided value |
| `oci-register.config.example.yaml` | Example control-plane registry registration configuration; not ready to apply |
| `imagecatalog.example.yaml`, `chartcatalog.example.yaml` | Catalog placeholders using the engine's known names and IDs |
| `mirror.example.yaml` | Placeholder artifact copy plan, not a complete image inventory |

## Before deployment

These files alone are not a complete standalone installation. Confirm the
target AWC environment has the matching `qbeast-ace-default` ImageCatalog and
`qbeast-ace-charts` ChartCatalog, including the `use` and `portal` images and
the `useEndpoint` and `portal` charts referenced by the engine. Obtain the
exact catalog definitions, chart and image versions, and registry access from
the owner of the working deployment; they were not supplied with this package.
The example catalog files are **not deployable** because their artifact
locations and versions are unknown. Replace the placeholders and verify the
complete chart image inventory before using them. `landing-page` and `mcp-endpoint` are platform
capabilities. Before registering `capability.yaml`, compare its derived schema
with the live `qbeast-workspace` contract and any existing consumers; do not
overwrite an existing incompatible Capability.

The target needs a compatible AWC/ACE platform, Flux, Knox, gateway, and the
registry credentials copied by AWC into `awc-console-registry-creds`. The
blueprint pins Kubernetes `v1.34.3`; verify that the target supports it and its
node sizes before deploying. It requests one control-plane and five worker
nodes by default.

Configure an Iceberg REST catalog using `catalogUri` and `catalogWarehouse`.
Bind a bucket to the `warehouse` storage purpose, or configure the direct S3
settings. For catalog OAuth and static S3 credentials, the engine accepts
credential values in its configuration. Treat the configuration and rendered
resources as sensitive: use authorized secret handling, restrict access, and
never include real credentials in a shared ZIP or commit. Registry credentials
and the Qbeast license must also be provisioned separately.

## Deploy and check

Use your platform's existing engine and blueprint registration process,
including the catalogs and capabilities above. Do not apply these manifests to
an arbitrary cluster or publish them until their dependencies and permissions
have been reviewed. The supplied Role includes CRD creation permissions.
Its RoleBinding references `qbeast-ace-engine-namespaced-role`, and ACE
aggregates the Role and ClusterRole as described in `role.yaml`. The
HelmReleases use the instance service account. Strict-RBAC compatibility of the
actual chart versions and the platform's aggregation policy must be checked on
the target; the charts and a cluster were not supplied.
Once an instance is deployed, check that its `-use` and `-portal` Flux
HelmReleases are Ready, then verify the portal and MCP URLs reported by AWC,
catalog access, and warehouse read/write access. `mcpKnoxOAuth` defaults to
true and exempts discovery, registration, and token paths across the
namespace; review the engine's authentication configuration for your
environment.

The manifests were supplied as working files; this package does not establish
that a different target environment is configured or that a deployment has
been tested there.

## Registry and mirroring

The onboarding toolkit provides `make register-partner-registry CONFIG=...`
for `awc-oci-register` and `make mirror-engine DIR=...` for a bundle with a
configured `mirror.sh`. Registry registration and mirroring are different:
registration configures control-plane access; mirroring copies artifacts.
The example configuration and mirror plan are not ready to use. Obtain the actual source and
destination registries, chart versions, and complete image list before creating
a mirror plan. No Qbeast mirror or publish script is supplied with guessed
destinations. Operations need the appropriate tools, access, and approval.

## Current integration boundaries

- The engine uses catalog form settings rather than a Harmony `ref` dependency:
  its supplied comments report a Console limitation for existing instances.
- Spark executor dynamic allocation is configured; Kubernetes node
  autoscaling is not configured by these manifests.
- UDF/Ranger policy provisioning and Cloudera-specific portal branding are not
  configured here. They require their platform integration and portal/chart
  support respectively.
