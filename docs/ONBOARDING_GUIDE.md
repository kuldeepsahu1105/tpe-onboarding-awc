# Onboarding guide

## Setup
Run the commands below from the repository root unless a command says otherwise.
Python 3.10+ is required. `./awc` creates `.venv/` and installs `requirements.txt`
on the first Python-backed command; `./awc doctor` only reports available tools.

```bash
cd /path/to/tpe-onboarding-awc
./awc doctor
```

## Edit source configuration before running

There is **no `.env` file or dotenv loader** in this toolkit. Engine configuration
is YAML: create an operator-owned input file from the shipped starter, then edit it.
Do not run `new` over an existing input: it copies over the file.

```bash
./awc new my-app
vi my-app.input.yaml
```

In `vi`, press `i` to insert/edit, then `Esc` and `:wq` followed by Enter to save
and quit. Use `Esc`, `:q!`, Enter to discard unsaved edits. Preserve YAML indentation
with spaces, use real booleans (`true`/`false`), and quote versions and size strings.
The checklists below use dotted paths: `publish.destinationRegistry` means the
`destinationRegistry:` key inside `publish:`, not a literal dotted YAML key.

### Engine input checklist

**Required** below means needed by the file workflow without a default.
**Review/defaulted** means the implementation can supply a value, but you must
verify it fits the actual application; successful generation is not deployment approval.

| Check | Actual input keys | Requirement / action before generation |
|---|---|---|
| Identity | `partner.id`, `partner.owner`, `engine.displayName`, `engine.description` | `partner.id` and `engine.description` are required. Use a unique lowercase hyphenated ID. Owner defaults from the ID; display name defaults from owner. Replace starter identity text even though it is accepted as input. |
| Deployment model | `engine.template` | Review/defaulted to `helm-simple`; choose `helm-simple`, `helm-multi-role`, `helm-operator`, or `native-k8s`. |
| Version and names | `engine.version`, `engine.name`, `engine.apiVersion` | Optional overrides: version defaults to `helm.version` (otherwise `1.0.0`), name to `<partner-id>-ace-engine`, API version to `v1alpha10`. |
| Helm chart | `helm.repoUrl`, `helm.chart`, `helm.version` | For **all `helm-*` templates**, repo URL and version are required; chart defaults to `partner.id`. Verify all three against the chart you actually ship. No chart coordinates are required for `native-k8s`. |
| Images | `images[]` as pinned strings or `{id, ref}`; alternatively `{id, source, repository, tag}` | Operationally required: list **every** image, including sidecars/operator images. The code can synthesize a primary image, but that is not discovery. `id` must match any `.Image.<id>` references in custom values. Use exact tags; digest-only references are not preserved by the parser. |
| Primary image fallback | `helm.imageRepository`, `helm.imageTag`, `helm.imageId` | Optional, including for `native-k8s`: the first `images[]` entry supplies the primary repository/ID when not overridden. Review explicit overrides so the template references the correct catalog image. |
| Network/UI | `service.port`, `service.hasLandingPage`, `service.landingPort` | Review/defaulted to `8080`, `true`, and the primary port. Set the actual service port; review `landingPort` when a web UI is enabled. Set `hasLandingPage: false` for an engine without a web UI. |
| Marketplace tile | `blueprint.needed`, `blueprint.outcome`, `blueprint.name`, `blueprint.instanceName` | `needed` defaults to `true`; then `outcome` is required by file loading. Names default to `partner.id`. Set `needed: false` only for a hidden/internal engine; the multi-engine composer suppresses per-engine Blueprints itself. |
| Publish destination | `publish.destinationRegistry`, `publish.namespace` | Review/defaulted: registry is **only a placeholder** (`<your-oci-registry.example.com>`), namespace defaults to `partner.id`. Supply the approved OCI registry hostname (not credentials or `oci://`) and repository namespace/path. |
| Mirroring | `mirror.skip`, `mirror.chart.repoUrl`, `mirror.chart.name`, `mirror.chart.version` | Helm mirroring defaults on; optional chart overrides default from `helm.*`. Skip only when all required charts/images already exist at the exact catalog destinations. Native images also need a real destination and copying when not already present. |
| Cluster sizing | `cluster.kubernetesVersion`, `cluster.workerCountDefault`, `cluster.workerCountMinimum`, `cluster.minCpu`, `cluster.minMemory`, `cluster.recommendedCpu`, `cluster.recommendedMemory`, `cluster.diskDefault`, `cluster.diskMinimum`, `cluster.hasGPU` | Review/defaulted: `>= 1.28.0`, 1/1 nodes, `4` CPU / `16Gi` minimum, normally `8` CPU / `32Gi` recommended, `100Gi`/`50Gi` disks, no GPU. File defaults derive recommended CPU from minimum CPU. Match real requirements; multi-role baseline is 8 CPU / 32Gi minimum. |

