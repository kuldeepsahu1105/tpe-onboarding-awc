# Bluemetrix SecureToken STMS

Start here if you are new to this folder: [GETTING_STARTED.md](GETTING_STARTED.md).

The longer guide for publishing, the marketplace, and how this repo is put together is [PARTNER.md](PARTNER.md).

This folder is the Anywhere Cloud shape for **SecureToken STMS** (the management service). It is not a running install. A blueprint does not start pods. An engine instance does. See the repo [README](../README.md) section "Installation Flow".

## Files

| File | What it is |
| --- | --- |
| [GETTING_STARTED.md](GETTING_STARTED.md) | Short path from this folder to a marketplace tile. Open this first. |
| [PARTNER.md](PARTNER.md) | How publishing and the engine files work, with the real commands. |
| [blueprint.yaml](blueprint.yaml) | The marketplace install guide: which engines, and how big the nodes are. |
| [engine.yaml](engine.yaml) | The STMS form: URLs and secret names. No chart and no images yet. |
| [mirror.sh](mirror.sh), [publish.sh](publish.sh) | Draft upload scripts. They refuse while the chart and image lists are placeholders. |
| [mirror.yaml](mirror.yaml) | Empty chart and image lists. Commented placeholders only. |
| [oci-register.config.example.yaml](oci-register.config.example.yaml) | Draft control-plane registry file. Do not commit a password file. |

There is no image catalog, chart catalog, role, or example instance. Those come when the Helm chart exists. Copy the layout from [neo4j/](../neo4j/), not from a blank scaffold. `make scaffold-engine` would write catalogs and image tags you do not have.

## Instances

Required (listed in the blueprint):

| Blueprint name | Engine | minimumVersion | Why |
| --- | --- | --- | --- |
| `ranger` | `udf-plugin` | `1.7.0` | Ranger policies. From [udf/blueprint.yaml](../udf/blueprint.yaml). UDF has no Ranger KMS. |
| `cde` | `cde-engine` | `1.6.0` | Spark. Agent sidecar via pod template. From [cde/awc-cde-blueprint.yaml](../cde/awc-cde-blueprint.yaml). |
| `stms` | `bluemetrix-stms-engine` | `0.0.0` | STMS itself. `0.0.0` means no chart version is published yet. |

Optional (commented in the blueprint, because a live `optional: true` on an instance is only a disabled comment in [caii/blueprint.yaml](../caii/blueprint.yaml)):

| Blueprint name | Engine | minimumVersion | Why it is optional |
| --- | --- | --- | --- |
| `polaris` | `polaris-plugin` | `2.0.0` | Preferred catalog. [polaris/blueprint.yaml](../polaris/blueprint.yaml). |
| `hms` | `hive-metastore-plugin` | `1.6.0` | Hive Metastore only. [cde-udf/blueprint.yaml](../cde-udf/blueprint.yaml). |
| `ozone` | `ozone-engine` | `1.6.0` | In-cluster object storage. [ozone/blueprint.yaml](../ozone/blueprint.yaml). |
| `caiw` | `caiw` | `1.6.0` | Cloudera AI Workbench. There is no engine named `cai`. |
| `caii` | `caii` | `2.0.0-b1` | Cloudera AI Inference. There is no engine named `cai-i`. |
| `cair` | `cair` | `2.0.0` | Cloudera AI Registry. There is no engine named `cai-r`. |

Not an instance:

- **Trino.** Required product shape (worker sidecar, loopback only), but [trino-lakehouse/README.md](../trino-lakehouse/README.md) and [trino-core/README.md](../trino-core/README.md) say the engines moved to CLE/trino-operator. Use the lakehouse tree when it is wired. Do not add a guessed engine name.
- **PostgreSQL.** Bundled database is `postgres-plugin` `18.0.0` as an auto dependency, same rule as Polaris. Not listed on the blueprint. External database is a form.
- **Ranger KMS and Kerberos KDC.** Not in Anywhere Cloud and not in UDF. External form fields only.
- **Data Discovery, Cloud KMS, Hive server, admission webhook.** Not in this blueprint.

