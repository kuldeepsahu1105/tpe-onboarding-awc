# Partner third-party engine onboarding

This package describes the partner onboarding app as an Anywhere Cloud engine and blueprint. It is not a second copy of the Python app.

## What the customer gets

A workbench on their computer:

- Guided questions
- Paste YAML
- An install guide for more than one product
- Publish, after the image address is filled in

The running app stays at the repository root. Start it with `./awc ui` from that root. The pages live in `web/`. The questions and checks live in `onboarding/`.

## What this package does not do

It does not push by itself. Registry host, repository, image name, and tag are filled at publish time. There is no default cloud registry. No password is stored in these YAML files.

The Helm chart and container image are not published yet. `chartcatalog.yaml` and `imagecatalog.yaml` are empty on purpose. `mirror.sh` and `publish.sh` stop while those lists, or the registry names, are still empty or still placeholders. Nothing is copied and nothing is sent on that path.

## Files

| File | What it is |
|---|---|
| `blueprint.yaml` | The install a customer would see, once a chart exists |
| `engine.yaml` | The product definition. No chart release yet |
| `capabilities.yaml` | The workbench address shape. No password |
| `chartcatalog.yaml` | Empty until a chart exists |
| `imagecatalog.yaml` | Empty until an image exists |
| `role.yaml` | Permissions for a future chart install |
| `mirror.yaml` | Copy plan. Empty until names are filled |
| `mirror.sh` | Refuses to copy while names are placeholders |
| `publish.sh` | Refuses to send while names are placeholders |
| `oci-register.config.example.yaml` | Registry registration example. Password stays in a separate file |
| `examples/instance.yaml` | One local example of the engine, port 8765 |