### Conditional and advanced input checklist

| When | Actual input keys to verify/update |
|---|---|
| `helm-multi-role` | `engine.roles[]` entries with `name`, `replicas`, and optional `cpu`, `memory`, `resources`. Replace the fallback coordinator/worker roles with your chart's real roles. The top-level `roles` key is not used. |
| `helm-operator` | Required `operator.chartRepoUrl`, `operator.chartName`, `operator.chartVersion`, `operator.group`, `operator.kind`, and `operator.resource`. Review `operator.namespace` (default `ace-operators`, must already exist). The CR and Role are rendered only from those values. |
| `capability.exportsStructuredData: true` | Review `capability.name` (default `<partner-id>-connection`) and `capability.fields` (`name:type` list, default host/port). For a nested contract, use `capability.schema` and `capability.fields: []`. Verify produced connection values; arbitrary field names do not implement their semantics automatically. |
| `dependencies.hasAny: true` | Supply `dependencies.entries[]`: `name`, `engine`, `type` (`auto`, `optional`, `ref`), and `instance` for non-auto links where the default target name is wrong. Do not rely on the fallback entry with an empty engine. `auto` is private and omitted from Blueprint wiring. |
| Chart needs custom values | `helm.values` for static nested values; `config.extras[]` with `name`, `type`, `default`, `description`, optional `title`, `minimum`, `valuesPath`; or `helm.valuesTemplate` for a full values-block replacement. Match real chart value paths. See [advanced options](ADVANCED_OPTIONS.md). |
| Custom multi-role settings | Review `engine.configFromRoles`, `engine.roleStorage`, and `config.extras[]`; disabling auto-config means you must define the fields used by your values template. |
| Custom routing/exports | Review `service.landingHost`, `service.landingHostPrefix`, `service.domainPrefix`, `service.landingBackend`, `service.endpointHost`, `service.endpointUrl`, and `provides[]` when defaults do not match actual Services/contracts. Support varies by template; inspect rendered output without editing it. |

### Placeholders, credentials, and source vs generated files

Replace `my-app`, `My Company`, example chart/image locations and **all** example
registry hosts (including `registry.example.com` and
`registry.partner-corp.example.com`) in your input. Ordinary example domains may
not trigger a warning. Do not use `:latest` or the forbidden
`docker-private.infra.cloudera.com` registry.

Never put passwords, tokens, private keys, or kubeconfig contents in input files,
Helm values, command arguments, UI/MCP conversations, or generated bundles.
`config.extras[].default` is copied to the generated instance example; it is not
a secret store. Use approved external credential stores/login prompts and
chart-supported references to existing Kubernetes Secrets. Authenticate separately
to source/destination registries with your organization's Helm/skopeo credential
procedure; do not add invented `*_PASSWORD` keys to YAML.

Edit **your `*.input.yaml` sources**, not `output/`, pre-rendered
`examples/bundles/`, `manifest.json`, session JSON, or downloaded generated ZIP
contents. Never hand-edit generated `engine.yaml`, catalogs, `mirror.yaml`,
scripts, or `examples/instance.yaml`: fix the input and regenerate. CLI session
JSON is runtime state, not an operator config file.

**Template limitation:** `helm-operator` writes the custom resource and its Role
rule from `operator.group`, `operator.kind`, and `operator.resource`. Generation
does not fill those in, and it does not leave angle-bracket tokens. Supply the
real CRD before generating. `native-k8s` renders a fixed Deployment/PVC/Service
scaffold, not an import of arbitrary Kubernetes YAML; app-specific changes not
expressible in inputs require a reviewed source-template change via
`vi templates/native-k8s/engine.yaml.j2`. Template changes affect every app using
that class and are not routine environment edits.

## 1. Single-engine app (Neo4j, PuppyGraph, StarRocks, ...)
After `vi my-app.input.yaml` and the checklists above:
```bash
./awc build my-app.input.yaml
```
The wrapper writes `output/my-app/` (based on the input **filename**).
Alternatively copy `examples/neo4j.input.yaml` to `my-app.input.yaml` before
editing; do not edit the shipped example as your environment config.

