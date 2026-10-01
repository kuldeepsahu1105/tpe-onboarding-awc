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

## 3. With an AI agent (MCP)
```
python -m mcp_server.server
```
Tools: `start_session`, `get_next_question`, `answer_question`, `add_dependency`,
`load_answers`, `generate_bundle`, `validate_bundle`, `onboard_engine`,
`compose_blueprint`, `list_examples`, `get_example`, docs tools.

## Before publishing
Fix every validator error; review warnings (e.g. `<TODO>` placeholders in `helm-operator`
scaffolds, Go-template control flow that could not be parsed statically).
