# Qbeast on Anywhere Cloud

Qbeast engine 1.3.12 and its Blueprint in `examples/qbeast/`.
Qbeast makes lakehouse tables faster to query and less
costly to run, and serves them to AI agents through a built-in MCP server.

The manifests are hand-authored, not generated from an `*.input.yaml`: the engine
renders Flux objects, two HTTPRoutes and a Knox AuthConfig in its template, which no
toolkit template covers. Source of truth: `qbeast-ace-engine/` in
`Qbeast-io/cloudera-awc`.

| File | What it is |
| --- | --- |
| `engine.yaml` | The Engine: Flux HelmRepositories and HelmReleases for USE (Spark backend and MCP server) and the portal, HTTPRoutes, Knox AuthConfig for MCP, settings, health checks |
| `blueprint.yaml` | The Marketplace tile: one `qbeast-ace-workspace` instance (engine 1.3.12 or later), hardware tier sizing |
| `role.yaml` | Role, ClusterRole and RoleBinding the engine's charts need under strict ACE RBAC |
| `capabilities.yaml` | `qbeast-workspace` contract: the public `portal` and `mcp` URLs, both required. Spark Connect is not exported |
| `imagecatalog.yaml` / `chartcatalog.yaml` | Pinned images and charts of USE release 0.10.1, at their source (`registry.example.invalid`) |
| `mirror.yaml` + `mirror.sh` | Copy plan and script: from `registry.example.invalid` to your registry |
| `publish.sh` | Lint and publish with `awc-marketplace` (dry run by default) |
| `oci-register.config.example.yaml` | `awc-oci-register` config for the registry you publish to |
The supplied bundle did not include `examples/instance.yaml` or a smoke-test
script. Obtain and review a deployment-specific EngineInstance before direct use.

## Artifacts

| Catalog id | Source | Version |
| --- | --- | --- |
| image `use` | `registry.example.invalid/replace-me/image-1` | `aws-use-v0.10.7` |
| image `portal` | `registry.example.invalid/replace-me/image-2` | `v0.8.5` |
| chart `useEndpoint` | `oci://registry.example.invalid/replace-me/chart-1` | `1.24.0` |
| chart `portal` | `oci://registry.example.invalid/replace-me/chart-2` | `1.8.0` |

That is the complete inventory: the charts pull no other image (the Spark executors
and MCP sessions run the `use` image). Both images are multi-arch (amd64, arm64).

`registry.example.invalid` needs the registry license key Qbeast gave you (password; the
username is not checked). It serves only artifacts of final product releases.
**Until USE 0.10.1 is final, it answers `DENIED: tag not released` for the four
versions above:** mirroring and a real publish wait for that release. See the
reported checks and limits below; validate against your own environment.

## Publish

1. Log in to both registries. For the Qbeast one:

   ```bash
   KEY=/path/to/qbeast-registry.license
   tr -d '\n' < "$KEY" | helm registry login registry.example.invalid -u license --password-stdin
   tr -d '\n' < "$KEY" | crane auth login registry.example.invalid -u license --password-stdin
   ```

   `awc-marketplace` and skopeo read the Docker credentials (`~/.docker/config.json`)
   that `crane auth login` or `docker login` write; helm keeps its own.

2. Optional: copy the artifacts ahead of the publish.

   ```bash
   DEST_REGISTRY=<your registry> DEST_NAMESPACE=<marketplace namespace> ./mirror.sh
   ```

3. Publish. The engine publish copies whatever is still missing to
   `<REGISTRY>/<NAMESPACE>/images/<name>` and `.../charts/<name>` (the same paths
   `mirror.sh` uses) and repoints the published catalogs at the copies. The bundle's
   own catalogs keep the source.

   ```bash
   REGISTRY=<your registry> NAMESPACE=<marketplace namespace> ./publish.sh          # dry run
   REGISTRY=<your registry> NAMESPACE=<marketplace namespace> ./publish.sh --push
   ```

   Schema version 2: the manifests are `v1alpha10`. The engine is published under the
   Blueprint instance's `minimumVersion` (1.3.12).

4. If the Console doesn't know the registry yet, register it with
   `oci-register.config.example.yaml` (`make register-partner-registry CONFIG=...`),
   then restart `awc-console`: it reads the registry list when it starts.

Workload clusters pull the images and charts with `awc-console-registry-creds`, the
Secret AWC copies into every namespace. They never reach `registry.example.invalid`.

## Deploy and check

Deploy the Qbeast tile from the Console after configuring the catalog and bucket.

Through the Console the instance is named `<cluster>-inst-qbeast-ace-workspace`. The
portal is at `https://<instance>.<cluster domain>` (Cloudera SSO), the MCP server at
`https://<instance>-mcp.<cluster domain>/mcp` (Knox).

**License.** The registry license key only pulls artifacts. The product license is
separate: the customer enters it on the portal's license page, which stores it in the
workspace's `qbeast-license` Secret. Since 1.3.12 the portal no longer reads
`awc-console-registry-creds` to prefill it: that Secret holds your registry
credentials, which the portal shouldn't see.

## Settings

The Console builds the form from `configSchema`. Every key has a default, but Qbeast
does no useful work without a catalog and a bucket:

