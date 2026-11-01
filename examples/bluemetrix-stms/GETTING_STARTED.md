# Getting started: SecureToken STMS on Anywhere Cloud

Open this file first. The longer notes are in [PARTNER.md](PARTNER.md). The field list is in [README.md](README.md).

An **engine** is the definition of one service. A **blueprint** is the form and the install guide a customer sees. The **marketplace** is the catalog that lists that blueprint as a tile. A tile does not start the service. Deploying the tile creates an **engine instance**, and that instance starts pods.

## Before you start

**You create**

- A git client, Python 3.9 or newer, Helm, and Docker (or a tool that can push images). The onboarding notes also use `skopeo` when you mirror images. See [engine-onboarding/README.md](../../engine-onboarding/README.md). PyYAML is required for the form tools. `jsonschema` is optional.
- Your own OCI registry: a place that stores your container images and Helm charts. You need permission to push to it.

**Cloudera gives you**

- This `ace-engines` git repository.
- The registry host and namespace to publish into, when they are ready for you.
- A review of the dry-run publish before anything is pushed.

**You do not have yet**

- A finished STMS Helm chart. The product still deploys with Kustomize. Helm is in progress.
- Image names and tags for STMS or the agent sidecar.

Do not invent those. Do not put passwords in git.

## 1. What you are building

You are packing the SecureToken management service (STMS) so a customer can install it on Anywhere Cloud.

- The **engine** is STMS itself, plus the form for URLs and secret names.
- The **blueprint** is the form the customer fills in, and the list of other services that install with it.
- The **marketplace** lists that blueprint as a tile.

Done looks like: you can point at `bluemetrix-stms/blueprint.yaml` and say what the customer will deploy.

## 2. What to install on your machine

Install git, Python 3.9+, Helm, and Docker. Install `skopeo` before you copy images to your registry. That list matches [engine-onboarding/README.md](../../engine-onboarding/README.md) (Python and PyYAML for the form tools; Helm for charts).

Check:

```bash
git --version
python3 --version
helm version
docker version
```

Done looks like: each command prints a version. You can log in to your registry. You do not need the marketplace CLI until step 8.

## 3. Get the repo and open this folder

Clone `ace-engines` the way Cloudera told you to. From the repo root:

```bash
cd bluemetrix-stms
```

| File | One line |
| --- | --- |
| `GETTING_STARTED.md` | This page. |
| `README.md` | Map of required and optional pieces, and the secret table. |
| `PARTNER.md` | Why the files look like this, and how publish works. |
| `blueprint.yaml` | The tile: which services install, and how big the nodes are. |
| `engine.yaml` | The form fields. No chart and no container images yet. |
| `mirror.sh`, `publish.sh` | Draft upload scripts. They refuse a real push until the chart exists. |
| `mirror.yaml` | Empty chart and image lists, with commented placeholders. |
| `oci-register.config.example.yaml` | Draft registry registration. Replace the placeholders. Do not commit a password. |

Done looks like: you see those files. You do not see an image catalog or a chart catalog. That is expected.

## 4. Build on these files

Edit the files in this folder. Do not start from a blank directory. Do not run `make scaffold-engine` yet. That command writes image and chart names from a form. We do not have a real chart, so the scaffold would invent them.

The source of truth is `blueprint.yaml` and `engine.yaml`.

When your Helm chart is ready, add the same kinds of files Neo4j has under [neo4j/](../neo4j/):

| File you will add or edit | What goes in it |
| --- | --- |
| `chartcatalog.yaml` | Your chart name and version. Copy the shape of `neo4j/chartcatalog.yaml`. |
| `imagecatalog.yaml` | Your real image names and tags, including the agent sidecar. Copy the shape of `neo4j/imagecatalog.yaml`. |
| `engine.yaml` | The Helm values template that reads the form fields. Keep the field names that are already there. |
| `blueprint.yaml` | Change the `stms` `minimumVersion` from `0.0.0` to your chart version. |

You can list images from a real chart with:

```bash
make discover-images REPO_URL=<helm-repo-url> CHART=<chart-name> VERSION=<chart-version>
```

That command only looks. It does not publish. Run it from the repo root.

Done looks like: the form fields are unchanged, and any new catalog file uses tags you can pull. `minimumVersion` is no longer `0.0.0`.

## 5. External settings the customer types

Customers type these on the engine form (`engine.yaml`). They paste a URL or a Secret **name**. They never paste a password.

A **Secret** is a Kubernetes object that already holds the password, keytab, or certificate. The form only stores the name of that object and the key inside it.

