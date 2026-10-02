# AWC Onboarding Toolkit

Turn **any app** (Neo4j, StarRocks, PuppyGraph, your own...) into a package that can be
published to the Cloudera Anywhere Cloud (AWC) marketplace. **No AI required.**

## In plain words
You describe your app (name, Helm chart, ports). The toolkit writes all the AWC files,
checks them, and gives you scripts to copy your charts/images to your registry and publish.

| AWC word | What it means |
|---|---|
| **Engine** | One deployable piece (e.g. a database) described by `engine.yaml` |
| **Blueprint** | The tile users see in the marketplace; it contains one or more engines |
| **Helm chart** | The package of Kubernetes files for the app (you usually already have one) |
| **Image** | The container (Docker) image the chart runs |
| **Registry** | Where charts and images are stored (e.g. `registry.example.com`) |

## Quick start (5 minutes)

```bash
cd awc_onboarding
./awc ui          # opens http://127.0.0.1:8765 - answer the questions, download a zip
```

Prefer files over a form?

```bash
./awc new my-app                       # 1. creates my-app.input.yaml (every line explained)
# edit my-app.input.yaml               # 2. fill in your app's details
./awc build my-app.input.yaml          # 3. generates + validates -> output/my-app/
```

Prefer a terminal Q&A? `./awc wizard`. Not sure where to start? `./awc examples`
(ready-made, pre-generated results are in `examples/bundles/`: Neo4j, StarRocks, PuppyGraph).

Only needs Python 3.10+. The first run sets itself up. `./awc doctor` shows which optional
tools you have.

## What you get
`output/my-app/` contains:

| File | What it is |
|---|---|
| `engine.yaml`, `role.yaml`, `capability.yaml` | The AWC engine definition |
| `blueprint.yaml` | The marketplace tile |
| `chartcatalog.yaml`, `imagecatalog.yaml`, `clusterrequirements.yaml` | What to deploy and how big |
| `mirror.sh` | Copies your chart + images into your registry (needs `helm`, `skopeo`) |
| `publish.sh` | Validates and publishes (dry run by default, `--push` for real; needs `awc-marketplace`) |
| `examples/instance.yaml`, `examples/smoke-test.sh` | Deploy it and check it works |

The result prints `"ok": true` when valid. **Errors** must be fixed; **warnings** should be read.

## Step by step: from nothing to published
1. `./awc new my-app` and edit it. Don't know your images? `./awc images <repoUrl> <chart> <version>`.
2. `./awc build my-app.input.yaml` until `"ok": true`.
3. `cd output/my-app && ./mirror.sh` (skip if your chart/images are already in your registry).
4. `./publish.sh` (dry run), then `./publish.sh --push`.
5. Wait about 60 seconds, then check the marketplace. Run `examples/smoke-test.sh` after deploying.

## Bigger apps (several engines in one Blueprint)
An app made of several engines (e.g. DB + auth + API, or your app + existing CDE/CAI/CDF):
write one input file per engine plus a `blueprint.input.yaml`, then `./awc blueprint blueprint.input.yaml`.
See `examples/dataspark/` and `examples/phoenixai-suite/`.

## Using AI (optional)
`mcp_server/` is an MCP server so an AI assistant (Copilot, Claude, ...) can ask the same
questions and generate the bundle for you. Start it with `python -m mcp_server.server`.
Everything above works without it.

## Troubleshooting
| Problem | Fix |
|---|---|
| `still need '<question>'` | That field is missing in your input file; add it |
| `Unresolved placeholder '<...>'` warning | Only for `helm-operator`: fill in the operator's CRD group/kind |
| `helm template failed ... required` | Add the chart's required values: `--set key=value` |
| `command not found: skopeo` / `awc-marketplace` | Install it; only needed for mirror/publish |

More: [`docs/AWC_CONCEPTS.md`](docs/AWC_CONCEPTS.md) (how AWC fits together) and
[`docs/ONBOARDING_GUIDE.md`](docs/ONBOARDING_GUIDE.md) (reference: all fields, MCP tools, templates).

Not included: building images from source / Dockerfiles.
