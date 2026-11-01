# PuppyGraph: reference bundle from Nijjwol23/awc-partner-engine-agents

Hand-tuned "golden" PuppyGraph bundle, copied unchanged from
`golden/puppygraph/` (plus `partners/puppygraph/partner.yaml` and the
`examples/instance.yaml` from `puppygraph-ace-engine`). Use it as the target
quality when checking toolkit output.

Compare with the toolkit-generated version in `../../bundles/puppygraph/`
(built from `../../puppygraph.input.yaml`):

| Reference has | Toolkit output |
|---|---|
| `v1alpha10` apiVersion, embedded-registry annotation | `v1alpha9`, no annotation |
| Single shared `storageSize`, plus `priorityIpCidr`, `username`, `password` config | Per-role replicas/cpu/memory/storage; no auth config |
| Hand-written Flux HelmRelease values, AuthConfig, ingress | Generic multi-role template |
| Registry `docker-sandbox.infra.cloudera.com/nijjwol-awc` | Your `publish.destinationRegistry` |

To match it more closely, add those config fields and the HelmRelease values to the
`helm-multi-role` template (or edit the generated `engine.yaml`).