| Field | When it is required | What they paste |
| --- | --- | --- |
| `authMode` | Always. Use `local` on day one. | The word `local` or `ldap`. |
| `localAdminPasswordSecret` | When `authMode` is `local`. | Secret name. Key `password`. |
| `ldapUrl`, `ldapBindDn`, `ldapUserSearchBase`, `ldapGroupSearchBase` | When `authMode` is `ldap`. | URLs and directory names. |
| `ldapBindPasswordSecret` | When `authMode` is `ldap`. | Secret name. Key `bind-password`. |
| `useExternalRangerAdmin` | Always. Leave `false` to use Unified Data Fabric. | `true` or `false`. |
| `rangerAdminUrl` | When `useExternalRangerAdmin` is `true`. | Ranger Admin URL. |
| `rangerAdminUsername` | When `useExternalRangerAdmin` is `true`. | A username, not a password. |
| `rangerAdminPasswordSecret` | When Ranger Admin is external and you are not using the UDF password. | Secret name. Key `rangerAdmin_password`. |
| `useExternalRangerKms` | Always. Leave `false` unless Ranger KMS is outside the cluster. | `true` or `false`. |
| `rangerKmsUrl`, `kdcRealm`, `kdcHost`, `kerberosPrincipal` | When `useExternalRangerKms` is `true`. | URL, realm, host, principal. |
| `kerberosKeytabSecret` | When `useExternalRangerKms` is `true`. | Secret name. Key `keytab`. |
| `tlsCertIssuerName` | Required unless you bring your own cert secrets. | cert-manager issuer name. |
| `stmsServerTlsSecretName`, `agentClientTlsSecretName`, `trustBundleSecretName` | Required when `tlsCertIssuerName` is empty. | Secret names. Keys `tls.crt`, `tls.key`, and `ca.crt`. |
| `postgresMode` | Always. `bundled` is the normal choice. | `bundled` or `external`. |
| `postgresHost`, `postgresDatabase`, `postgresUsername`, `postgresPasswordSecret` | When `postgresMode` is `external`. | Host, database, user, and a secret name. |
| `objectStorage` | Always. `unconfigured` until you choose storage. | `unconfigured`, `external-s3`, or `ozone`. |
| `s3Endpoint`, `s3Bucket`, `s3Region` | When `objectStorage` is `external-s3`. | Endpoint URL, bucket, region. |
| `s3CredentialsSecret` | When `objectStorage` is `external-s3`. Not used for in-cluster Ozone. | Secret name. Keys `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`. |

KDC fields stay empty when Ranger KMS is off. Ranger KMS is not installed by this blueprint. In-cluster Ozone does not need S3 keys.

Done looks like: every secret field in git is a name, and the real password lives only in the cluster Secret.

## 6. Sidecars

A **sidecar** is an extra container in the same pod as the job. The SecureToken agent is that container. It listens on `127.0.0.1` only.

- **CDE** Spark driver and executor pods get the agent from a **pod template**. A pod template is a snippet that adds containers to the Spark pod. Do not use an admission webhook.
- **Trino** worker pods get the same agent. Trino also needs SecureToken functions. Without the sidecar, Trino can only mask. The Trino engine is not in this repo yet. See [trino-lakehouse/README.md](../trino-lakehouse/README.md).

When the agent image exists, put its name and tag in `imagecatalog.yaml` (the file from step 4). Point the CDE pod template and the Trino worker spec at that catalog entry. There is no image line to fill in today.

Done looks like: you know which file will hold the image name, and you have not typed a fake tag.

## 7. Check the YAML before anyone publishes

`publish.sh` in this folder is a draft. With the chart list still empty it exits non-zero and does not call `awc-marketplace`. That is safe: nothing is uploaded.

Check that the blueprint and engine YAML load:

```bash
python3 -c "import yaml; yaml.safe_load(open('bluemetrix-stms/blueprint.yaml')); yaml.safe_load(open('bluemetrix-stms/engine.yaml')); print('ok')"
```

Run that from the repo root.

The draft publish check is:

```bash
make publish-engine DIR=bluemetrix-stms
```

Today that command refuses, because `mirror.yaml` has no chart or images and `REGISTRY` is empty. After you fill those in, the same command is the dry run. It follows [neo4j/publish.sh](../neo4j/publish.sh): `awc-marketplace validate` on the folder and on the blueprint, and no `--push`.

Done looks like: the YAML check prints `ok`. The draft publish command prints `DRAFT: refusing publish` and does not upload.

## 8. Upload, dry-run, then real publish

`mirror.sh` and `publish.sh` are already in this folder. They are drafts. They copy the shape of [neo4j/mirror.sh](../neo4j/mirror.sh) and [neo4j/publish.sh](../neo4j/publish.sh). They do not contain Neo4j image names. `REGISTRY` and `NAMESPACE` default to empty. Chart and image names live only as comments in [mirror.yaml](mirror.yaml).

From the repo root:

```bash
make mirror-engine DIR=bluemetrix-stms
make publish-engine DIR=bluemetrix-stms
```

