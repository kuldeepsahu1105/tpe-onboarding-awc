# Partner guide: SecureToken STMS on Anywhere Cloud

This is for Bluemetrix engineers. The short path is [GETTING_STARTED.md](GETTING_STARTED.md). This file explains the repository and the publish steps in more detail.

Words used here:

- **Anywhere Cloud (AWC)** is Cloudera's Kubernetes product.
- An **engine** is the deployable definition of one service (template, dependencies, form).
- A **blueprint** is the install guide the marketplace shows. It does not start pods.
- An **engine instance** is the object that actually deploys.

Those three roles are the "Installation Flow" section of the repo [README](../README.md).

## 1. What this directory is

`bluemetrix-stms/` is the Anywhere Cloud shape for **SecureToken STMS**, the management half of Bluemetrix SecureToken (tokenization as a service).

**Required in the blueprint**

- `stms` / `bluemetrix-stms-engine` — STMS itself. No Helm chart is attached yet.
- `ranger` / `udf-plugin` `1.7.0` — centralized Ranger policies. The engine is Unified Data Fabric. It includes Ranger Admin. It does **not** include Ranger KMS.
- `cde` / `cde-engine` `1.6.0` — Cloudera Data Engineering. Spark executor and driver pods get the SecureToken agent as a sidecar through a **pod template**. Traffic to the agent is loopback `127.0.0.1` only. Do not use an admission webhook.

**Required product shape, not a blueprint instance**

- **Trino.** Worker pods need the same agent sidecar, plus SecureToken functions. Without the sidecar, Trino can only mask. This repo no longer contains the Trino engine. [trino-lakehouse/README.md](../trino-lakehouse/README.md) and [trino-core/README.md](../trino-core/README.md) say the YAML lives in CLE/trino-operator. The lakehouse tree is the one to wire. Do not invent an engine name.

**Optional (commented in [blueprint.yaml](blueprint.yaml))**

A live blueprint instance is deployed. This repo does not have a working "optional instance" flag. [caii/blueprint.yaml](../caii/blueprint.yaml) only shows `optional: true` inside a comment, disabled because of a platform bug. So HMS, Polaris, Ozone, and the CAI engines are comments, not instances.

- Polaris (`polaris-plugin` `2.0.0`) — preferred catalog.
- Hive Metastore (`hive-metastore-plugin` `1.6.0`) — optional other catalog. Not a Hive server. Anywhere Cloud has no Hive server.
- Ozone (`ozone-engine` `1.6.0`) — in-cluster object storage. External S3 is a form instead, not a fake engine.
- CAI family, only for a later Data Discovery MCP path: `caiw` (Workbench; there is no engine named `cai`), `caii` (Inference; there is no `cai-i`), `cair` (Registry; there is no `cai-r`).

**External only (form fields, never engines)**

- LDAP or Active Directory URL, bind DN, search bases, bind-password secret.
- Ranger Admin URL, only when you are not using the UDF instance.
- Ranger KMS URL, Kerberos realm, KDC host, principal, and keytab secret. **Only** when `useExternalRangerKms` is true. Ranger KMS is not in Anywhere Cloud and is not in UDF. No KDC engine is bundled. The Kerberos ticket sidecar is not deployed unless that flag is set.
- External S3 bucket, region, endpoint, prefix, and credential secret. Or in-cluster Ozone. Neither is required.
- External PostgreSQL, if you do not use bundled CloudNativePG.

Cloud KMS is not a field. Data Discovery is a later Helm chart (about 8–10 pods), not this blueprint.

**Day-1 sign-in** is a local STMS user (`authMode: local`). Platform SSO (Knox, SAML, Keycloak, Okta) exists on Anywhere Cloud but is not wired into partner engines yet.

**PostgreSQL.** Other blueprints do not list `postgres-plugin`. Polaris and UDF declare it as an auto dependency and the operator creates it. Bundled STMS should do the same (`postgres-plugin` `18.0.0`) once the chart exists. Until then the engine does not declare the auto dependency, so a half-built engine cannot create a database. External host, database, user, and password secret are on the form.

