# Advanced input options (matching hand-written engines)

Most engines only need the basics in `starter.input.yaml`. These optional keys let the generated
bundle match hand-tuned engines such as Nijj's PuppyGraph and Anshul's StarRocks.
See `examples/puppygraph.input.yaml` and `examples/starrocks.input.yaml` for full uses.

| Key | What it does |
|---|---|
| `engine.apiVersion` | Engine CRD version (default `v1alpha9`; PuppyGraph uses `v1alpha10`). |
| `engine.roleStorage` | `false` removes the per-role storage-size fields. |
| `engine.configFromRoles` | `false` = do not auto-create replica/cpu/memory fields; define them yourself in `config.extras`. |
| `roles[].cpu` / `memory` / `resources: false` | Per-role sizing overrides, or drop the resources block for a role. |
| `config.extras` | Extra user-facing settings: `{name, type, default, description, title?, minimum?, valuesPath?}`. `valuesPath` (e.g. `storage.size`) wires the setting into the Helm values. |
| `helm.values` | Static nested Helm values added to every install. |
| `helm.valuesTemplate` | Full replacement of the generated Helm `values:` block (use `{{ .Config.x }}`, `{{ .Image.id.repository }}`). |
| `helm.pullPolicy` | Image pull policy inside the image block. |
| `service.landingHost` / `landingHostPrefix` / `domainPrefix` | Control the web-UI hostname. |
| `service.landingBackend` | Kubernetes Service the HTTPRoute points at. |
| `service.endpointUrl` | Provide the endpoint capability as a URL instead of host. |
| `provides` | Raw list of `{name, capability, value}` replacing the generated provides. |
| `capability.schema` | Raw JSON-schema replacing the flat `capability.fields` (for nested contracts). |

The web UI shows an example and placeholder for every guided question, and has a Back button.
