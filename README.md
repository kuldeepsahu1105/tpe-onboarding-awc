# Partner engine onboarding

Create and check Anywhere Cloud (AWC) engine files on your computer. Copying
images to a registry, publishing, and installing are separate steps.

## Fastest start: web workbench

Requirements: Python 3.10 or newer.

```sh
./awc doctor
./awc ui
```

Open <http://127.0.0.1:8765>, then:

1. Choose **Guided questions**, **Paste YAML**, or **Install guide**.
2. Select an example if you want a starting point.
3. Choose **Create and check files**.
4. Choose **Save on this computer** or **Download ZIP**.

Saved files go under `output/<folder-name>/`. The workbench checks them again
before saving and will not replace an existing folder.

## Build from the terminal

Start a new input file, edit it, then create and check the package:

```sh
./awc new my-app
vi my-app.input.yaml
./awc build my-app.input.yaml
```

In `vi`, press `i` to edit; press `Esc`, type `:wq`, then press Enter to save.
The files are written to `output/my-app/`. Replace all sample names, versions,
image and chart locations, and registry settings before using the package.

See available starting points:

```sh
./awc examples
```

## Copy, preview, and publish

Review the scripts first. `publish` without `--push` runs a preview using the
Marketplace command-line tool; only `--push` publishes.

```sh
bash -n output/my-app/mirror.sh output/my-app/publish.sh
./awc mirror output/my-app
./awc publish output/my-app
# Publish only when the target and files are approved:
./awc publish output/my-app --push
```

## Share a fictional sample ZIP

The sample ZIP contains made-up values, placeholder addresses, and no
executable scripts. It is for reviewing file layout only; it is not a real
Qbeast package and cannot be installed or published.

```sh
./awc package sample sample-partner.zip
```

## More help

- [Copy-and-run instructions](docs/USAGE.md)
- [Detailed setup and input checklist](docs/ONBOARDING_GUIDE.md)
- [Advanced YAML options](docs/ADVANCED_OPTIONS.md)
- [How the toolkit works](docs/HOW_IT_WORKS.md)
- `./awc help` — all commands