Both commands find the scripts and then refuse. Nothing is copied and nothing is published. The dry run is safe.

When the Helm chart and the STMS and agent images exist:

1. Replace the commented lines in `mirror.yaml` with the real chart and the two images.
2. Set your registry (do not reuse a sample host from another engine):

```bash
export REGISTRY=<your-registry>
export NAMESPACE=<your-namespace>
export VERSION=<chart-version>
```

3. Run the dry run again:

```bash
make mirror-engine DIR=bluemetrix-stms
make publish-engine DIR=bluemetrix-stms
```

`make publish-engine` without `PUSH` does not push the marketplace record. [engine-onboarding/PARTNER_PIPELINE.md](../../engine-onboarding/PARTNER_PIPELINE.md) says to stay on the dry run until a reviewer says yes. Do not run the real push until a Cloudera reviewer has seen that dry run.

The real push is:

```bash
make publish-engine DIR=bluemetrix-stms PUSH=1 APPROVE_PUBLISH=1
```

`PUSH=1` asks `publish.sh` to run with `--push`. [engine-onboarding/scripts/publish_engine.sh](../../engine-onboarding/scripts/publish_engine.sh) refuses that unless `APPROVE_PUBLISH=1`. The draft `publish.sh` still refuses `--push` while `mirror.yaml` is a placeholder, even if both flags are set.

`mirror.sh` needs `helm`, `skopeo`, and a registry login (`helm registry login` / `skopeo login`) only after the lists are real. It does not call them while the lists are empty.

Done looks like: today both commands exit non-zero with a DRAFT message and upload nothing. After the lists are real, the dry run prints `Dry run complete`. The push happens only after review.

## 9. Connect the registry to the marketplace

Do this only after a real publish. The draft example is [oci-register.config.example.yaml](oci-register.config.example.yaml). Copy it, replace every `<placeholder>`, and keep the password in `passwordFile` outside git. Do not commit that file. Do not run the example until the placeholders are gone.

```bash
make register-partner-registry CONFIG=<path-to-your-filled-oci-register.config.yaml>
```

The script runs `awc-oci-register verify` and then `apply` on the control plane. Details are in [engine-onboarding/scripts/register_partner_registry.sh](../../engine-onboarding/scripts/register_partner_registry.sh). The example comment matches Neo4j: this registers pull credentials and `MARKETPLACE_REGISTRIES` until CCF-95.

What you will see in the console: after publish and this registration, the marketplace shows a tile for "Bluemetrix SecureToken STMS". Opening it shows the form (external URLs and secret names) and a hardware size. Deploying it creates engine instances. The repo docs do not list the clicks. They call the last step "Console → Marketplace → Deploy" in [PARTNER_PIPELINE.md](../../engine-onboarding/PARTNER_PIPELINE.md). Neo4j's publish script says the catalog sync takes about 60 seconds after a push.

Done looks like: the tile is listed, the form shows the fields from step 5, and a deploy creates an engine instance rather than only a blueprint.

## 10. If something fails

Short list from the troubleshooting section of the repo [README](../README.md).

1. **Engine not installed.** `kubectl get engines`. The blueprint names `bluemetrix-stms-engine`, `udf-plugin`, and `cde-engine`. A missing engine fails the instance. The blueprint can exist with no pods. That is normal until an engine instance exists.
2. **Missing image.** `kubectl describe engine bluemetrix-stms-engine`. `MissingReferences` means the image catalog or chart catalog was not applied.
3. **Missing secret.** The form names a Secret that is not in the instance namespace, or the key inside it is wrong. The password is not in the YAML. Fix the Secret, not the blueprint.
4. **Registry credentials.** Mirror and publish need `helm registry login` or `skopeo login`. Marketplace pulls need the control-plane registration from step 9.
5. **Blueprint applied, nothing running.** `kubectl get engineinstance -A`. Applying `blueprint.yaml` does not start pods. An engine instance does. Then `kubectl describe engineinstance <name> -n <namespace>` and read `Status.Conditions`.

Done looks like: you know which of the five it is before you change the chart.

## 11. Not your job yet

Do not build these for this blueprint:

- Ranger KMS as a service inside Anywhere Cloud. It stays an external URL.
- A Kerberos KDC. It stays an external host, and only if Ranger KMS is external.
- Hive. There is no Hive server. Hive Metastore is optional and already named in the blueprint comments.
- Data Discovery. Later Helm chart. The CAI engines stay commented until that chart exists.
- Cloud KMS. Not a form field.
- An admission webhook for the agent. The plan is a pod template.
- A NIST or FIPS claim. That status is not decided.

Done looks like: the blueprint still has three live instances (`ranger`, `cde`, `stms`) and the optional ones stay comments.
