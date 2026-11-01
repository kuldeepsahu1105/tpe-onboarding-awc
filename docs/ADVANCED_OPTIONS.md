# Advanced input options (matching hand-written engines)

Most engines only need the basics in `examples/starter.input.yaml`. These optional keys let the generated
bundle match hand-tuned engines such as Nijj's PuppyGraph and Anshul's StarRocks.
See `examples/puppygraph.input.yaml` and `examples/starrocks.input.yaml` for full uses.

After creating your source with `./awc new my-app` from the repository root, use
`vi my-app.input.yaml` to add these keys, then rerun `./awc build my-app.input.yaml`.
Do not edit generated YAML/scripts. Follow the [input and safety checklists](ONBOARDING_GUIDE.md#edit-source-configuration-before-running)
first; not every advanced option is consumed by every template.

| Key | What it does |
|---|---|
| `engine.apiVersion` | Engine CRD version. Default `v1alpha10`, the version every engine in ace-engines uses. |
| `engine.roleStorage` | `false` removes the per-role storage-size fields. |
| `engine.configFromRoles` | `false` = do not auto-create replica/cpu/memory fields; define them yourself in `config.extras`. |
| `engine.roles[].cpu` / `engine.roles[].memory` / `engine.roles[].resources: false` | Per-role sizing overrides, or drop the resources block for a role. |
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
