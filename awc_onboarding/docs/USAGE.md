# How to use the toolkit — step by step (UI, CLI, AI/MCP)

(Want the big picture first? See `HOW_IT_WORKS.md`.)

All three methods use the same engine and produce the same bundle (Engine, Blueprint, catalogs,
Role, `publish.sh`, `mirror.sh`, `examples/instance.yaml`, `examples/smoke-test.sh`).
Pick whichever you like. **Requirements:** Python 3.10+. Optional: `helm` (image discovery),
`skopeo` (mirroring), `awc-marketplace` (publishing), `kubectl` (smoke test). Run `./awc doctor`.

```
cd awc_onboarding
```

---

## Method 1 — Web UI (easiest, no AI)

1. `./awc ui` (first run sets itself up), then open <http://127.0.0.1:8765>.
2. Choose the **Guided questions** tab. Each question shows help, an **Example**, and a placeholder.
   Type your value (or accept the default) and press **Next**. Press **← Back** to change an earlier answer.
   Unsure which template to pick? Read the help text under "How does this engine ship?".
3. If asked about dependencies, use **Add dependency** for each one, then continue.
4. At the end press **Generate & validate**. Fix any red *errors*; *warnings* are advice.
5. Download the zip or open the file list. Faster alternatives: pick a ready-made example in the
   **Paste input.yaml** tab (Neo4j, StarRocks, PuppyGraph, ...) and run it, or use the **Blueprint** tab to
   combine several engines.
6. Go to **Publish** section below.

## Method 2 — CLI (no AI)

**A. Fill in a file (recommended, repeatable)**
1. `./awc new my-app` creates `my-app.input.yaml` with comments. Or copy `examples/neo4j.input.yaml`.
2. Edit it (partner, engine, helm chart + version, images, ports, registry).
3. Not sure which images the chart needs? `./awc images <repoUrl> <chart> <version>`.
4. `./awc build my-app.input.yaml` writes `output/my-app/` and validates it. Fix errors, re-run.

**B. Answer questions in the terminal**
1. `./awc wizard`. Each question prints an `e.g.` example. Type `?` for help, Enter for the default.
2. The bundle is generated and validated at the end.

**C. Several engines in one Blueprint**
1. One `*.input.yaml` per engine + a `blueprint.input.yaml` (see `examples/dataspark/`, `examples/phoenixai-suite/`).
2. `./awc blueprint blueprint.input.yaml` → one Blueprint, all engines, one `publish.sh`.
   Reuse existing marketplace engines (CDE, CAI, CDF, ...) with `existing:` entries.

## Method 3 — AI assistant via MCP (optional)

1. Run `./awc mcp config` and copy the printed JSON into your MCP client's config
   (Copilot CLI: `~/.copilot/mcp-config.json`; Claude Desktop: `claude_desktop_config.json`; VS Code: `.vscode/mcp.json`
   under `servers`). Restart the client. (`./awc mcp` alone starts the server on stdio.)
2. Ask the assistant, for example:
   > "Use awc-onboarding to onboard Neo4j from https://helm.neo4j.com/neo4j chart neo4j 5.26.0 onto AWC."
3. It calls the tools for you: `start_session` → `get_next_question` / `answer_question` (or `load_answers` /
   `onboard_engine` with a YAML blob) → `generate_bundle` → `validate_bundle`.
   Helpers: `discover_images`, `compose_blueprint`, `list_examples`, `get_example`, `add_dependency`,
   `get_status`, `get_concepts_doc`, `get_onboarding_guide`.
4. Tip: tell the assistant to "ask me one question at a time with an example", or to
   "start from the starrocks example and change the version".

---

## Publish (same for all methods)

Run from the generated folder, e.g. `output/my-app/`:

1. `./mirror.sh` — copies the Helm chart and images to your registry (`publish.destinationRegistry`).
   Needs `helm`, `skopeo`, and a registry login. Skip it if `mirror.skip: true`.
2. `./publish.sh` — **dry run**: prints the `awc-marketplace validate/publish` commands.
3. `./publish.sh --push` — does it for real (needs `awc-marketplace` and cluster access).
4. `kubectl apply -f examples/instance.yaml`, then `./examples/smoke-test.sh` to check it is running.

## Quick help

| Problem | Fix |
|---|---|
| Validator error about registry / `:latest` | Use your own registry and pin image tags. |
| Don't know which template | `docs/CHOOSING_A_TEMPLATE.md` |
| Need nested Helm values / custom capability | `docs/ADVANCED_OPTIONS.md` |
| Concepts (Engine, Blueprint, Capability) | `docs/AWC_CONCEPTS.md` |
