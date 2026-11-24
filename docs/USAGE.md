# How to use the toolkit — step by step (UI, CLI, AI/MCP)

(Want the big picture first? See `HOW_IT_WORKS.md`.)

All three methods use the same engine and produce the same bundle (Engine, Blueprint, catalogs,
Role, `publish.sh`, `mirror.sh`, `examples/instance.yaml`, `examples/smoke-test.sh`).
Current output omits the removed ClusterRequirements resource; legacy output retains it.
Pick whichever you like. **Requirements:** Python 3.10+. Optional: `helm` (image discovery),
`skopeo` (mirroring), `awc-marketplace` (publishing), `kubectl` (smoke test). Run `./awc doctor`.

```
cd /path/to/tpe-onboarding-awc
```

---

## Method 1 — Web UI (easiest, no AI)

1. `./awc ui` (first run sets itself up), then open <http://127.0.0.1:8765>.
2. Choose the **Guided questions** tab. Each question shows help, an **Example**, and a placeholder.
   Type your value (or accept the default) and press **Next**. Press **← Back** to change an earlier answer.
   Unsure which template to pick? Read the help text under "How does this engine ship?".
3. If asked about dependencies, use **Add dependency** for each one, then continue.
4. Before **Generate & validate**, review the [input checklist](ONBOARDING_GUIDE.md#engine-input-checklist).
   Use the paste-YAML tab for a complete `images[]` list, `engine.roles[]` or
   advanced fields not collected by guided questions. Fix red *errors* and
   review warnings; unresolved scaffold placeholders must block publishing.
5. Download the zip or open the file list. Faster alternatives: pick a ready-made example in the
   **Paste input.yaml** tab (Neo4j, StarRocks, PuppyGraph, ...) and run it, or use the **Blueprint** tab to
   combine several engines.
   For Qbeast, use **Download Qbeast reference ZIP** in that tab instead. This
   packages the supplied manifests and a derived capability contract, not a generated input.
6. Go to **Publish** section below.

## Method 2 — CLI (no AI)

**A. Fill in a file (recommended, repeatable)**
1. `./awc new my-app` creates `my-app.input.yaml` with comments. Or copy `examples/neo4j.input.yaml`.
2. Run `vi my-app.input.yaml`. Complete the [required/defaulted and conditional key checklists](ONBOARDING_GUIDE.md#engine-input-checklist)
   (including chart, all images, ports, sizing and registry). There is no `.env`
   file. In `vi`, `i` edits; `Esc` then `:wq` + Enter saves/quits; `:q!` discards.
3. Not sure which images the chart needs? `./awc images <repoUrl> <chart> <version>`.
4. `./awc build my-app.input.yaml` writes `output/my-app/` and validates it. Fix errors, re-run.

For the hand-authored Qbeast reference, run `./awc package qbeast [output.zip]`.
Read its README for the external catalogs and other deployment prerequisites.

**B. Answer questions in the terminal**
1. `./awc wizard`. Each question prints an `e.g.` example. Type `?` for help, Enter for the default.
2. This collects answers in the `default` session only. With the toolkit virtualenv installed, run
   `.venv/bin/python -m onboarding.cli generate --session default`, then
   `.venv/bin/python -m onboarding.cli validate --session default`.
   Output defaults to `output/<partner-id>/ace/`. Do not edit session JSON or generated files.

**C. Several engines in one Blueprint**
1. One `*.input.yaml` per engine, plus a `blueprint.input.yaml` you write when several of your engines install together. DataSpark and Phoenix AI are each a single file (`examples/dataspark.input.yaml`, `examples/phoenixai.input.yaml`).
   Follow the [copy commands, explicit vi commands and composer checklist](ONBOARDING_GUIDE.md#2-multi-engine-app-or-combining-with-existing-experiences);
   review each engine source and the composer source before running.
2. `./awc blueprint blueprint.input.yaml` → one Blueprint, all engines, one `publish.sh`.
   List other marketplace engines (CDE, CAI, CDF, ...) with `existing:` entries.
   Shared running instances require separate runtime bindings; listing an engine does not reuse one.

## Method 3 — AI assistant via MCP (optional)

1. Run `./awc mcp config` and copy the printed JSON into your MCP client's config
   (Copilot CLI: `~/.copilot/mcp-config.json`; Claude Desktop: `claude_desktop_config.json`; VS Code: `.vscode/mcp.json`
   under `servers`). Restart the client. (`./awc mcp` alone starts the server on stdio.)
   For Copilot CLI, open `vi ~/.copilot/mcp-config.json` and merge the printed
   `mcpServers.awc-onboarding` entry without overwriting other servers.
   Verify `command` is the absolute toolkit `.venv/bin/python`, `args` is
   `["-m", "mcp_server.server"]`, and `cwd` is this repository
   directory. Other clients may require a different enclosing schema; do not
   paste `mcpServers` verbatim into a client that expects `servers`. These are
   client connection settings, not engine/environment inputs; no credentials
   are needed in this server entry.
2. Ask the assistant, for example:
   > "Use awc-onboarding to onboard Neo4j from https://helm.neo4j.com/neo4j chart neo4j 5.26.0 onto AWC."
3. It calls the tools for you: `start_session` → `get_next_question` / `answer_question` (or `load_answers` /
   `onboard_engine` with a YAML blob) → `generate_bundle` → `validate_bundle`.
   Helpers: `discover_images`, `compose_blueprint`, `list_examples`, `get_example`, `add_dependency`,
   `get_status`, `get_concepts_doc`, `get_onboarding_guide`.
   Use `get_reference_package("qbeast")` for the supplied Qbeast manifests and
   partner instructions; these are not generator inputs.
4. Tip: tell the assistant to "ask me one question at a time with an example", or to
   "start from the starrocks example and change the version".

---

## Publish (same for all methods)

First complete the [offline validation sequence and credential/source guidance](ONBOARDING_GUIDE.md#safe-validation-sequence-before-mirroring-or-publishing).
Never edit generated files to fix configuration; update the input and regenerate.
The operations below are **not** part of a local/offline check and need approval
for the target registry/cluster.

### Register the marketplace registry

Install [awc-oci-register](https://github.com/agupta-git/awc-oci-register) separately
and add it to `PATH` or set `AWC_OCI_REGISTER` to its executable. It registers
registry access; it does not mirror artifacts or publish Blueprints. Set up the
provider CLI and credentials according to its instructions, outside the UI.

```sh
./awc registry init /path/to/registry.yaml
# Edit the config with your registry, credential-file paths, and AWC settings.
./awc registry plan /path/to/registry.yaml
./awc registry verify /path/to/registry.yaml
# After reviewing the plan, target Kubernetes context and authorization:
APPROVE_REGISTRY_APPLY=1 ./awc registry apply /path/to/registry.yaml
```

`init` will not overwrite an existing file; if initialization fails, inspect or
remove the empty file before retrying. `plan` can access the cluster and resolve
credentials. `apply` verifies first, then can modify pull credentials and marketplace
registration and restart the console. Check the upstream configuration and your
target cluster before running it.

The web **Publish → Run reviewed registry and bundle operations** section also runs
these commands after confirmation. It accepts paths, not passwords; subprocess
output is hidden to avoid exposing credentials, so inspect plan and verification
details in a terminal. Real operations require the localhost UI, and bundle scripts
must be reviewed and located under this checkout's `output/`. The older job-list
buttons are simulations, not publishing.

### Mirror and publish

Run from the generated folder, e.g. `output/my-app/`:

1. `./mirror.sh` — copies the Helm chart and images to your registry (`publish.destinationRegistry`).
   Needs `helm`, `skopeo`, and a registry login. Skip it if `mirror.skip: true`.
2. `./publish.sh` — **no-push mode**: actually invokes `awc-marketplace validate` and `publish` without `--push`; it is not an offline command printer.
3. `./publish.sh --push` — does it for real (needs `awc-marketplace` and cluster access).
4. Only after reviewing the generated instance defaults and intended cluster/context,
   `kubectl apply -f examples/instance.yaml`, then `./examples/smoke-test.sh`.
   Change defaults through source inputs/templates and regenerate, not by editing
   this generated instance. The smoke script probes connectivity, not full
   application correctness.

## Quick help

| Problem | Fix |
|---|---|
| Validator error about registry / `:latest` | Use your own registry and pin image tags. |
| Don't know which template | `docs/CHOOSING_A_TEMPLATE.md` |
| Need nested Helm values / custom capability | `docs/ADVANCED_OPTIONS.md` |
| Concepts (Engine, Blueprint, Capability) | `docs/AWC_CONCEPTS.md` |
