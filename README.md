# tpe-onboarding-awc is Cloudera partner third-party engine onboarding for Anywhere Cloud (AWC)

You finish with a product folder (an engine, the product definition) and an install guide (a blueprint) a customer can deploy. Those files are written on your computer first. Pushing to an image registry and installing into a cluster are separate commands.

Toolkit for onboarding any data/big-data app onto the Cloudera Anywhere Cloud (AWC)
marketplace. Works with or without AI (web UI, CLI wizard, MCP server).

**Start here:** from this repo, run `./awc ui`. One command opens the workbench. `./awc help` and `make help` list the same flow: generate, validate, blueprint, mirror, and publish. The workbench and those actions live in this repository.

Before generating a bundle, follow the [configuration edit commands and parameter
checklists](docs/ONBOARDING_GUIDE.md#edit-source-configuration-before-running)
for YAML inputs, conditional settings, credentials, and offline validation.

Example packages live in `examples/`, including `examples/bluemetrix-stms` and `examples/neo4j`. They are not a second onboarding app.

The [Qbeast reference](examples/qbeast/README.md) organizes its supplied
manifests and a derived capability contract. Download it from **Paste input.yaml** in the workbench, or create
`qbeast.zip` with `./awc package qbeast`. It requires separately supplied
catalogs and platform dependencies; it is not generated from an input form.