- **Catalog:** `catalogUri` and `catalogWarehouse` name an Iceberg REST catalog. For a
  Harmony Catalog, its cluster-local URL needs no credential (Knox passes the caller's
  identity, Ranger authorizes it). Its published URL needs `catalogCredential` (a
  Console access key) and `catalogOAuthServerUri`.
- **Tables' bucket:** bind a bucket to the instance's `warehouse` purpose on the
  Console's Storage tab (AWC storage, through ABS), or set `warehouseBucket`,
  `storageRegion` and `storageAuthType` (`chain` with `irsaRoleArn`, or `static`).
- **Sizing:** Qbeast backend 1-3 executors of 2 vCPU / 24Gi; each MCP session a driver
  and 0-3 executors of 3.25 vCPU / 28Gi. The Blueprint defaults to one control-plane
  node and 5 worker nodes of 8 vCPU / 64Gi (r6a.2xlarge), which index and query
  tables of about 50 GB. Add 2 worker nodes per extra concurrent MCP session.

## Validation

The supplied documentation reports these checks; they have not been independently
verified against a live registry or cluster here:

- `awc-marketplace lint --schema-version 2` on the engine and the Blueprint: clean.
- `publish.sh` dry run: the mirror plan maps the 2 images and 2 charts to exactly the
  destinations of `mirror.yaml`. It then stops on the source tags, as above.
- `mirror.sh` with helm and skopeo stubbed: it runs exactly those 4 copies.
- Engine template rendered with the catalogs as the publish rewrites them: both
  HelmRepositories at `oci://<REGISTRY>/<NAMESPACE>/charts`, charts `use-endpoint`
  1.24.0 and `portal` 1.8.0, images from `<REGISTRY>/<NAMESPACE>/images/`, no
  reference left to `registry.example.invalid`, the portal's license without
  `pullSecretName`.
- The toolkit's reference-file checks (`onboarding/reference_package.py`): one
  Blueprint referencing the Engine, Role/RoleBinding/ClusterRole, the catalog names
  and ids the engine uses, the Capability provided by the engine. Plus `mirror.yaml`
  matching the catalogs. These real Qbeast files remain in this folder and are not
  included in the fictional, shareable sample ZIP.
- The 1.3.x engine runs on Qbeast's AWC demo cluster (Console deploy, portal, MCP
  sessions from Claude).

Not run: a publish or mirror to your registry (waiting on USE 0.10.1), and 1.3.12 on a
cluster (1.3.12 changes only the portal's license prefill).

## Changes from the earlier reference package

- Engine and Blueprint 1.3.12 (from 1.3.11): the portal no longer reads the pull secret
  (see License).
- Real catalogs, mirror plan and scripts in place of the placeholders. File names
  follow `examples/bundles/` (`imagecatalog.yaml`, `chartcatalog.yaml`, `mirror.yaml`).
- `capabilities.yaml`, not `capability.yaml`: `awc-marketplace publish` packs only
  `capabilities.yaml` into the engine artifact, and the Console applies the
  Capabilities it finds there. Under the other name the Capability isn't published,
  and the engine fails admission on a Console that doesn't have it yet. The
  generated Neo4j and StarRocks examples now use the same filename.
- The Capability requires `mcp`, as yours does, and no longer has `sparkConnect`:
  only the portal and the MCP server are meant to be reachable from outside the
  workspace. Engines older than 1.3.12 still validate against it (they provide
  `sparkConnect` as an extra field), and nothing consumes the Capability yet.
- `onboarding/reference_package.py` checks the actual catalog and mirror names.
- No `clusterrequirements.yaml`: the Blueprint's `hardwareTiers` carry the sizing.

## Boundaries

- No Harmony `ref` dependency: even an optional one keeps the engine Pending until
  `harmony-catalog-plugin` runs on the same cluster, and the Console can't offer an
  existing catalog instance to a partner Blueprint yet. The `catalog*` settings name
  the catalog instead.
- Ranger policies granting Qbeast access to a Harmony Catalog are set up by an admin;
  the engine doesn't provision them.
- `storageAuthType: static` keeps the key pair in the EngineInstance config, an
  ordinary Kubernetes object. Prefer AWC storage or `chain` with `irsaRoleArn`.
- Spark executors scale dynamically; nodes don't (no node autoscaling here).
- `role.yaml` includes a ClusterRole that creates, patches and updates
  CustomResourceDefinitions: use-endpoint installs its ComputeEngineProfile CRD
  (`computeengineprofiles.mcp.qbeast.io`) as the instance's service account. ACE binds
  it; Kyverno limits an engine to CRDs of its own API group.
- Strict RBAC: the Role covers what these chart versions create; the 1.3.x engine
  runs with it on Qbeast's AWC demo cluster. Check it again for other chart versions
  or another aggregation policy.
- With `mcpKnoxOAuth` (default `true`), the namespace's AuthConfig lets
  `/.well-known/*`, `/register` and `/token` through without a Knox token, so MCP
  clients can sign in with the MCP OAuth flow. These match on path only, for every
  host in the namespace. They hand out nothing without a code from `/authorize`, which
  stays behind Knox SSO. `false` accepts pasted Knox tokens only.
- Never put real credentials in this bundle, an `*.input.yaml` or a commit: registry
  passwords and license keys stay in files outside it, catalog and S3 secrets in the
  instance's settings.