**CDE and Ozone.** [cde/engine.yaml](../cde/engine.yaml) declares `ozone-engine` as a ref dependency. STMS audit does not require Ozone. If you deploy this repo's CDE engine, that CDE engine still needs an Ozone instance. Uncomment `ozone` in the blueprint or reuse one that is already on the cluster.

**CDP base connector.** A second path, later, is engine `cdp-base-connector-plugin` (see [cde-cdp-base-connected/blueprint.yaml](../cde-cdp-base-connected/blueprint.yaml) and [demo-cdp-base-connector/blueprint.yaml](../demo-cdp-base-connector/blueprint.yaml)). It is not an instance here.

Hardware is one blueprint with several node groups, the same idea as [cde-and-polaris/blueprint.yaml](../cde-and-polaris/blueprint.yaml) and [clo/blueprint.yaml](../clo/blueprint.yaml): STMS nodes, UDF nodes, CDE nodes, and an optional CDE GPU group. Optional products are not given node groups until you uncomment them. Copy sizes from their own blueprints when you do.

There is no NIST or FIPS claim in this folder. Certification was left as a follow-up.

## 2. How to read the current code

Worked partner example: [neo4j/](../neo4j/). It has a real chart and real images.

| Neo4j file | Role | STMS today |
| --- | --- | --- |
| `engine.yaml` | Engine definition and `configSchema` (the form) | [engine.yaml](engine.yaml) has the form only. No template, no catalogs. |
| `blueprint.yaml` | Marketplace guide: instances, hardware, display name | [blueprint.yaml](blueprint.yaml) |
| `imagecatalog.yaml` | Image names and tags | Not created. Add it when images exist. |
| `chartcatalog.yaml` | Helm chart name and version | Not created. |
| `capabilities.yaml` | What the engine provides to other engines | Not created. |
| `role.yaml` | RBAC for the ACE operator | Not created. |
| `examples/instance.yaml` | Sample engine instance | Not created. |
| `mirror.sh`, `publish.sh`, `mirror.yaml`, `oci-register.config.example.yaml` | Copy artifacts, publish, register the registry | Drafts. They refuse while the chart and image lists are placeholders. No catalogs yet. |

[starrocks/plugin.yaml](../starrocks/plugin.yaml) is an older `kind: Plugin` (`apiVersion: awc.cloudera.com/v1alpha3`). It is not the marketplace layout. Follow Neo4j.

The repo README says a blueprint combines engine versions (`versionMatrix`) and a user-facing schema. No blueprint file on disk has `versionMatrix` or a config schema. Versions are `minimumVersion` on each instance. The form is the engine `configSchema`.

**Where the form lives.** [engine.yaml](engine.yaml) `spec.configSchema`. Secret fields follow [awc-workspaces/engine.yaml](../awc-workspaces/engine.yaml): a string for the Secret name (default empty) and a string for the key. TLS issuer fields follow [prometheus-adapter/engine.yaml](../prometheus-adapter/engine.yaml): issuer name and kind, or a secret you already created. This repo's schema has no "if" gate. The field `description` says when the field applies. Booleans and enums are the switches: `authMode`, `useExternalRangerAdmin`, `useExternalRangerKms`, `postgresMode`, `objectStorage`.

**Conditional groups**

- `authMode: local` — local admin username and `localAdminPasswordSecret`.
- `authMode: ldap` — LDAP URL, bind DN, search bases, `ldapBindPasswordSecret`.
- `useExternalRangerAdmin: false` — use the UDF instance. Leave the Ranger Admin URL and password secret empty.
- `useExternalRangerAdmin: true` — `rangerAdminUrl`, `rangerAdminUsername`, `rangerAdminPasswordSecret`.
- `useExternalRangerKms: false` — leave every KMS and KDC field empty. Do not deploy a ticket sidecar.
- `useExternalRangerKms: true` — `rangerKmsUrl`, `kdcRealm`, `kdcHost`, `kerberosPrincipal`, `kerberosKeytabSecret`. `rangerKmsCredentialSecret` only if the KMS needs a second credential.
- `tlsCertIssuerName` set — cert-manager issues the STMS server cert and the agent client cert. Kind is `tlsCertIssuerKind`.
- `tlsCertIssuerName` empty — set `stmsServerTlsSecretName`, `agentClientTlsSecretName`, and `trustBundleSecretName`.
- `postgresMode: bundled` — operator-generated secret. Leave the password secret empty.
- `postgresMode: external` — host, port, database, username, `postgresPasswordSecret`. `postgresTlsSecretName` optional.
- `objectStorage: unconfigured` — no bucket fields.
- `objectStorage: external-s3` — endpoint, bucket, region, optional prefix, `s3CredentialsSecret`.
- `objectStorage: ozone` — do not set S3 keys. Use an Ozone engine.
- `s3SseKmsKeyId` — optional, not a secret, only for SSE-KMS on an external bucket.