`./awc wizard` collects answers only; it does **not** generate a bundle. For a
named wizard session, with the toolkit virtualenv already installed:
```bash
.venv/bin/python -m onboarding.cli wizard --session my-engine
.venv/bin/python -m onboarding.cli generate --session my-engine
.venv/bin/python -m onboarding.cli validate --session my-engine
```
The Python CLI's default output is `output/<partner-id>/ace/`, unlike the wrapper.
The guided question graph does not collect `images[]`, `engine.roles[]`, or all
advanced options. For these, maintain `my-app.input.yaml` and use the file
workflow (or load the complete YAML into a named session before generation).

## 2. Multi-engine app or combining with existing experiences
DataSpark and Phoenix AI are each one engine: `examples/dataspark.input.yaml` and `examples/phoenixai.input.yaml`. Phoenix AI lists CAI, CDE, and CDF under `dependencies.entries` in that same file. A Blueprint that installs several of your own engines is a separate `blueprint.input.yaml` you write, with one `engines[].input` path per engine file. Keep those paths relative to the blueprint file.
```bash
vi my-suite/blueprint.input.yaml
./awc blueprint my-suite/blueprint.input.yaml
```
Run `mkdir` only for a new directory; do not copy over existing local inputs.
Apply the engine checklists to **each** engine file before composition.

| Composer input checklist | Requirement / action |
|---|---|
| `blueprint.name`, `blueprint.owner`, `blueprint.displayName` | Required; set the app's real identity. Output goes to `output/<blueprint.name>/`. |
| `blueprint.description`, `blueprint.outcome`, `blueprint.version`, `blueprint.kubernetesVersion` | Optional; description is derived from display name, outcome is omitted when absent, version defaults to `1.0.0`, Kubernetes constraint to `>= 1.28.0`. Pin intended versions explicitly. |
| `engines[]` | Required nonempty list. Each entry should specify either `input` or `existing`, not both. |
| `engines[].input` | Path to an engine source file, relative to the composer file's directory (e.g. `db.input.yaml`). |
| `engines[].existing.engine`, `engines[].existing.instance`, `engines[].existing.version` | Engine/instance required for an existing entry; version defaults to the Blueprint version. Verify the actual target-cluster engine name, instance name and version; CAI/CDE/CDF example identifiers are not discovery. |
| Included engine `blueprint.instanceName`, `blueprint.nodeGroupId`, `engine.name`, `partner.id` | Keep identifiers unique across included components and verify non-auto `dependencies.entries[].instance` targets. |
| Included engine `publish.destinationRegistry`, `publish.namespace` | Verify each engine's mirror target. The combined publish script takes its default registry/namespace from the **first included input engine**; use consistent destinations across the suite. For existing-only composition, its defaults are `<registry>`/`<namespace>` and must be supplied at invocation. |

- `input:` includes and generates one of your engines (its own Blueprint is suppressed).
- `existing:` pulls in an engine already on the cluster (`engine`, `instance`, `version`).
- Declare links in an engine's `dependencies.entries` (`auto` / `optional` / `ref`).

Examples: `examples/dataspark.input.yaml` (one native app; API, auth, and database images), `examples/phoenixai.input.yaml` (one Helm app that depends on CAI, CDE, and CDF).

## 3. Web UI (no AI needed)
```bash
./awc ui                    # then open http://127.0.0.1:8765
```
Three tabs: guided questions (with dependency form), paste `input.yaml`, and the
multi-engine Blueprint composer. Results show validation, each generated file, and a .zip download.
The CLI above and this UI are fully standalone; AI is optional.
Use the same key checklists for form answers and pasted YAML. Keep repeatable
YAML in your own input files (`vi my-app.input.yaml`); edit and re-paste rather
than modifying ZIP outputs. Use the paste-YAML tab for fields not collected by
the guided questions, such as a complete `images[]` list or `engine.roles[]`.
In the composer UI, supplied engine filenames must
match the `engines[].input` references.

