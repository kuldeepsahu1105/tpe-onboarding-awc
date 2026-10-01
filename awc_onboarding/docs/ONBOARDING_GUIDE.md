# Onboarding guide

## Setup
```
cd awc_onboarding && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
```

## 1. Single-engine app (Neo4j, PuppyGraph, StarRocks, ...)
Copy the closest `examples/<name>.input.yaml`, edit it, then:
```
python -m onboarding.cli all --file my-engine.input.yaml
```
Or answer questions interactively: `python -m onboarding.cli wizard --session my-engine`
then `generate` and `validate`. Unanswered optional fields get defaults.
Output goes to `output/<partner-id>/ace/` (engine files + its own `blueprint.yaml`).

## 2. Multi-engine app or combining with existing experiences
Write one `input.yaml` per engine you own plus a `blueprint.input.yaml`:
```
python -m onboarding.cli blueprint --file examples/dataspark/blueprint.input.yaml
```
- `input:` includes and generates one of your engines (its own Blueprint is suppressed).
- `existing:` pulls in an engine already on the cluster (`engine`, `instance`, `version`).
- Declare links in an engine's `dependencies.entries` (`auto` / `optional` / `ref`).

Examples: `examples/dataspark/` (3 engines), `examples/phoenixai-suite/` (own engine + CAI, CDE, CDF).

## 3. Web UI (no AI needed)
```
python -m web.app            # then open http://127.0.0.1:8765
```
Three tabs: guided questions (with dependency form), paste `input.yaml`, and the
multi-engine Blueprint composer. Results show validation, each generated file, and a .zip download.
The CLI above and this UI are fully standalone; AI is optional.

## 4. With an AI agent (MCP, optional)
```
python -m mcp_server.server
```
Tools: `start_session`, `get_next_question`, `answer_question`, `add_dependency`,
`load_answers`, `generate_bundle`, `validate_bundle`, `onboard_engine`,
`compose_blueprint`, `list_examples`, `get_example`, docs tools.

## Charts, images, mirroring and publishing
Declare every image the app needs under `images:` (strings like
`docker.io/starrocks/fe-ubuntu:3.4.3` or `{id, ref}`). Don't know them? Discover them:

```bash
python -m onboarding.cli discover-images --repo-url https://helm.neo4j.com/neo4j \
  --chart neo4j --version 5.26.0 --set neo4j.name=neo4j --set volumes.data.mode=defaultStorageClass
# add --write input.yaml to store the result
```

Generated bundle (besides the ACE YAML):

| File | Purpose | Needs |
|---|---|---|
| `mirror.yaml` | Plan: charts and images, source -> destination | - |
| `mirror.sh` | `helm pull/push` charts and `skopeo copy --all` images into your registry | helm, skopeo, registry logins |
| `publish.sh` | `awc-marketplace validate` + `publish` engine + Blueprint (+ `catalog fetch`). Dry run by default; `--push` pushes | awc-marketplace CLI |

Flow: `mirror.sh` -> `publish.sh` (dry run) -> `publish.sh --push`. For a composed
multi-engine Blueprint, `publish.sh` publishes each engine then the one Blueprint;
run each `engines/<id>/mirror.sh` first. Set `mirror: {skip: true}` if artifacts are
already in your registry.

Not covered: building images from source or writing Dockerfiles, and the
reference repos' staged pipeline (approval gates, smoke tests, JSON reports).

## Before publishing
Fix every validator error; review warnings (e.g. `<TODO>` placeholders in `helm-operator`
scaffolds, Go-template control flow that could not be parsed statically).
