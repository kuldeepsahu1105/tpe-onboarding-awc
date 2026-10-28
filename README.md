# Cloudera partner third-party engine onboarding

You finish with a product folder (an engine, the product definition) and an install guide (a blueprint) a customer can deploy. Those files are written on your computer first. Pushing to an image registry and installing into a cluster are separate commands.

Toolkit for onboarding any data/big-data app onto the Cloudera Anywhere Cloud (AWC)
marketplace. Works with or without AI (web UI, CLI wizard, MCP server).

**Start here:** [`awc_onboarding/README.md`](awc_onboarding/README.md), then run `cd awc_onboarding && ./awc ui`.

Before generating a bundle, follow the [configuration edit commands and parameter
checklists](awc_onboarding/docs/ONBOARDING_GUIDE.md#edit-source-configuration-before-running)
for YAML inputs, conditional settings, credentials, and offline validation.

Partner engine package: [`bluemetrix-stms/`](bluemetrix-stms/README.md).