## 4. With an AI agent (MCP, optional)
```bash
./awc mcp
```
Tools: `start_session`, `get_next_question`, `answer_question`, `add_dependency`,
`load_answers`, `generate_bundle`, `validate_bundle`, `onboard_engine`,
`compose_blueprint`, `list_examples`, `get_example`, docs tools.
MCP passes the same answers/Blueprint inputs; it does not require an environment
file. For client connection setup, see [USAGE.md](USAGE.md#method-3--ai-assistant-via-mcp-optional).

## Charts, images, mirroring and publishing
Declare every image the app needs under `images:` (strings like
`docker.io/starrocks/fe-ubuntu:3.4.3` or `{id, ref}`). Don't know them? Discover them:

```bash
.venv/bin/python -m onboarding.cli discover-images --repo-url https://helm.neo4j.com/neo4j \
  --chart neo4j --version 5.26.0 --set neo4j.name=neo4j --set volumes.data.mode=defaultStorageClass
# add --write input.yaml to store the result
```

Generated bundle (besides the ACE YAML):

| File | Purpose | Needs |
|---|---|---|
| `mirror.yaml` | Plan: charts and images, source -> destination | - |
| `mirror.sh` | `helm pull/push` charts and `skopeo copy --all` images into your registry | helm, skopeo, registry logins |
| `publish.sh` | `awc-marketplace validate` + `publish` engine + Blueprint (+ `catalog fetch`). Dry run by default; `--push` pushes | awc-marketplace CLI |

Also generated: `examples/instance.yaml` (ready-to-apply EngineInstance with config defaults)
and `examples/smoke-test.sh` (kubectl + port-forward probe). Ready-made, pre-rendered bundles
for Neo4j, StarRocks (FE/BE) and PuppyGraph (controlplane/leader/compute) are in
`examples/bundles/<name>/`; their sources are `examples/<name>.input.yaml`.

After offline checks and explicit authorization for registry operations, flow:
`mirror.sh` -> `publish.sh` (dry run) -> `publish.sh --push`. For a composed
multi-engine Blueprint, `publish.sh` publishes each engine then the one Blueprint;
run each `engines/<id>/mirror.sh` first. Set `mirror: {skip: true}` if artifacts are
already in your registry.

`publish.sh` supports invocation-time environment overrides: `AWC_MARKETPLACE`
(executable path), `REGISTRY`, `NAMESPACE`, and `SCHEMA_VERSION` (default `1`).
These are shell variables, **not an env file**. Review all four before invoking
the script; normal registry/namespace defaults come from your input. Overriding
`REGISTRY`/`NAMESPACE` changes publishing only, not catalog or mirror targets:
change the source and regenerate for a permanent target change. The script
still invokes `awc-marketplace validate` and `publish` without `--push` in its
default mode; it is not just an offline command printer.

Not covered: building images from source or writing Dockerfiles, and the
reference repos' staged pipeline (approval gates, smoke tests, JSON reports).

## Safe validation sequence before mirroring or publishing

1. `./awc doctor` reports dependencies without provisioning or contacting a cluster.
   `./awc build` needs Python packages; first-run dependency installation requires
   package-index access. Helm/skopeo/marketplace/kubectl are not needed for static validation.
2. Edit and review the source checklist, then run `./awc build my-app.input.yaml`.
   This only generates files and runs offline static validation; it also saves
   session state. It does not mirror, publish or deploy. Use a fresh output
   directory after changing template class or removing features: generation
   overwrites emitted files but does not remove stale ones. For example:
   `./awc build my-app.input.yaml output/my-app-review-2`.
3. Fix source errors and regenerate until `"ok": true`; review **every warning**.
   Placeholder registries, `:latest`, low sizing, and unparsed Go-template control
   flow may be warnings, not failures. Example domains, credentials and deployment
   correctness are not comprehensively checked. Never treat `"ok": true` as a
   guarantee of a complete operator scaffold or cluster compatibility.
4. For a named file-backed session, reload before regenerating:
   `.venv/bin/python -m onboarding.cli answers --session my-app --file my-app.input.yaml`,
   then `generate --session my-app --out output/my-app-review` and
   `validate --session my-app --out output/my-app-review` using the same Python
   CLI prefix. `validate` alone checks the existing output/session, not new edits
   to the YAML file. For a suite, rerun `./awc blueprint my-suite/blueprint.input.yaml`
   and inspect every engine's validation report; composition does not verify
   existing engines against a cluster or fully validate the composed Blueprint.
5. Inspect generated files read-only.
   `bash -n output/my-app/mirror.sh && bash -n output/my-app/publish.sh`
   checks both scripts' shell syntax without executing anything; omit the mirror
   check when `mirror.sh` is absent.
   Use the actual output directory (and per-engine paths for a suite).

Optional image discovery (`./awc images ...` or `discover-images`) invokes
`helm template`, may download upstream charts, and may need chart-specific
`--values`/`--set` arguments. `--write my-app.input.yaml` modifies your source's
`images` list; review it again with `vi my-app.input.yaml`. It is not required
for an offline build when you already have verified image references.

**Stop here for documentation/offline review.** `mirror.sh` copies artifacts;
`publish.sh` uses an external marketplace CLI even without `--push`;
`publish.sh --push` publishes; `kubectl apply` deploys; and smoke-test scripts
contact a cluster and open a port-forward. None are local static checks.