The full table of secret keys is in [README.md](README.md).

## 3. Publishing and uploading

Read [engine-onboarding/PARTNER_PIPELINE.md](../../engine-onboarding/PARTNER_PIPELINE.md) and [engine-onboarding/README.md](../../engine-onboarding/README.md). The Makefile targets are in the repo root [Makefile](../Makefile).

Draft scripts are in this folder: [mirror.sh](mirror.sh), [publish.sh](publish.sh), [mirror.yaml](mirror.yaml), and [oci-register.config.example.yaml](oci-register.config.example.yaml). They follow Neo4j's shape. They are not for a real push. The chart list and both image lines in `mirror.yaml` are empty comments. `REGISTRY`, `NAMESPACE`, and `VERSION` default to empty. No image catalog or chart catalog is in this folder, so the scripts refuse before `helm`, `skopeo`, or `awc-marketplace` run.

The Makefile targets call [engine-onboarding/scripts/mirror_engine.sh](../../engine-onboarding/scripts/mirror_engine.sh) and [engine-onboarding/scripts/publish_engine.sh](../../engine-onboarding/scripts/publish_engine.sh), which exec `mirror.sh` and `publish.sh` in this directory.

```bash
make mirror-engine DIR=bluemetrix-stms
make publish-engine DIR=bluemetrix-stms
```

Both exit non-zero today. That is the safe dry run: nothing is copied and nothing is published. `make publish-engine` without `PUSH` does not pass `--push`.

When `mirror.yaml` lists a real chart, the STMS image, and the agent sidecar image, and `REGISTRY`, `NAMESPACE`, and `VERSION` are set, `publish.sh` matches [neo4j/publish.sh](../neo4j/publish.sh): `awc-marketplace validate` on the directory and the blueprint, then publish with `--skip-images --skip-charts`. Without `--push` it prints `Dry run complete`. Do not copy Neo4j's sample registry host.

[PARTNER_PIPELINE.md](../../engine-onboarding/PARTNER_PIPELINE.md) says to keep the dry run until `PUSH=1`. The shared wrapper refuses `--push` unless `APPROVE_PUBLISH=1`. This draft also refuses `--push` while the chart or image list is still a placeholder, even if those flags are set.

```bash
make publish-engine DIR=bluemetrix-stms PUSH=1 APPROVE_PUBLISH=1
```

`mirror.sh` needs `helm`, `skopeo`, and a registry login only after the lists are real.

**What Bluemetrix must supply**

- An OCI registry, and the credentials to push to it and to pull from the cluster.
- The STMS Helm chart and the real image tags, once the chart has left Kustomize.
- The agent image that CDE and Trino sidecars will run.
- Kubernetes Secrets (name + keys) for passwords, keytabs, and certificates. Not the secret values in git.

**What is not ready**

- STMS is still Kustomize, with Helm in progress. No dedicated operator.
- No image catalog and no chart catalog in this folder. The draft scripts do not need them in order to refuse.
- `mirror.sh` and `publish.sh` are drafts. They exit non-zero until `mirror.yaml` has a real chart and the STMS and agent sidecar images.
- Do not run scaffold just to invent catalogs. `make scaffold-engine` writes image and chart entries from the form. A form without a real chart would invent them.
- Do not publish fake images. The draft refuses that push.

Third-party CI, when you are ready to merge a real engine, is [docs/thirdparty-engine-publishing.md](../docs/thirdparty-engine-publishing.md). A top-level folder is third-party when it contains `CODEOWNERS`. This folder does not have one yet. Add it when there is something to publish. Do not add a `VERSION` file until the version is real.

