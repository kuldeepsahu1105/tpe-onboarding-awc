# Copy, check, and share

Run commands from the repository folder. Python 3.10 or newer is required.

## Option 1: use the web workbench

```sh
./awc doctor
./awc ui
```

Open <http://127.0.0.1:8765>.

1. **Guided questions** — answer one question at a time.
2. **Paste YAML** — paste a product input or choose a starting example.
3. **Install guide** — list the products that belong in one installation.
4. Choose **Create and check files**.
5. Choose **Save on this computer** or **Download ZIP**.

Saved files are placed in `output/<folder-name>/`. Saving checks the input again
and does not replace an existing folder.

## Option 2: create files with commands

Make a new input file and open it:

```sh
./awc new my-app
vi my-app.input.yaml
```

In `vi`, press `i` to edit. Save with `Esc`, `:wq`, Enter. Then build and check:

```sh
./awc build my-app.input.yaml
```

Find your files in `output/my-app/`. Replace example names, chart and image
versions, registry address, and product settings before using them.

To start from an existing example instead:

```sh
./awc examples
cp examples/neo4j.input.yaml my-app.input.yaml
vi my-app.input.yaml
./awc build my-app.input.yaml
```

Only use `cp` with a new destination filename; it replaces an existing file.

## Find the images used by a Helm chart

Use the chart's actual repository, name, and version:

```sh
./awc images <chart-repository-url> <chart-name> <chart-version>
```

For example:

```sh
./awc images https://helm.neo4j.com/neo4j neo4j 5.26.0
```

Review the listed images and add the correct ones to your input file before
building. Image discovery may download and render the chart.

## Put several products in one install guide

Create a `blueprint.input.yaml` that lists each product input file, then run:

```sh
./awc blueprint path/to/blueprint.input.yaml
```

See the [multi-product example and input format](ONBOARDING_GUIDE.md#2-multi-engine-app-or-combining-with-existing-experiences).

## Copy and publish

Review the scripts and target registry before running them:

```sh
bash -n output/my-app/mirror.sh output/my-app/publish.sh
./awc mirror output/my-app
./awc publish output/my-app
```

The last command checks and prepares a publish using the Marketplace command-line
tool. To actually publish, explicitly add `--push`:

```sh
./awc publish output/my-app --push
```

Copying and publishing need the required tools and registry sign-in. These
commands are separate from creating and checking files.

## Set up registry access (advanced)

Install the `awc-oci-register` tool and sign in using your organization's
instructions. Then:

```sh
./awc registry init /path/to/registry.yaml
vi /path/to/registry.yaml
./awc registry plan /path/to/registry.yaml
./awc registry verify /path/to/registry.yaml
```

Review the plan and target cluster before applying changes:

```sh
APPROVE_REGISTRY_APPLY=1 ./awc registry apply /path/to/registry.yaml
```

## Make a fictional sample ZIP

This ZIP uses made-up names and reserved placeholder addresses. It has no
executable scripts, is not a Qbeast package, and is not ready to install or
publish.

```sh
./awc package sample sample-partner.zip
```

## Optional: connect an AI assistant

```sh
./awc mcp config
```

Copy the printed settings into your AI client's MCP configuration, then restart
the client. For command help, run:

```sh
./awc help
```

For field-by-field settings, safety checks, and deployment notes, see the
[detailed onboarding guide](ONBOARDING_GUIDE.md). For how generated files fit
together, see [How it works](HOW_IT_WORKS.md).