`cde-engine` itself requires `ozone-engine` ([cde/engine.yaml](../cde/engine.yaml)). STMS audit does not. If you deploy this repo's CDE engine, uncomment `ozone` or point CDE at an Ozone instance that is already on the cluster.

## Two ways to reach systems outside the cluster

1. **URLs and secrets on the STMS form.** LDAP, external Ranger Admin, external Ranger KMS plus KDC, external S3. This is the day-1 path.
2. **An existing CDP cluster.** Engine `cdp-base-connector-plugin` (see [cde-cdp-base-connected/blueprint.yaml](../cde-cdp-base-connected/blueprint.yaml)). Not an instance here. [caii/blueprint.yaml](../caii/blueprint.yaml) leaves that connector commented because of a platform bug.

## Secret inputs

The form is `spec.configSchema` in [engine.yaml](engine.yaml). You type a Secret **name** and a **key**. You never type a password, keytab, or private key. Create the Secret in the instance namespace before deploy.

Image pull secrets are not a field. The platform registry path is `make register-partner-registry` ([neo4j/oci-register.config.example.yaml](../neo4j/oci-register.config.example.yaml)). CAII hardcodes the console pull secret in its template instead of asking the user.

| Input | Secret keys | When | System |
| --- | --- | --- | --- |
| `localAdminPasswordSecret` / `localAdminPasswordSecretKey` (`password`) | password | Required when `authMode` is `local` | STMS local admin |
| `ldapBindPasswordSecret` / `ldapBindPasswordSecretKey` (`bind-password`) | bind password | Required when `authMode` is `ldap` | LDAP or AD |
| `rangerAdminPasswordSecret` / `rangerAdminPasswordSecretKey` (`rangerAdmin_password`) | Ranger Admin password | Required only when `useExternalRangerAdmin` is true and you do not use the UDF credential | External Ranger Admin |
| `kerberosKeytabSecret` / `kerberosKeytabSecretKey` (`keytab`) | keytab bytes | Required when `useExternalRangerKms` is true | External KDC for Ranger KMS |
| `rangerKmsCredentialSecret` / `rangerKmsCredentialSecretKey` (`password`) | extra KMS credential | Optional, only when `useExternalRangerKms` is true and a keytab is not enough | External Ranger KMS |
| `stmsServerTlsSecretName` (`tls.crt`, `tls.key`) | server cert and private key | Required when `tlsCertIssuerName` is empty | STMS nginx |
| `agentClientTlsSecretName` (`tls.crt`, `tls.key`) | client cert and private key | Required when `tlsCertIssuerName` is empty | Agent mTLS |
| `trustBundleSecretName` / `trustBundleSecretKey` (`ca.crt`) | CA bundle | Required when `tlsCertIssuerName` is empty; also when a custom CA verifies Ranger, LDAP, or S3 | Trust |
| `postgresPasswordSecret` / `postgresPasswordSecretKey` (`password`) | database password | Required when `postgresMode` is `external` | External PostgreSQL |
| `postgresTlsSecretName` / `postgresTlsCaKey` (`ca.crt`) | database CA | Optional when `postgresMode` is `external` | External PostgreSQL |
| `s3CredentialsSecret` (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) | access key and secret key | Required when `objectStorage` is `external-s3`. Do not set when `objectStorage` is `ozone` | External S3 |

`tlsCertIssuerName` plus `tlsCertIssuerKind` (`ClusterIssuer` or `Issuer`) is the cert-manager path. It is the same idea as `prometheusScrapeCertIssuerName` on prometheus-adapter. When the issuer is set, do not also paste certificates.

When `postgresMode` is `bundled`, CloudNativePG generates the password secret. Leave `postgresPasswordSecret` empty.

`s3SseKmsKeyId` is optional and is not a secret. It is not Cloud KMS and not Ranger KMS.