## 4. Integrating to the marketplace

The onboarding docs describe this as: mirror, publish, then register the registry (`MARKETPLACE_REGISTRIES` via `awc-oci-register`). Step 8 in [PARTNER_PIPELINE.md](../../engine-onboarding/PARTNER_PIPELINE.md) is "Console → Marketplace → Deploy". They do not describe click-by-click screens.

Registration command:

```bash
make register-partner-registry CONFIG=<path-to-your-filled-oci-register.config.yaml>
```

That runs [engine-onboarding/scripts/register_partner_registry.sh](../../engine-onboarding/scripts/register_partner_registry.sh), which runs `awc-oci-register verify` and `awc-oci-register apply` on the **control plane** cluster. Start from [oci-register.config.example.yaml](oci-register.config.example.yaml). Replace `<your-registry>`, `<your-namespace>`, `<registry-username>`, and `<path-to-registry-password-file>`. The password file must not be committed. Do not point this command at the example until those placeholders are gone. The comment matches Neo4j: this registers pull credentials and `MARKETPLACE_REGISTRIES` until CCF-95. The repo does not describe a Cloudera Cloud Factory UI. Use the script.

After publish and registry registration, the marketplace can list the blueprint. The blueprint's `ui.displayName` is the name. `minimumVersion` on each instance is the version floor. The customer then fills the engine form (Ranger URL, LDAP, KDC fields only if external Ranger KMS is on, S3 bucket, region, endpoint, and secret **names** for credentials and certs) and picks the hardware tier. Deploy creates engine instances. The blueprint alone does not.

After a real `--push`, [publish.sh](publish.sh) says the partner catalog sync takes about 60 seconds. That sentence matches [neo4j/publish.sh](../neo4j/publish.sh). The draft does not reach it while the chart list is empty.

## 5. Further development

Do these in order.

1. Finish the STMS Helm chart (the move from Kustomize). Data Discovery stays a later chart.
2. Map chart values onto the fields and secret refs already in [engine.yaml](engine.yaml). Do not add password literals.
3. Add `imagecatalog.yaml` and `chartcatalog.yaml` with the real tags. Use [neo4j/imagecatalog.yaml](../neo4j/imagecatalog.yaml) and [neo4j/chartcatalog.yaml](../neo4j/chartcatalog.yaml) as the shape. Discover images with `make discover-images REPO_URL=<helm-repo-url> CHART=<chart> VERSION=<version>` only after the chart is real.
4. Add the engine `template` and `releases` that render that chart. Declare `postgres-plugin` `18.0.0` as `type: auto` when the chart can read the generated secret. Set `minimumVersion` on the `stms` instance to that chart version and drop `0.0.0`.
5. Put the agent image in the image catalog. Wire it into the CDE pod template (Spark driver and executor). Wire the same image into Trino worker pods when the lakehouse engine is referenced from this repo. Loopback only. No admission webhook.
6. Test Ranger policy creation against UDF's Ranger OpenAPI (`udf-plugin`). Keep external Ranger Admin as the form flag.
7. Keep Ranger KMS and KDC as external inputs. Do not add those engines.
8. Leave Polaris preferred and HMS optional. Leave Ozone optional versus external S3.
9. Leave `caiw`, `caii`, and `cair` commented until Data Discovery's MCP server is a real chart. Do not add engines named `cai`, `cai-r`, or `cai-i`.
10. Keep local authentication as the day-1 identity until platform SSO is wired into partner engines.
11. Fill [mirror.yaml](mirror.yaml) with the real chart, STMS image, and agent sidecar image. Set `REGISTRY`, `NAMESPACE`, and `VERSION`. Dry-run `make publish-engine DIR=bluemetrix-stms`. Get a review. Then `PUSH=1 APPROVE_PUBLISH=1`. The draft scripts are already here; they refuse until that list is real.
12. Register the registry with `make register-partner-registry`.

Do not claim NIST certification. Do not add Cloud KMS fields until there is a real integration. Do not bundle a KDC.
