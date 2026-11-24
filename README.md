# tpe-onboarding-awc is Cloudera partner third-party engine onboarding for Anywhere Cloud (AWC)

You finish with a product folder (an engine, the product definition) and an install guide (a blueprint) a customer can deploy. Those files are written on your computer first. Pushing to an image registry and installing into a cluster are separate commands.

Toolkit for onboarding any data/big-data app onto the Cloudera Anywhere Cloud (AWC)
marketplace. Works with or without AI (web UI, CLI wizard, MCP server).

**Start here:** from this repo, run `./awc ui`. One command opens the workbench. `./awc help` and `make help` list the same flow: generate, validate, blueprint, mirror, and publish. The workbench and those actions live in this repository.

Before generating a bundle, follow the [configuration edit commands and parameter
checklists](docs/ONBOARDING_GUIDE.md#edit-source-configuration-before-running)
for YAML inputs, conditional settings, credentials, and offline validation.

Examples have distinct purposes: `examples/*.input.yaml` are inputs to the main
generator, `engine-onboarding/examples/` contains the separate input-form schema
examples, and `examples/bundles/` holds generated snapshots. Hand-authored
packages such as `examples/neo4j/` and `examples/qbeast/` are separate from those
snapshots; their contents and configuration are not interchangeable.

The self-hosted Engine package is in [`tpe-onboarding/`](tpe-onboarding/README.md);
the running application remains at the repository root.

The [Qbeast reference](examples/qbeast/README.md) organizes its supplied
Qbeast 1.3.12 manifests and catalogs. Download it from **Paste input.yaml** in
the workbench, or create `qbeast.zip` with `./awc package qbeast`. Source registry
access and platform-specific deployment prerequisites apply; it is not generated
from an input form.

Blueprint generation defaults to the current marketplace `hardwareTiers` shape.
Use `blueprint.format: legacy` to retain the earlier generator output. See the
[Blueprint and dependency guide](docs/ONBOARDING_GUIDE.md#2-multi-engine-app-or-combining-with-existing-experiences)
and `examples/polaris-udf.blueprint.input.yaml` for the shared-UDF distinction.

For offline infrastructure cost estimates and separate billed costs, use
`./awc cost-report` with explicit inventory and price exports. The sample data
is illustrative, not live pricing. See [cost reporting](docs/COST_REPORTING.md).
