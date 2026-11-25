"""Package curated, hand-authored reference manifests without regenerating them."""

from __future__ import annotations

import argparse
import io
from pathlib import Path
import zipfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {
    "qbeast": (
        "README.md", "blueprint.yaml", "engine.yaml", "role.yaml",
        "capabilities.yaml", "oci-register.config.example.yaml",
        "imagecatalog.yaml", "chartcatalog.yaml", "mirror.yaml", "mirror.sh", "publish.sh",
    ),
    "sample": (
        "README.md", "blueprint.yaml", "engine.yaml", "role.yaml",
        "capabilities.yaml", "imagecatalog.yaml", "chartcatalog.yaml", "mirror.yaml",
    ),
}
DOWNLOADABLE_PACKAGES = {"sample"}


def reference_files(name: str) -> dict[str, bytes]:
    if name not in PACKAGES:
        raise ValueError(f"Unknown reference package: {name}")
    folder = ROOT / "examples" / name
    files = {filename: (folder / filename).read_bytes() for filename in PACKAGES[name]}
    docs = {
        filename: list(yaml.safe_load_all(files[filename]))
        for filename in ("blueprint.yaml", "engine.yaml", "role.yaml", "capabilities.yaml")
    }
    blueprint = docs["blueprint.yaml"]
    engine = docs["engine.yaml"]
    roles = docs["role.yaml"]
    capabilities = docs["capabilities.yaml"]
    if len(blueprint) != 1 or len(engine) != 1:
        raise ValueError("Expected one Blueprint and one Engine")
    if not isinstance(blueprint[0], dict) or blueprint[0].get("kind") != "Blueprint":
        raise ValueError("Invalid Blueprint")
    if not isinstance(engine[0], dict) or engine[0].get("kind") != "Engine":
        raise ValueError("Invalid Engine")
    engine_name = engine[0].get("metadata", {}).get("name")
    instances = blueprint[0].get("spec", {}).get("instances", [])
    if not engine_name or not any(i.get("engine") == engine_name for i in instances):
        raise ValueError("Blueprint does not reference the Engine")
    if not all(isinstance(role, dict) for role in roles) or {r.get("kind") for r in roles} != {
        "Role", "RoleBinding", "ClusterRole"
    }:
        raise ValueError("Expected Role, RoleBinding, and ClusterRole")
    if len(capabilities) != 1 or not isinstance(capabilities[0], dict):
        raise ValueError("Expected one Capability")
    capability = capabilities[0]
    if capability.get("kind") != "Capability" or not any(
        entry.get("capability") == capability.get("metadata", {}).get("name")
        for entry in engine[0].get("spec", {}).get("provides", [])
    ):
        raise ValueError("Engine does not provide the Capability")
    role = next(r for r in roles if r["kind"] == "Role")
    binding = next(r for r in roles if r["kind"] == "RoleBinding")
    if binding.get("roleRef", {}).get("name") != role.get("metadata", {}).get("name"):
        raise ValueError("RoleBinding does not reference the Role")
    return files


def reference_zip(name: str) -> bytes:
    if name not in DOWNLOADABLE_PACKAGES:
        raise ValueError(f"{name!r} is not available as a shareable ZIP; use the fictional sample package")
    files = reference_files(name)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for filename, contents in files.items():
            info = zipfile.ZipInfo(filename)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100755 if filename.endswith(".sh") else 0o100644) << 16
            archive.writestr(info, contents)
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", choices=sorted(DOWNLOADABLE_PACKAGES))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = reference_zip(args.name)
    args.output.write_bytes(data)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
